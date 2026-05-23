"""Inbox と参照フォルダの間に置く縦長コマンドストリップ (DOS ファイラー風)。

Norton Commander / Total Commander の中央コマンド列に倣い、頻用操作を縦に
小ボタンで並べる。マウス派の代替操作 + 将来の拡張余地。

最初は最小構成:
  ▶▶  Inbox 選択 → アクティブなサブフォルダへ投入
  ✕   Inbox 選択を「無視」(表示から除外、実ファイルは触らない) トグル
  ↶   Undo (M4 で実装予定、現状 disabled)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget


class CommandStrip(QWidget):
    """Inbox と参照フォルダの間に挟む細い縦バー。"""

    STRIP_WIDTH = 28  # ペイン外から見える視覚幅 (動的レイアウト計算で参照)

    injectClicked = Signal()
    ignoreClicked = Signal()
    undoClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandStrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(self.STRIP_WIDTH)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 4, 2, 4)
        lay.setSpacing(2)
        # 上下に等しい伸縮スペーサを入れてボタン群を縦方向中央に
        lay.addStretch(1)

        self.btn_inject = self._make(
            "▶▶",
            "Inbox の選択ファイルを\nアクティブなサブフォルダへ投入\n(現状はダミー、M3 で実投入)",
        )
        self.btn_inject.clicked.connect(self.injectClicked.emit)
        lay.addWidget(self.btn_inject)

        self.btn_ignore = self._make(
            "✕",
            "Inbox の選択ファイルを\n表示から除外 / 解除 (実ファイルは触らない)",
        )
        self.btn_ignore.clicked.connect(self.ignoreClicked.emit)
        lay.addWidget(self.btn_ignore)

        self.btn_undo = self._make("↶", "Undo (M4 で実装予定)")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undoClicked.emit)
        lay.addWidget(self.btn_undo)

        lay.addStretch(1)

    def _make(self, label: str, tooltip: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("stripBtn")
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setToolTip(tooltip)
        return btn
