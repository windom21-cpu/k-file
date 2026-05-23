"""ウィンドウ下部のファンクションキーバー (DOS ファイラー風)。

F1〜F12 を等幅で並べ、各セルに役割テキストを表示。キー押下・セルクリック
の両方で発火 (機能本体は MainWindow が結線)。未実装の役割は disabled
表示で「枠」だけ見せ、将来追加していく動機にする。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class FunctionKeysBar(QWidget):
    """F1〜F12 のラベル付きセル 12 個を横に並べる薄いバー。"""

    keyTriggered = Signal(int)  # 1..12 — セルクリック時に発火

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("fnKeysBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(1)
        self._cells: list[QPushButton] = []
        for i in range(1, 13):
            cell = QPushButton(f"F{i}")
            cell.setObjectName("fnKeyCell")
            cell.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            cell.setEnabled(False)  # 初期は枠だけ、set_slot で有効化
            cell.clicked.connect(lambda _=False, k=i: self.keyTriggered.emit(k))
            lay.addWidget(cell, stretch=1)
            self._cells.append(cell)

    def set_slot(
        self,
        fn: int,
        label: str,
        *,
        enabled: bool = True,
        tooltip: str = "",
    ) -> None:
        """`fn` 番セル (1..12) のラベル・有効状態・ツールチップを設定。"""
        if not 1 <= fn <= 12:
            return
        cell = self._cells[fn - 1]
        text = f"F{fn} {label}".rstrip()
        cell.setText(text)
        cell.setEnabled(enabled)
        if tooltip:
            cell.setToolTip(tooltip)
