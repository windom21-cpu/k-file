"""フォント描画モード (ガタガタ / 中間 / なめらか) を widget tree に適用する helper。

QSS で font-family を指定すると Qt が QFont.StyleStrategy をリセットするため、
widget tree を歩いて各 widget の font に明示的に再付与する必要がある。
MainWindow と SettingsDialog / AboutDialog 等のサブダイアログ共通で使う。

描画モードは「同じフォント・同じサイズのまま StyleStrategy だけ」を切り替える
(サイズ/レイアウトは一切変えない)。モニタ解像度の好みで手動切替する用途:
- ガタガタ (bitmap): MS Gothic 埋め込みビットマップ。1080p のドット感レトロ。既定。
- 中間 (outline)  : アウトライン字形を AA 無しで描画。ビットマップ固定の崩れを避けつつ
                    エッジは硬い (滲ませない)。
- なめらか (smooth): アウトライン + アンチエイリアス。4K スケーリング向け。
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QToolTip, QWidget

FONT_MODE_BITMAP = "bitmap"     # ガタガタ
FONT_MODE_OUTLINE = "outline"   # 中間
FONT_MODE_SMOOTH = "smooth"     # なめらか

# 表示用ラベル (ステータスバー通知等)
FONT_MODE_LABELS = {
    FONT_MODE_BITMAP: "ガタガタ",
    FONT_MODE_OUTLINE: "中間",
    FONT_MODE_SMOOTH: "なめらか",
}
# メニューに並べる順 (mode, ラベル)
FONT_MODE_MENU_ITEMS = [
    (FONT_MODE_BITMAP, "ガタガタ"),
    (FONT_MODE_OUTLINE, "中間"),
    (FONT_MODE_SMOOTH, "なめらか"),
]

_S = QFont.StyleStrategy
_STRATEGIES = {
    # 埋め込みビットマップ + AA オフ (従来の既定 = レトロのドット感)
    FONT_MODE_BITMAP: _S(_S.PreferBitmap | _S.NoAntialias),
    # アウトライン字形だが AA 無し (硬いエッジ・滲ませない中間)
    FONT_MODE_OUTLINE: _S(_S.PreferOutline | _S.NoAntialias),
    # アウトライン + アンチエイリアス (滑らか)
    FONT_MODE_SMOOTH: _S(_S.PreferOutline | _S.PreferAntialias),
}

# 現在の描画モード (起動時に MainWindow が kfile.db から復元して set する)。
_current_mode = FONT_MODE_BITMAP


def set_font_render_mode(mode: str) -> None:
    """現在の描画モードを切り替える (未知の値は無視して既定維持)。

    実際の widget への反映は `apply_bitmap_font_strategy` / `reapply_font_render_mode`
    が行う。この関数は「次に apply される戦略」を決めるだけ。
    """
    global _current_mode
    if mode in _STRATEGIES:
        _current_mode = mode


def get_font_render_mode() -> str:
    return _current_mode


def _strategy() -> QFont.StyleStrategy:
    return _STRATEGIES[_current_mode]


def apply_bitmap_font_strategy(
    root: QWidget, point_size: int | None = None
) -> None:
    """root とその全子孫 widget の font に、現在の描画モードの StyleStrategy を再付与。

    QSS 適用後の widget tree に対して呼ぶ。サブダイアログを開く時にも (新規 widget
    tree なので) 呼び直す必要がある。`point_size` を指定すると同時にフォントサイズも
    上書きする (ダイアログを本体より一回り小さい 9pt にしたい時用)。

    関数名は歴史的経緯で bitmap だが、実際は `set_font_render_mode` で選んだモード
    (ガタガタ / 中間 / なめらか) を適用する。
    """
    strategy = _strategy()
    targets = [root] + root.findChildren(QWidget)
    for w in targets:
        f = w.font()
        f.setStyleStrategy(strategy)
        if point_size is not None:
            f.setPointSize(point_size)
        w.setFont(f)


def tooltip_font() -> QFont:
    """ツールチップ用フォント (MS Gothic 12pt + 現在の描画モード戦略)。

    ツールチップは top-level の別 widget で QSS の `*` 継承外なので、main.py /
    モード切替時に QToolTip.setFont へ渡して本体と見え方を揃える。
    """
    f = QFont("MS Gothic", 12)
    f.setStyleStrategy(_strategy())
    return f


def reapply_font_render_mode() -> None:
    """モード変更後に、開いている全 top-level widget へ戦略を再適用する。

    point_size は触らない (各 widget の既存サイズ = ダイアログ 9pt 等を保つ)。
    ツールチップフォントも合わせて更新する。
    """
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        apply_bitmap_font_strategy(w)
    QToolTip.setFont(tooltip_font())
