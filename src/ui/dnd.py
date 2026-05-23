"""ファイル D&D の MIME 形式と判定ヘルパ。

k-file 内部の D&D では標準 `text/uri-list` に加え、起点を判別するために
`application/x-kfile-source` ("inbox" / "case") を載せる。これで
「投入 (inbox→case)」と「移動 (case→case)」を取り違えない。

外部 (OS のファイルマネージャ等) からの drop は M5/M6 の事件タブ追加で
扱う領域なので、M3 では「起点が k-file 内部」のものだけ受け入れる。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl

KFILE_SOURCE_MIME = "application/x-kfile-source"

SRC_INBOX = "inbox"
SRC_CASE = "case"


def make_kfile_mime_data(source: str, path: Path) -> QMimeData:
    """k-file 内部 D&D 用の MIME を組み立てる (uri-list + 起点識別)。"""
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(path))])
    data.setData(KFILE_SOURCE_MIME, source.encode("utf-8"))
    return data


def kfile_source_of(mime: QMimeData) -> str | None:
    """MIME から起点ラベル ("inbox" / "case") を取り出す。なければ None。"""
    if mime.hasFormat(KFILE_SOURCE_MIME):
        return bytes(mime.data(KFILE_SOURCE_MIME)).decode("utf-8")
    return None


def kfile_local_paths(mime: QMimeData) -> list[Path]:
    """MIME から file:// URL のローカルパスのみを抜き出す。"""
    return [
        Path(url.toLocalFile())
        for url in mime.urls()
        if url.isLocalFile()
    ]
