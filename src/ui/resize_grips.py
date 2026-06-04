"""Frameless ウインドウ用 リサイズグリップ (全辺・全角対応)

QSizeGrip は右下角しか掴めない。Win95 風 Frameless ウインドウの見た目を
保ったまま、左/右/下の辺と左下/右下の隅からもリサイズできるよう、
ウインドウ縁に「透明な細いグリップ widget」を重ねる。

- 各グリップは専用のリサイズカーソル (↔ / ↕ / ⤡ / ⤢) を表示
- 左ドラッグで `windowHandle().startSystemResize(edge)` を発火
  (title_bar の startSystemMove と同じ native 流儀。Win / Wayland 両対応)
- native API が使えない環境ではフレームジオメトリを直接いじる手動リサイズに
  フォールバック

上辺と左上隅は TitleBar が自前で処理する (× ボタンに被せないため、ここでは
左/右/下の辺と左下/右下の隅のみを担当する)。親ウインドウの resizeEvent から
`reposition()` を呼んで縁に追従させる。
"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QCursor, QMouseEvent, QPainter
from PySide6.QtWidgets import QWidget

# 辺グリップの厚み (px) と 隅グリップの一辺 (px)。
_MARGIN = 6
_CORNER = 16

# Win95/98 風 raised ウインドウ外枠の色 (古典 3D システムカラー)。
# 本物の窓枠は「外側 1px + 内側 1px」の 2 段ベベルで、片側 1 色のベタ塗りでは
# なく 4 色で構成される。これが「ボタン」ではなく「窓」に見える肝。
#   上/左 = 明: 外側 3DLIGHT (#DFDFDF) → 内側 ハイライト白 (#FFFFFF)
#   下/右 = 暗: 外側 濃影 黒 (#000000) → 内側 影灰 (#808080)
_FRAME_LIGHT = QColor("#DFDFDF")     # 外側・上左 (3DLIGHT)
_FRAME_HILIGHT = QColor("#FFFFFF")   # 内側・上左 (BTNHIGHLIGHT)
_FRAME_DKSHADOW = QColor("#000000")  # 外側・下右 (3DDKSHADOW)
_FRAME_SHADOW = QColor("#808080")    # 内側・下右 (BTNSHADOW)
_FRAME_WIDTH = 2                     # 片側の総厚 (= 外側 1px + 内側 1px)


class _WindowFrame(QWidget):
    """ウインドウ全体に Win95 風の raised 外枠だけを描く透明オーバーレイ。

    Frameless ウインドウは OS の枠が無く、隣接ウインドウやデスクトップとの
    境界が見えない (特にプレビュー右端で顕著)。最前面に縁だけを描き、中身は
    透過 + マウスも透過させて操作・リサイズを一切妨げない。
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        # マウスは下のグリップ/中身へ素通り。背景も描かず縁だけ paint。
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event) -> None:
        # drawLine は High-DPI で端の device pixel を取りこぼすため fillRect で
        # 1px 帯を 2 段重ねる (論理矩形を device pixel まで正確に塗り、DPR 2 でも
        # 端が欠けない)。本物の Win95 窓枠と同じ「外側 1px + 内側 1px」の raised
        # 2 段ベベル。上左 (明) を先・下右 (暗) を後に塗るので、右上/左下の隅は
        # 暗が明に勝ち、ボタンではなく「窓」に見える raised の陰影になる。
        p = QPainter(self)
        w, h = self.width(), self.height()
        # --- 外側リング (最端 1px): 上左 = 3DLIGHT, 下右 = 黒 ---
        p.fillRect(0, 0, w, 1, _FRAME_LIGHT)           # 上
        p.fillRect(0, 0, 1, h, _FRAME_LIGHT)           # 左
        p.fillRect(0, h - 1, w, 1, _FRAME_DKSHADOW)    # 下
        p.fillRect(w - 1, 0, 1, h, _FRAME_DKSHADOW)    # 右
        # --- 内側リング (端から 1px 内): 上左 = 白, 下右 = 影灰 ---
        p.fillRect(1, 1, w - 2, 1, _FRAME_HILIGHT)     # 上
        p.fillRect(1, 1, 1, h - 2, _FRAME_HILIGHT)     # 左
        p.fillRect(1, h - 2, w - 2, 1, _FRAME_SHADOW)  # 下
        p.fillRect(w - 2, 1, 1, h - 2, _FRAME_SHADOW)  # 右
        p.end()


class _ResizeGrip(QWidget):
    """ウインドウ縁に重ねる透明なリサイズハンドル。"""

    def __init__(self, parent: QWidget, edges: Qt.Edge, cursor: Qt.CursorShape) -> None:
        super().__init__(parent)
        self._edges = edges
        self.setCursor(QCursor(cursor))
        # 背景を描かない = 下のペイン内容がそのまま透けて見える。マウスイベント
        # だけは受け取る (WA_TransparentForMouseEvents は付けない)。
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # 手動リサイズ フォールバック用の状態。
        self._manual = False
        self._press_global = None
        self._start_geom: QRect | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        win = self.window()
        if win.isMaximized():
            return  # 最大化中はリサイズしない
        handle = win.windowHandle()
        if handle is not None and handle.startSystemResize(self._edges):
            event.accept()
            return
        # native が使えない環境 (一部 platform / offscreen): 手動リサイズへ。
        self._manual = True
        self._press_global = event.globalPosition().toPoint()
        self._start_geom = win.geometry()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._manual or self._start_geom is None:
            super().mouseMoveEvent(event)
            return
        win = self.window()
        delta = event.globalPosition().toPoint() - self._press_global
        g = QRect(self._start_geom)
        min_w = max(win.minimumWidth(), 1)
        min_h = max(win.minimumHeight(), 1)
        if self._edges & Qt.Edge.LeftEdge:
            g.setLeft(min(g.left() + delta.x(), g.right() - min_w))
        if self._edges & Qt.Edge.RightEdge:
            g.setRight(max(g.right() + delta.x(), g.left() + min_w))
        if self._edges & Qt.Edge.TopEdge:
            g.setTop(min(g.top() + delta.y(), g.bottom() - min_h))
        if self._edges & Qt.Edge.BottomEdge:
            g.setBottom(max(g.bottom() + delta.y(), g.top() + min_h))
        win.setGeometry(g)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._manual = False
        self._start_geom = None
        super().mouseReleaseEvent(event)


class ResizeGrips:
    """Frameless ウインドウに左/右/下の辺 + 左下/右下の隅グリップを取り付ける。

    上辺・左上隅は TitleBar 側で処理するため、`top_inset` (= タイトルバー高さ)
    の分だけ左右辺グリップを下げ、タイトルバーや × ボタンに被らないようにする。
    """

    def __init__(self, window: QWidget, top_inset: int = 0) -> None:
        self._window = window
        self._top_inset = top_inset
        # ウインドウ全体の外枠 (常時表示・最前面・マウス透過)。
        self.frame = _WindowFrame(window)
        self.left = _ResizeGrip(
            window, Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor
        )
        self.right = _ResizeGrip(
            window, Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor
        )
        self.bottom = _ResizeGrip(
            window, Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor
        )
        self.bottom_left = _ResizeGrip(
            window,
            Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
            Qt.CursorShape.SizeBDiagCursor,  # "/" 方向
        )
        self.bottom_right = _ResizeGrip(
            window,
            Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
            Qt.CursorShape.SizeFDiagCursor,  # "\" 方向
        )
        self._grips = [
            self.left, self.right, self.bottom,
            self.bottom_left, self.bottom_right,
        ]
        self.reposition()

    def reposition(self) -> None:
        """ウインドウ縁に沿ってグリップ・外枠を再配置 (resizeEvent から呼ぶ)。"""
        w = self._window.width()
        h = self._window.height()
        t = self._top_inset
        m, c = _MARGIN, _CORNER
        # 外枠はウインドウ全体を覆う (最大化中も縁を見せる)。
        self.frame.setGeometry(0, 0, w, h)
        self.frame.raise_()
        # 最大化中はリサイズ不可なのでグリップは隠す (カーソルの誤表示も防ぐ)。
        if self._window.isMaximized():
            for g in self._grips:
                g.setVisible(False)
            return
        side_h = max(h - t - c, 0)
        self.left.setGeometry(0, t, m, side_h)
        self.right.setGeometry(w - m, t, m, side_h)
        self.bottom.setGeometry(c, h - m, max(w - 2 * c, 0), m)
        self.bottom_left.setGeometry(0, h - c, c, c)
        self.bottom_right.setGeometry(w - c, h - c, c, c)
        for g in self._grips:
            g.setVisible(True)
            g.raise_()
        # グリップは透過なので外枠より上に来ても縁は見えるが、確実に最前面へ。
        self.frame.raise_()
