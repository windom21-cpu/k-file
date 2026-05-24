"""フォント描画戦略 (PreferBitmap + NoAntialias) を widget tree に適用する helper。

QSS で font-family を指定すると Qt が QFont.StyleStrategy をリセットするため、
widget tree を歩いて各 widget の font に明示的に再付与する必要がある。
MainWindow と SettingsDialog / AboutDialog 等のサブダイアログ共通で使う。
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget


def apply_bitmap_font_strategy(
    root: QWidget, point_size: int | None = None
) -> None:
    """root とその全子孫 widget の font に PreferBitmap + NoAntialias を再適用。

    MS Gothic の埋め込みビットマップで描画させるため、QSS 適用後の widget
    tree に対して呼ぶ。サブダイアログを開く時にも (新規 widget tree なので)
    呼び直す必要がある。

    `point_size` を指定すると同時にフォントサイズも上書きする (ダイアログを
    本体より一回り小さい 9pt にしたい時用)。
    """
    strategy = QFont.StyleStrategy(
        QFont.StyleStrategy.PreferBitmap
        | QFont.StyleStrategy.NoAntialias
    )
    targets = [root] + root.findChildren(QWidget)
    for w in targets:
        f = w.font()
        f.setStyleStrategy(strategy)
        if point_size is not None:
            f.setPointSize(point_size)
        w.setFont(f)
