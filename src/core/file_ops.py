"""ファイル投入・移動・削除の中核ロジック (Qt 非依存、ユニットテスト可能)。

業務的安全性のため次の不変条件を満たす:
- **inject (Inbox → 事件サブフォルダ)**: Copy → サイズ検証 → 元削除。途中失敗時は
  元ファイルが残るので、ユーザーが Inbox から再操作できる (二重投入は起きない)。
- **move (cross-case)**: shutil.move 一発 (Dropbox 30 日履歴 + 自前 Undo が保険)。
- **rename**: 同フォルダ内の os.rename。Win 禁則文字をモジュール定数でチェック。
- **trash**: send2trash で OS ごみ箱へ。
- **衝突回避**: dst に同名ファイルがあれば自動連番 `name (2).ext`、`name (3).ext`...

infra/kfile_db への履歴記録は呼び出し側 (UI 層) で行う — file_ops 自体は DB に
依存しないことで純粋関数として残し、テストを楽にする。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

# Windows のファイル名で使えない文字。Linux/Mac でも一律禁止 (Dropbox 同期での
# 事故防止)。改行・タブ等は別途 strip するので、ここでは「明示的な記号」のみ。
FORBIDDEN_CHARS = set('\\/:*?"<>|')


@dataclass
class OpResult:
    """投入・移動・rename・削除の結果。UI 通知・履歴記録に使う。"""

    ok: bool
    action: str           # "inject" / "move" / "rename" / "trash"
    src: Path
    dst: Path | None      # 削除時は None
    renamed_to: str       # 衝突回避で変わった最終ファイル名 (元と同じなら == src.name)
    original_name: str    # 投入前のファイル名 (Inbox 上の名前)
    collided: bool        # 自動連番が発生したか
    error: str = ""       # ok=False 時のメッセージ


def validate_name(name: str) -> str | None:
    """ファイル名の禁則チェック。OK なら None、NG なら理由メッセージを返す。"""
    if not name or name.strip() == "":
        return "ファイル名が空です"
    if name in (".", ".."):
        return "予約名は使えません: . / .."
    bad = [c for c in name if c in FORBIDDEN_CHARS]
    if bad:
        return 'ファイル名に使えない文字が含まれています:  \\ / : * ? " < > |'
    if name.endswith(" ") or name.endswith("."):
        return "ファイル名の末尾に空白やピリオドは使えません"
    return None


def resolve_collision(dst_dir: Path, name: str) -> tuple[Path, bool]:
    """dst_dir / name が既存なら ` (2)`, ` (3)`... と連番付与した未使用パスを返す。

    返り値の bool は「連番付与が発生したか」(True なら衝突を回避した)。
    """
    candidate = dst_dir / name
    if not candidate.exists():
        return candidate, False
    stem = candidate.stem
    suffix = candidate.suffix
    i = 2
    while True:
        candidate = dst_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate, True
        i += 1


def inject(src: Path, dst_dir: Path, new_name: str | None = None) -> OpResult:
    """Inbox → 事件サブフォルダ投入。

    ファイル: 1) dst_dir 確保  2) 衝突回避で最終 dst パス確定
             3) shutil.copy2 で属性込みコピー  4) サイズ検証
             5) 元 src を unlink。途中失敗時は元が残るため再操作可能。

    フォルダ (2026-05-25 追加): デスクトップに作った作業フォルダ等を事件サブ
    フォルダに丸ごと運ぶ。サイズ検証は実施せず shutil.move 一発で移動する
    (フォルダ配下の N ファイル全てを byte-by-byte 検証するのは重く、複合機の
    スキャン PDF とは違って書き込み完了タイミングの心配もないため)。
    """
    src = Path(src)
    dst_dir = Path(dst_dir)
    original_name = src.name

    is_folder = src.is_dir() and not src.is_symlink()
    if not (src.is_file() or is_folder):
        return OpResult(
            False, "inject", src, None, original_name, original_name, False,
            error=f"投入元が見つかりません: {src}",
        )
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return OpResult(
            False, "inject", src, None, original_name, original_name, False,
            error=f"投入先フォルダを作成できません: {e}",
        )

    name = new_name if new_name else original_name
    err = validate_name(name)
    if err:
        return OpResult(
            False, "inject", src, None, original_name, original_name, False,
            error=err,
        )

    dst_path, collided = resolve_collision(dst_dir, name)

    if is_folder:
        # フォルダはコピー検証を省略して shutil.move 一発 (cross-case Move と同方式)
        try:
            shutil.move(str(src), str(dst_path))
        except OSError as e:
            return OpResult(
                False, "inject", src, None, name, original_name, collided,
                error=f"フォルダ投入に失敗しました: {e}",
            )
        return OpResult(
            True, "inject", src, dst_path, dst_path.name, original_name, collided,
        )

    try:
        shutil.copy2(str(src), str(dst_path))
    except OSError as e:
        # 途中で部分書込されている可能性があるので、検証失敗扱いでクリーンアップ
        if dst_path.exists():
            try:
                dst_path.unlink()
            except OSError:
                pass
        return OpResult(
            False, "inject", src, None, original_name, name, collided,
            error=f"コピーに失敗しました: {e}",
        )

    # 検証: サイズ一致 (mtime まで見ると Dropbox 巻取等で誤検出するため size のみ)
    try:
        if dst_path.stat().st_size != src.stat().st_size:
            # 不一致ならコピー先を消して元を残す
            try:
                dst_path.unlink()
            except OSError:
                pass
            return OpResult(
                False, "inject", src, dst_path, name, original_name, collided,
                error="コピー後のサイズが一致しません (コピー失敗とみなしました)",
            )
    except OSError as e:
        return OpResult(
            False, "inject", src, dst_path, name, original_name, collided,
            error=f"投入後の検証に失敗しました: {e}",
        )

    # 元削除 (ここまで来たらコピーは確実に成功している)
    try:
        src.unlink()
    except OSError as e:
        # コピーは成功しているのでファイル本体は dst にある。
        # 元削除に失敗した旨を伝えて、ユーザーに後始末させる (Undo 時の整合のため
        # 行動を完了とは扱わない)。
        return OpResult(
            False, "inject", src, dst_path, dst_path.name, original_name, collided,
            error=f"投入後の元ファイル削除に失敗しました: {e}",
        )

    return OpResult(
        True, "inject", src, dst_path, dst_path.name, original_name, collided,
    )


def move(src: Path, dst_dir: Path, new_name: str | None = None) -> OpResult:
    """事件A → 事件B など、Move 操作 (cross-case D&D)。

    inject と異なり Copy→検証→削除のステップは踏まない (両端で「移動した」のが
    自然なため shutil.move 一発)。Dropbox 30 日履歴 + 自前 Undo が保険。
    """
    src = Path(src)
    dst_dir = Path(dst_dir)
    original_name = src.name

    if not src.exists():
        return OpResult(
            False, "move", src, None, original_name, original_name, False,
            error=f"移動元が見つかりません: {src}",
        )
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return OpResult(
            False, "move", src, None, original_name, original_name, False,
            error=f"移動先フォルダを作成できません: {e}",
        )

    name = new_name if new_name else original_name
    err = validate_name(name)
    if err:
        return OpResult(
            False, "move", src, None, original_name, original_name, False,
            error=err,
        )

    dst_path, collided = resolve_collision(dst_dir, name)

    try:
        shutil.move(str(src), str(dst_path))
    except OSError as e:
        return OpResult(
            False, "move", src, None, name, original_name, collided,
            error=f"移動に失敗しました: {e}",
        )

    return OpResult(
        True, "move", src, dst_path, dst_path.name, original_name, collided,
    )


def copy(src: Path, dst_dir: Path, new_name: str | None = None) -> OpResult:
    """src を dst_dir にコピー (元は残す)。衝突時は自動連番。

    クロス事件 Copy (Ctrl+D&D) で使う。ファイルもフォルダも対応:
    - ファイル: shutil.copy2 (mtime / 属性込み)
    - フォルダ: shutil.copytree (再帰)
    move と違い元ファイルは保持されるため、Undo は dst を削除するだけ。
    """
    src = Path(src)
    dst_dir = Path(dst_dir)
    original_name = src.name

    if not src.exists():
        return OpResult(
            False, "copy", src, None, original_name, original_name, False,
            error=f"コピー元が見つかりません: {src}",
        )
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return OpResult(
            False, "copy", src, None, original_name, original_name, False,
            error=f"コピー先フォルダを作成できません: {e}",
        )

    name = new_name if new_name else original_name
    err = validate_name(name)
    if err:
        return OpResult(
            False, "copy", src, None, original_name, original_name, False,
            error=err,
        )

    dst_path, collided = resolve_collision(dst_dir, name)

    try:
        if src.is_dir():
            shutil.copytree(str(src), str(dst_path))
        else:
            shutil.copy2(str(src), str(dst_path))
    except OSError as e:
        return OpResult(
            False, "copy", src, None, name, original_name, collided,
            error=f"コピーに失敗しました: {e}",
        )

    return OpResult(
        True, "copy", src, dst_path, dst_path.name, original_name, collided,
    )


def rename(src: Path, new_name: str) -> OpResult:
    """同フォルダ内の rename。衝突時は自動連番。"""
    src = Path(src)
    original_name = src.name

    if not src.exists():
        return OpResult(
            False, "rename", src, None, original_name, original_name, False,
            error=f"対象が見つかりません: {src}",
        )

    err = validate_name(new_name)
    if err:
        return OpResult(
            False, "rename", src, None, original_name, original_name, False,
            error=err,
        )

    if new_name == original_name:
        # 何もしない (UI 側で「変更なし」として扱う)
        return OpResult(
            True, "rename", src, src, original_name, original_name, False,
        )

    dst_path, collided = resolve_collision(src.parent, new_name)
    try:
        src.rename(dst_path)
    except OSError as e:
        return OpResult(
            False, "rename", src, None, new_name, original_name, collided,
            error=f"名前を変更できませんでした: {e}",
        )

    return OpResult(
        True, "rename", src, dst_path, dst_path.name, original_name, collided,
    )


def trash(src: Path) -> OpResult:
    """OS ごみ箱に送る (send2trash)。失敗時は ok=False。

    send2trash は本物のごみ箱に送るため復元は OS 側で行う (k-file の Undo は
    `drop_history` を参照してごみ箱からの復元を試行する形になる — M4)。
    """
    src = Path(src)
    original_name = src.name

    if not src.exists():
        return OpResult(
            False, "trash", src, None, original_name, original_name, False,
            error=f"対象が見つかりません: {src}",
        )

    try:
        # send2trash は import 失敗時に明確なエラーが出るよう lazy import する
        from send2trash import send2trash
    except ImportError as e:
        return OpResult(
            False, "trash", src, None, original_name, original_name, False,
            error=f"send2trash が利用できません: {e}",
        )

    try:
        send2trash(str(src))
    except OSError as e:
        return OpResult(
            False, "trash", src, None, original_name, original_name, False,
            error=f"ごみ箱に送れませんでした: {e}",
        )

    return OpResult(
        True, "trash", src, None, original_name, original_name, False,
    )
