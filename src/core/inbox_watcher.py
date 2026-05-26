"""Inbox 監視対象フォルダの実ファイル走査 + 変更検知。

scan / Desktop / 作業 等の監視対象フォルダを QFileSystemWatcher で見張り、
ファイルの増減があれば changed シグナルを出す。一覧は PDF + 画像のみに絞り、
ソースごとの「更新日時フィルタ」(例: 実 Desktop は 7 日以内のみ) も適用。

core 層だが GUI 非依存の QtCore (QFileSystemWatcher / QObject) には依存する。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

# 2026-05-25: ホワイトリスト方式 (INBOX_EXTENSIONS) を撤去し、Inbox は
# 「監視先フォルダの中身をほぼそのまま見せる」方針に転換。背景は:
#   - k-systemz のサブアプリ (k-photo 等) が `.k-photo` 等の JSON 一時保存
#     ファイルを生成 → 事件フォルダに保管 → リネーム/移動/削除する運用がある
#   - ユーザーがデスクトップに作業フォルダを作って事件に運ぶ流れがある
#   - 拡張子をホワイトリストで列挙していくと未知の業務拡張子を取りこぼす
# ブラックリストは「明らかに見せたくない」ものだけ:
#   - 一時/未完了 (.tmp / .part / .crdownload / .download)
#   - OS のシステムファイル (.DS_Store / Thumbs.db / desktop.ini)
#   - ドット隠しファイル (Linux 流儀、ただし `.k*` 系は k-systemz 連携で残す)
INBOX_EXCLUDE_EXTENSIONS = {
    ".tmp", ".part", ".crdownload", ".download",
}
INBOX_EXCLUDE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

# 0 バイトファイルが「複合機が書き込み中」なのか「実体として空」なのかを
# 判別する閾値 (秒)。更新時刻が現在から N 秒以内 ＆ 0 バイトなら書き込み中扱い。
_INCOMPLETE_GRACE_SEC = 5.0


def _is_visible_in_inbox(p: Path) -> bool:
    """Inbox に表示すべきかの判定 (ファイル/フォルダ共通)。

    - システム/一時ファイルは除外
    - ドット隠しは除外 (ただし `.k*` は k-systemz サブアプリ管理ファイルなので残す)
    """
    name = p.name
    if name in INBOX_EXCLUDE_NAMES:
        return False
    # `.kphoto-config` / `.k-photo` 等の k-systemz 連携 dotfile は表示対象。
    # k-systemz サブアプリの実拡張子は `.kphoto` / `.kevi` (ハイフン無し) だが、
    # 将来 dotfile 形式を採る可能性も含めて広めに `.k*` で許容する
    # (2026-05-26 K-SystemZ 側連携確認に基づく)。
    if name.startswith(".") and not name.startswith(".k"):
        return False
    if p.is_file() and p.suffix.lower() in INBOX_EXCLUDE_EXTENSIONS:
        return False
    return True


@dataclass
class InboxSource:
    """Inbox の 1 監視先設定。同一ラベルを複数持つと同じフィルタタブに合流する。

    cutoff_days を指定すると、その日数より古い更新日時のファイルを除外する
    (None なら全件表示)。実 Desktop のような長期蓄積場所で過去 PDF が並ぶ
    のを防ぐのに使う。
    """

    label: str
    path: Path
    cutoff_days: int | None = None


@dataclass
class InboxFile:
    """Inbox 監視対象フォルダ内の 1 エントリ (ファイル or フォルダ)。

    フォルダの場合は is_dir=True、size=0 で扱う。fields 名 (InboxFile) は歴史的に
    ファイル前提だったが、2026-05-25 以降は「Inbox は監視先フォルダの中身を
    そのまま見せる」方針に転換 (k-systemz サブアプリ・デスクトップ作業フォルダの
    現実反映) のためフォルダも含む。
    """

    name: str
    path: Path
    source: str   # 出所ラベル ("scan" / "Desktop" / "作業" 等)
    mtime: float
    size: int
    is_dir: bool = False


def list_inbox_files(
    sources: list[InboxSource], now: float | None = None
) -> list[InboxFile]:
    """純粋関数として list_files を切り出し (Qt 非依存・テスト可能)。

    ソースごとの cutoff_days があれば、現在時刻からその日数より古い更新日時の
    ファイルを除外する。`now` を渡せば現在時刻を上書きできる (テスト用)。
    """
    base = now if now is not None else time.time()
    out: list[InboxFile] = []
    # 同じ実パスが複数ソースに重複登録された場合の二重表示を防止。
    # 2026-05-25 本番テスト: Desktop 行が dev デフォルトに 2 つあり、ユーザーが
    # 両方とも実 Windows デスクトップに向けたら各ファイルが 2 倍表示される事故が
    # 発生 → resolve 済みパスで dedupe する保険を入れる (最初に出現したラベルを採用)。
    seen_resolved: set[Path] = set()
    for src in sources:
        if not src.path.is_dir():
            continue
        try:
            resolved = src.path.resolve()
        except OSError:
            resolved = src.path
        if resolved in seen_resolved:
            continue
        seen_resolved.add(resolved)
        cutoff_ts = (
            base - src.cutoff_days * 86400 if src.cutoff_days is not None else None
        )
        try:
            children = list(src.path.iterdir())
        except OSError:
            continue
        for p in children:
            # ファイル/フォルダ両方を対象に。symlink は target に追従して判定
            try:
                is_dir = p.is_dir()
                is_file = p.is_file()
            except OSError:
                continue
            if not (is_file or is_dir):
                continue
            if not _is_visible_in_inbox(p):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if cutoff_ts is not None and st.st_mtime < cutoff_ts:
                continue   # 古いものは表示しない
            # 複合機がスキャン PDF を書き込んでいる途中で
            # QFileSystemWatcher が発火 → 0KB のファイルが Inbox に並ぶバグ
            # (2026-05-25 本番テスト報告) を抑制する。0 バイト & 最近更新 ＆
            # ファイル (フォルダは size=0 が正常なので除外しない)。
            if (
                is_file
                and st.st_size == 0
                and (base - st.st_mtime) < _INCOMPLETE_GRACE_SEC
            ):
                continue
            size = 0 if is_dir else st.st_size
            out.append(
                InboxFile(p.name, p, src.label, st.st_mtime, size, is_dir=is_dir)
            )
    return out


class InboxWatcher(QObject):
    """監視対象フォルダ群を見張り、変更時に changed を出す。

    複合機が PDF を連続書き込み中は directoryChanged が連発するので、最後の
    発火から 700ms 沈黙した時点で 1 回だけ changed を emit する (debounce)。
    これにより「書き込み開始時 0 バイト → 増加中 → 完了」の途中の中途半端な
    状態を Inbox に出さず、安定後の最終状態を見せられる。
    """

    changed = Signal()

    # 連続書き込みの最後の発火から実 emit までの遅延 (ms)。長すぎると
    # ユーザーが「出てこない」と感じ、短すぎると 0KB が見える。
    DEBOUNCE_MS = 700

    def __init__(
        self,
        sources: list[InboxSource],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._sources: list[InboxSource] = [
            InboxSource(s.label, Path(s.path), s.cutoff_days) for s in sources
        ]
        self._watcher = QFileSystemWatcher(self)
        for src in self._sources:
            if src.path.is_dir():
                self._watcher.addPath(str(src.path))
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        # debounce: directoryChanged が連発すると毎回タイマーが reset され、
        # 沈黙してから DEBOUNCE_MS 後に 1 回だけ emit される。
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(self.DEBOUNCE_MS)
        self._debounce.timeout.connect(self.changed.emit)
        # 「書き込み中で表示を保留中」のファイル群を遅延再走査するためのフォロー
        # アップタイマー (Inbox 表示で 0KB が消えた直後にもう一度見直す)。
        self._followup = QTimer(self)
        self._followup.setSingleShot(True)
        self._followup.setInterval(int(_INCOMPLETE_GRACE_SEC * 1000) + 500)
        self._followup.timeout.connect(self.changed.emit)

    def _on_dir_changed(self, _path: str) -> None:
        self._debounce.start()       # 連続発火中は最後の沈黙でだけ emit
        self._followup.start()       # 書き込み完了直後の追い refresh

    def list_files(self) -> list[InboxFile]:
        """全監視対象フォルダの PDF + 画像ファイルを統合一覧で返す。"""
        return list_inbox_files(self._sources)
