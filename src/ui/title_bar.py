"""Win95 風自作タイトルバー (高密度版・14px)

FramelessWindowHint 下で、Win95 風の細い紺色タイトルバーを自前描画する。
- タイトル文字 (左)
- 最小化 / 最大化 / × ボタン (右、各 14×12px)
- ドラッグでウインドウ移動 (startSystemMove で Wayland 対応)
- ダブルクリックで最大化トグル
- アクティブ / 非アクティブで背景色変化 (QSS の `[inactive=true]` 属性切替)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class TitleBar(QWidget):
    def __init__(self, parent: QWidget, minimal: bool = False) -> None:
        """minimal=True でダイアログ用 (最小化/最大化を出さず × ボタンのみ)。"""
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(14)
        self._minimal = minimal
        # QSS background-color を素の QWidget に効かせるため
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(1)

        # アプリアイコン (Win95 のシステムメニューアイコン位置)。
        # WA_TransparentForMouseEvents でアイコン上からでもドラッグ移動可。
        self.icon_label = QLabel()
        self.icon_label.setObjectName("titleBarIcon")
        self.icon_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        app = QApplication.instance()
        if app is not None:
            pm = app.windowIcon().pixmap(12, 12)
            if not pm.isNull():
                self.icon_label.setPixmap(pm)
        layout.addWidget(self.icon_label)

        self.title_label = QLabel("k-file — 案件ドキュメント作業台")
        self.title_label.setObjectName("titleBarText")
        layout.addWidget(self.title_label, stretch=1)

        # minimal (ダイアログ用) は最小化/最大化を出さず × ボタンのみ
        self.btn_min = None
        self.btn_max = None
        if not minimal:
            self.btn_min = self._make_btn("_", self._on_minimize)
            self.btn_max = self._make_btn("□", self._on_toggle_max)
            layout.addWidget(self.btn_min)
            layout.addWidget(self.btn_max)
        self.btn_close = self._make_btn("✕", self._on_close)
        layout.addWidget(self.btn_close)

        parent.installEventFilter(self)

    def _make_btn(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("titleBarBtn")
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(slot)
        return btn

    def _on_minimize(self) -> None:
        self.window().showMinimized()

    def _on_toggle_max(self) -> None:
        if self.btn_max is None:  # minimal (ダイアログ) では無効
            return
        win = self.window()
        if win.isMaximized():
            win.showNormal()
            self.btn_max.setText("□")
        else:
            win.showMaximized()
            self.btn_max.setText("❐")

    def _on_close(self) -> None:
        self.window().close()

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._minimal and event.button() == Qt.MouseButton.LeftButton:
            self._on_toggle_max()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate):
            inactive = event.type() == QEvent.Type.WindowDeactivate
            self.setProperty("inactive", inactive)
            self.style().unpolish(self)
            self.style().polish(self)
            for w in (self.title_label,):
                w.style().unpolish(w)
                w.style().polish(w)
        return super().eventFilter(watched, event)
