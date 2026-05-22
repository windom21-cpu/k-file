"""右 プレビューペイン

M1 はプレースホルダのみ。M2 で QPdfView (PDF) + QLabel/QPixmap (画像) を実装。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from src.ui.pane_header import PaneHeader


class PreviewPane(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # spacing=0: 見出し下の余白は PaneHeader に内蔵済み (3 ペイン共通)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 上端: ペインタイトル (見出し + 彫り込み下線。3 ペイン共通)
        outer.addWidget(PaneHeader("プレビュー"))

        placeholder = QLabel("(PDF / 画像プレビューは M2 で実装)")
        placeholder.setObjectName("previewPlaceholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        outer.addWidget(placeholder, stretch=1)

    def show_file(self, path: str) -> None:
        """M2 で実装予定。"""
        pass
