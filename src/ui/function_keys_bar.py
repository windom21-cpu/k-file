"""ウィンドウ下部のファンクションキーバー (DOS ファイラー風)。

F1〜F12 を等幅で並べ、各セルに役割テキストを表示。キー押下・セルクリック
の両方で発火 (機能本体は MainWindow が結線)。未実装の役割は disabled
表示で「枠」だけ見せ、将来追加していく動機にする。

2 段構成: 通常段 (素の F キー) と Shift 段 (Shift+F キー)。Shift 段に 1 つでも
役割が登録されていれば、Shift を押している間だけバー全体が Shift 段の表示に
切り替わる (DOS ファイラーと同じ作法)。Shift 段が空なら切り替えない
(Shift+クリックの複数選択のたびにバーがちらつくのを避ける)。
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


@dataclass
class _Slot:
    label: str = ""
    enabled: bool = False
    tooltip: str = ""


class FunctionKeysBar(QWidget):
    """F1〜F12 のラベル付きセル 12 個を横に並べる薄いバー。"""

    # (1..12, Shift 段か) — セルクリック時に発火
    keyTriggered = Signal(int, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("fnKeysBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        # 上に 5px の余白: 中央ペインの「− 削除」ボタンと密着するのを避け、
        # 「下端の操作領域」として視覚的に分離する。下は 1px のまま。
        lay.setContentsMargins(2, 5, 2, 1)
        lay.setSpacing(1)
        self._cells: list[QPushButton] = []
        self._plain: list[_Slot] = [_Slot() for _ in range(12)]
        self._shift: list[_Slot] = [_Slot() for _ in range(12)]
        self._shift_active = False
        for i in range(1, 13):
            cell = QPushButton(f"F{i}")
            cell.setObjectName("fnKeyCell")
            cell.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            cell.setEnabled(False)  # 初期は枠だけ、set_slot で有効化
            cell.clicked.connect(
                lambda _=False, k=i: self.keyTriggered.emit(k, self._shift_active)
            )
            lay.addWidget(cell, stretch=1)
            self._cells.append(cell)

    def set_slot(
        self,
        fn: int,
        label: str,
        *,
        enabled: bool = True,
        tooltip: str = "",
        shift: bool = False,
    ) -> None:
        """`fn` 番セル (1..12) のラベル・有効状態・ツールチップを設定。

        `shift=True` で Shift 段 (Shift を押している間だけ見える) に登録する。
        """
        if not 1 <= fn <= 12:
            return
        layer = self._shift if shift else self._plain
        layer[fn - 1] = _Slot(label=label, enabled=enabled, tooltip=tooltip)
        self._render(fn)

    def clear_slot(self, fn: int, *, shift: bool = False) -> None:
        """`fn` 番セルを未割当 (枠だけ) に戻す。"""
        if not 1 <= fn <= 12:
            return
        layer = self._shift if shift else self._plain
        layer[fn - 1] = _Slot()
        if shift and not self.has_shift_layer():
            self._shift_active = False
            self._render_all()
        else:
            self._render(fn)

    def has_shift_layer(self) -> bool:
        return any(s.label for s in self._shift)

    def set_shift_active(self, active: bool) -> None:
        """Shift 押下状態を反映。Shift 段が空なら常に通常段のまま。"""
        active = bool(active) and self.has_shift_layer()
        if active == self._shift_active:
            return
        self._shift_active = active
        self._render_all()

    def shift_active(self) -> bool:
        return self._shift_active

    def _render_all(self) -> None:
        for fn in range(1, 13):
            self._render(fn)

    def _render(self, fn: int) -> None:
        layer = self._shift if self._shift_active else self._plain
        slot = layer[fn - 1]
        cell = self._cells[fn - 1]
        cell.setText(f"F{fn} {slot.label}".rstrip())
        cell.setEnabled(slot.enabled)
        cell.setToolTip(slot.tooltip)
