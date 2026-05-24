"""ファイル D&D の MIME 形式と判定ヘルパ。

k-file 内部の D&D では標準 `text/uri-list` に加え、起点を判別するために
`application/x-kfile-source` ("inbox" / "case") を載せる。これで
「投入 (inbox→case)」と「移動 (case→case)」を取り違えない。

外部 (OS のファイルマネージャ等) からの drop は M5/M6 の事件タブ追加で
扱う領域なので、M3 では「起点が k-file 内部」のものだけ受け入れる。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap

KFILE_SOURCE_MIME = "application/x-kfile-source"

SRC_INBOX = "inbox"
SRC_CASE = "case"


def make_drag_pixmap(names: list[str]) -> QPixmap:
    """D&D 中にカーソル横に表示する小さな付箋風 pixmap。
    1 件 → ファイル名、2 件以上 → 「先頭名 他 N 件」。Win95 風の黄色付箋色。"""
    if not names:
        return QPixmap()
    label = names[0] if len(names) == 1 else f"{names[0]}  他 {len(names) - 1} 件"
    font = QFont("MS Gothic", 10)
    fm = QFontMetrics(font)
    pad_x, pad_y = 8, 4
    w = min(fm.horizontalAdvance(label) + pad_x * 2, 400)
    h = fm.height() + pad_y * 2
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor(255, 255, 200))  # 薄黄色 (付箋メモ風)
    p = QPainter(pixmap)
    try:
        p.setFont(font)
        p.setPen(QPen(QColor(0, 0, 0)))
        p.drawRect(0, 0, w - 1, h - 1)
        elided = fm.elidedText(
            label, Qt.TextElideMode.ElideRight, w - pad_x * 2
        )
        p.drawText(pad_x, pad_y + fm.ascent(), elided)
    finally:
        p.end()
    return pixmap


def make_kfile_mime_data(
    source: str, paths: Path | list[Path]
) -> QMimeData:
    """k-file 内部 D&D 用の MIME を組み立てる (uri-list + 起点識別)。

    paths は 1 件 (Path) でも複数件 (list[Path]) でも可。
    """
    if isinstance(paths, Path):
        paths = [paths]
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
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
