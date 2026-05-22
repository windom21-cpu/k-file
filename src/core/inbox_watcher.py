"""Inbox 監視対象フォルダの実ファイル走査 + 変更検知。

scan / Desktop / 作業 等の監視対象フォルダを QFileSystemWatcher で見張り、
ファイルの増減があれば changed シグナルを出す。一覧は PDF + 画像のみに絞る。

core 層だが GUI 非依存の QtCore (QFileSystemWatcher / QObject) には依存する。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal

# Inbox に表示する拡張子 (PDF + 画像)。.txt / .lnk / フォルダ等は非表示。
INBOX_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@dataclass
class InboxFile:
    """Inbox 監視対象フォルダ内の 1 ファイル。"""

    name: str
    path: Path
    source: str   # 出所ラベル ("scan" / "Desktop" / "作業" 等)
    mtime: float
    size: int


class InboxWatcher(QObject):
    """監視対象フォルダ群を見張り、変更時に changed を出す。"""

    changed = Signal()

    def __init__(
        self,
        sources: list[tuple[str, Path]],
        parent: QObject | None = None,
    ) -> None:
        """sources = [(出所ラベル, フォルダパス), ...]。"""
        super().__init__(parent)
        self._sources = [(label, Path(p)) for label, p in sources]
        self._watcher = QFileSystemWatcher(self)
        for _label, path in self._sources:
            if path.is_dir():
                self._watcher.addPath(str(path))
        self._watcher.directoryChanged.connect(self._on_dir_changed)

    def _on_dir_changed(self, _path: str) -> None:
        self.changed.emit()

    def list_files(self) -> list[InboxFile]:
        """全監視対象フォルダの PDF + 画像ファイルを統合一覧で返す。"""
        out: list[InboxFile] = []
        for label, path in self._sources:
            if not path.is_dir():
                continue
            try:
                children = list(path.iterdir())
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
                out.append(
                    InboxFile(p.name, p, label, st.st_mtime, st.st_size)
                )
        return out
