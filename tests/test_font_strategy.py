"""文字描画モード (ガタガタ/中間/なめらか) のロジックテスト (GUI 非依存)。

2026-06-01 追加。モニタ解像度の好みで手動切替する機能。サイズ/レイアウトは
変えず QFont.StyleStrategy だけを 3 段階で切り替える。ここでは「3 モードが
別戦略になっていること」「各戦略のフラグが期待どおり」「set/get の往復」を固定。
widget への適用 (apply_bitmap_font_strategy) は GUI 層なので実機/手動確認に委ねる。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QFont  # noqa: E402

from src.ui._font_strategy import (  # noqa: E402
    FONT_MODE_BITMAP,
    FONT_MODE_OUTLINE,
    FONT_MODE_SMOOTH,
    _STRATEGIES,
    get_font_render_mode,
    set_font_render_mode,
)

_S = QFont.StyleStrategy


def _flags(mode: str) -> int:
    return int(_STRATEGIES[mode].value)


def test_three_modes_are_distinct():
    vals = {_flags(m) for m in (FONT_MODE_BITMAP, FONT_MODE_OUTLINE, FONT_MODE_SMOOTH)}
    assert len(vals) == 3   # 3 モードとも別戦略


def test_bitmap_mode_flags():
    f = _flags(FONT_MODE_BITMAP)
    assert f & _S.PreferBitmap.value
    assert f & _S.NoAntialias.value


def test_outline_mode_is_no_antialias_outline():
    # 中間 = アウトライン字形だが AA 無し (ビットマップではない)
    f = _flags(FONT_MODE_OUTLINE)
    assert f & _S.PreferOutline.value
    assert f & _S.NoAntialias.value
    assert not (f & _S.PreferBitmap.value)


def test_smooth_mode_is_antialiased_outline():
    # なめらか = アウトライン + AA。NoAntialias / Bitmap は立っていない
    f = _flags(FONT_MODE_SMOOTH)
    assert f & _S.PreferAntialias.value
    assert not (f & _S.NoAntialias.value)
    assert not (f & _S.PreferBitmap.value)


def test_set_get_roundtrip():
    try:
        set_font_render_mode(FONT_MODE_SMOOTH)
        assert get_font_render_mode() == FONT_MODE_SMOOTH
        set_font_render_mode(FONT_MODE_OUTLINE)
        assert get_font_render_mode() == FONT_MODE_OUTLINE
    finally:
        set_font_render_mode(FONT_MODE_BITMAP)   # 既定へ戻す (他テストへの影響回避)


def test_invalid_mode_is_ignored():
    set_font_render_mode(FONT_MODE_BITMAP)
    set_font_render_mode("nonsense")
    assert get_font_render_mode() == FONT_MODE_BITMAP
