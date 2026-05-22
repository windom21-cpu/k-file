"""ペイン見出し (タイトル文字を Win95 彫り込み線で上下から挟む)。

左 INBOX / 中央 参照フォルダ / 右 プレビュー の 3 ペインで共用し、
見出しを上下の彫り込み線 (etched line) で帯状に区切る。
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


def _etched_line() -> QFrame:
    """Win95 彫り込み線 (上 1px 暗 + 下 1px 明、高さ 2px)。"""
    line = QFrame()
    line.setObjectName("etchedLine")
    line.setFixedHeight(2)
    return line


class PaneHeader(QWidget):
    """ペイン上端の見出し帯。見出しを上下の彫り込み線で挟む。"""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 上端の彫り込み線
        layout.addWidget(_etched_line())

        self.label = QLabel(title)
        self.label.setObjectName("paneHeader")
        layout.addWidget(self.label)

        # 下端の彫り込み線
        layout.addWidget(_etched_line())

        # 彫り込み線の下に余白を確保し、本文 (タブバー/一覧) と
        # 線が密着して区切りが埋もれないようにする。3 ペイン共通。
        layout.addSpacing(3)
