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

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal

# Inbox に表示する拡張子 (PDF + 画像)。.txt / .lnk / フォルダ等は非表示。
INBOX_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


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
    """Inbox 監視対象フォルダ内の 1 ファイル。"""

    name: str
    path: Path
    source: str   # 出所ラベル ("scan" / "Desktop" / "作業" 等)
    mtime: float
    size: int


def list_inbox_files(
    sources: list[InboxSource], now: float | None = None
) -> list[InboxFile]:
    """純粋関数として list_files を切り出し (Qt 非依存・テスト可能)。

    ソースごとの cutoff_days があれば、現在時刻からその日数より古い更新日時の
    ファイルを除外する。`now` を渡せば現在時刻を上書きできる (テスト用)。
    """
    base = now if now is not None else time.time()
    out: list[InboxFile] = []
    for src in sources:
        if not src.path.is_dir():
            continue
        cutoff_ts = (
            base - src.cutoff_days * 86400 if src.cutoff_days is not None else None
        )
        try:
            children = list(src.path.iterdir())
        except OSError:
            continue
        for p in children:
            if not p.is_file():
                continue
            if p.suffix.lower() not in INBOX_EXTENSIONS:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if cutoff_ts is not None and st.st_mtime < cutoff_ts:
                continue   # 古いファイルは表示しない
            out.append(
                InboxFile(p.name, p, src.label, st.st_mtime, st.st_size)
            )
    return out


class InboxWatcher(QObject):
    """監視対象フォルダ群を見張り、変更時に changed を出す。"""

    changed = Signal()

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

    def _on_dir_changed(self, _path: str) -> None:
        self.changed.emit()

    def list_files(self) -> list[InboxFile]:
        """全監視対象フォルダの PDF + 画像ファイルを統合一覧で返す。"""
        return list_inbox_files(self._sources)
