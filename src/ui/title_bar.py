"""Win95 風自作タイトルバー (高密度版・14px)

FramelessWindowHint 下で、Win95 風の細い紺色タイトルバーを自前描画する。
- タイトル文字 (左)
- 最小化 / 最大化 / × ボタン (右、各 14×12px)
- ドラッグでウインドウ移動 (startSystemMove で Wayland 対応)
- 上端 _RESIZE_MARGIN px は「上辺リサイズ」帯 (左上隅 / 右上隅も判定)。
  ResizeGrips が担当する上辺・左上隅をここで補う (× ボタンに overlay を
  被せないため、上側だけタイトルバー自身がリサイズを処理する)
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

# 上辺リサイズ帯の厚み (px)。resize_grips._MARGIN と揃える。
_RESIZE_MARGIN = 6


class TitleBar(QWidget):
    def __init__(self, parent: QWidget, minimal: bool = False) -> None:
        """minimal=True でダイアログ用 (最小化/最大化を出さず × ボタンのみ)。"""
        super().__init__(parent)
        self.setObjectName("titleBar")
        # メニューバーと高さを揃える (22px)。中身のボタンは QSS 側で 18px。
        self.setFixedHeight(22)
        self._minimal = minimal
        # QSS background-color を素の QWidget に効かせるため
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 上辺リサイズ帯にカーソルを出すためホバー move を受け取る。
        self.setMouseTracking(True)

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

        self.title_label = QLabel("K-FILE")
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

    def _resize_edges(self, pos) -> Qt.Edge | None:
        """ホバー位置が上辺リサイズ帯なら掴む辺を返す (それ以外は None)。"""
        if pos.y() > _RESIZE_MARGIN:
            return None
        edges = Qt.Edge.TopEdge
        if pos.x() <= _RESIZE_MARGIN:
            edges = edges | Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - _RESIZE_MARGIN:
            edges = edges | Qt.Edge.RightEdge
        return edges

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            handle = win.windowHandle()
            if handle is not None:
                # 上端帯ならリサイズ、それ以外はウインドウ移動。
                edges = None if win.isMaximized() else self._resize_edges(
                    event.position().toPoint()
                )
                if edges is not None and handle.startSystemResize(edges):
                    event.accept()
                    return
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # ボタン非押下時のホバーで上辺リサイズカーソルを出す。
        if (
            event.buttons() == Qt.MouseButton.NoButton
            and not self.window().isMaximized()
        ):
            edges = self._resize_edges(event.position().toPoint())
            if edges is None:
                self.unsetCursor()
            elif edges & Qt.Edge.LeftEdge:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)   # 左上 "\"
            elif edges & Qt.Edge.RightEdge:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)   # 右上 "/"
            else:
                self.setCursor(Qt.CursorShape.SizeVerCursor)     # 上辺 ↕
        super().mouseMoveEvent(event)

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
