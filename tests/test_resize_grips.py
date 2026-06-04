"""Frameless ウインドウのリサイズグリップ (全辺・全角) のテスト。

2026-06-04 追加。リサイズが右下角 (QSizeGrip) しか掴めなかったのを、左/右/下の
辺 + 左下/右下の隅 (ResizeGrips) と 上辺/左上隅 (TitleBar) で全周対応にした。
ここでは GUI に依存しすぎない範囲で「縁に沿った配置計算」「各グリップの掴む辺と
カーソル」「タイトルバー上辺帯の辺判定」を固定する。実際のドラッグ挙動
(startSystemResize) は platform 依存なので実機/手動確認に委ねる。
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from src.ui.resize_grips import (  # noqa: E402
    ResizeGrips,
    _CORNER,
    _MARGIN,
    _WindowFrame,
)
from src.ui.title_bar import TitleBar, _RESIZE_MARGIN  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_reposition_places_grips_along_edges():
    _app()
    host = QWidget()
    host.resize(1000, 700)
    host.show()
    assert not host.isMaximized()
    g = ResizeGrips(host, top_inset=22)
    g.reposition()

    m, c, t = _MARGIN, _CORNER, 22
    w, h = host.width(), host.height()
    # 左右辺はタイトルバー下 (y=t) から下隅の手前まで。
    assert g.left.geometry().getRect() == (0, t, m, h - t - c)
    assert g.right.geometry().getRect() == (w - m, t, m, h - t - c)
    # 下辺は左右の隅を除いた幅。
    assert g.bottom.geometry().getRect() == (c, h - m, w - 2 * c, m)
    # 左下 / 右下の隅。
    assert g.bottom_left.geometry().getRect() == (0, h - c, c, c)
    assert g.bottom_right.geometry().getRect() == (w - c, h - c, c, c)
    assert all(x.isVisible() for x in g._grips)


def test_grip_edges_and_cursors():
    _app()
    host = QWidget()
    g = ResizeGrips(host, top_inset=22)
    E, C = Qt.Edge, Qt.CursorShape
    assert g.left._edges == E.LeftEdge
    assert g.right._edges == E.RightEdge
    assert g.bottom._edges == E.BottomEdge
    assert g.bottom_left._edges == (E.BottomEdge | E.LeftEdge)
    assert g.bottom_right._edges == (E.BottomEdge | E.RightEdge)
    assert g.left.cursor().shape() == C.SizeHorCursor
    assert g.bottom.cursor().shape() == C.SizeVerCursor
    assert g.bottom_left.cursor().shape() == C.SizeBDiagCursor   # "/"
    assert g.bottom_right.cursor().shape() == C.SizeFDiagCursor  # "\\"


def test_reposition_hides_grips_when_maximized():
    _app()
    host = QWidget()
    host.resize(800, 600)
    host.showMaximized()
    g = ResizeGrips(host, top_inset=22)
    g.reposition()
    if host.isMaximized():  # offscreen でも基本 True になる
        assert all(not x.isVisible() for x in g._grips)


def test_window_frame_created_and_mouse_transparent():
    _app()
    host = QWidget()
    g = ResizeGrips(host, top_inset=22)
    assert isinstance(g.frame, _WindowFrame)
    # マウス透過 = グリップ/中身の操作・リサイズを妨げない。
    assert g.frame.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_window_frame_paints_bevel_border():
    """外枠が本物の Win95 窓枠と同じ「2 段 4 色」の raised bevel を端まで塗ること。

    上/左 = 外側 3DLIGHT(#DFDFDF) → 内側 白(#FFFFFF)、
    下/右 = 外側 黒(#000000) → 内側 影灰(#808080)。
    High-DPI (DPR=2) でも端の device pixel が欠けないことを確認する
    (drawLine ではなく fillRect で塗る根拠)。
    """
    _app()
    host = QWidget()
    host.resize(120, 90)
    host.setStyleSheet("background:#C0C0C0;")
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    fr = _WindowFrame(host)
    fr.setGeometry(0, 0, 120, 90)
    fr.show()
    host.show()
    img = host.grab().toImage()
    dpr = img.width() / 120.0

    def lpx(lx, ly):  # 論理座標で読む (DPR 吸収)
        c = img.pixelColor(int(lx * dpr), int(ly * dpr))
        return (c.red(), c.green(), c.blue())

    # 上/左 = 明 (外側 3DLIGHT → 内側 白) の 2 段。
    assert lpx(0, 45) == (223, 223, 223)    # 左辺 外側 = 3DLIGHT
    assert lpx(1, 45) == (255, 255, 255)    # 左辺 内側 = 白
    assert lpx(60, 0) == (223, 223, 223)    # 上辺 外側 = 3DLIGHT
    assert lpx(60, 1) == (255, 255, 255)    # 上辺 内側 = 白
    # 下/右 = 暗 (外側 黒 → 内側 影灰) の 2 段。端まで塗れている。
    assert lpx(119, 45) == (0, 0, 0)        # 右辺 最端 = 黒
    assert lpx(118, 45) == (128, 128, 128)  # 右辺 内側 = 影灰
    assert lpx(60, 89) == (0, 0, 0)         # 下辺 最端 = 黒
    assert lpx(60, 88) == (128, 128, 128)   # 下辺 内側 = 影灰
    assert lpx(60, 45) == (192, 192, 192)   # 中央 = 枠なし (背景がそのまま)


def test_titlebar_top_edge_detection():
    _app()
    host = QWidget()
    host.resize(400, 300)
    tb = TitleBar(host)
    tb.resize(400, 22)
    E = Qt.Edge
    margin = _RESIZE_MARGIN
    # 上辺帯の内側: 中央 = 上辺のみ、左端 = +Left、右端 = +Right。
    assert tb._resize_edges(QPoint(200, 1)) == E.TopEdge
    assert tb._resize_edges(QPoint(1, 1)) == (E.TopEdge | E.LeftEdge)
    assert tb._resize_edges(QPoint(tb.width() - 1, 1)) == (E.TopEdge | E.RightEdge)
    # 帯の外 (= ここを掴むと移動): None。
    assert tb._resize_edges(QPoint(200, margin + 5)) is None
