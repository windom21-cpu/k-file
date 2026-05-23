"""drop_history の 1 エントリを「逆方向に実行」する Undo ロジック (Qt 非依存)。

actionごとの逆操作:
- inject / move: 現在の dst パスにあるファイルを src パスへ shutil.move
- rename:        dst (新名) → src (旧名) に rename
- trash:         OS ごみ箱からの自動復元は OS 依存のため失敗扱い、
                 ユーザーに手動復元を案内 (HANDOVER §2 既定)

戻り値: (成功フラグ, ユーザー向けメッセージ)。
副作用としてファイル/フォルダを動かすだけで、DB 更新 (status='undone' 等) は
呼び出し側 (MainWindow) が担当する — file_ops と同じ責務分離。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping


def undo_action(row: Mapping) -> tuple[bool, str]:
    """drop_history 行を逆実行。dict-like で十分 (sqlite3.Row もそのまま渡せる)。"""
    action = row["action"]
    src_str = row["src_path"]
    dst_str = row["dst_path"]
    if action in ("inject", "move"):
        return _undo_movelike(src_str, dst_str)
    if action == "rename":
        return _undo_rename(src_str, dst_str)
    if action == "trash":
        name = Path(src_str).name if src_str else "(不明)"
        return False, (
            f"「{name}」は OS のごみ箱にあります — "
            "ごみ箱で右クリック →「元に戻す」で復元 "
            "(編集メニュー →「ごみ箱を開く」)"
        )
    return False, f"未対応のアクション: {action}"


def _undo_movelike(src_str: str, dst_str: str) -> tuple[bool, str]:
    """inject / move を逆実行: dst にあるファイルを src に戻す。"""
    if not dst_str or not src_str:
        return False, "履歴に必要なパスが欠けています"
    src = Path(src_str)
    dst = Path(dst_str)
    if not dst.exists():
        return False, f"戻すべきファイルが見つかりません: {dst}"
    if src.exists():
        return False, f"戻し先に既にファイルがあります: {src}"
    try:
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(src))
    except OSError as e:
        return False, f"ファイルを戻せませんでした: {e}"
    return True, f"{dst.name} を元の位置へ戻しました"


def _undo_rename(src_str: str, dst_str: str) -> tuple[bool, str]:
    """rename を逆実行: dst (新名) → src (旧名)。"""
    if not dst_str or not src_str:
        return False, "履歴に必要なパスが欠けています"
    src = Path(src_str)
    dst = Path(dst_str)
    if not dst.exists():
        return False, f"名前を戻すべきファイルが見つかりません: {dst}"
    if src.exists():
        return False, f"旧名が既に使われています: {src.name}"
    try:
        dst.rename(src)
    except OSError as e:
        return False, f"名前を戻せませんでした: {e}"
    return True, f"{dst.name} → {src.name} に名前を戻しました"
