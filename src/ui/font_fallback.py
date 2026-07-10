"""MS Gothic が無い環境向けの同梱 IPAゴシック フォールバック。

QSS (`win95.qss` の `*` rule) とツールチップは "MS Gothic" を第一候補に
指定しているが、Mac / Linux には通常入っていない (Mac は Office for Mac が
入っていれば存在する)。フォールバック方針 (ユーザー決定 2026-07-10):

- **システムに MS Gothic があればそれをそのまま使う** (同梱フォントは登録すら
  しない = 従来環境は一切変化なし)
- 無いときだけ同梱 IPAゴシック (`resources/fonts/ipag.ttf`) を登録し、
  QFont.insertSubstitution で "MS Gothic" / "MS UI Gothic" の解決先にする。
  IPAゴシックは MS Gothic と寸法互換のため px 前提レイアウトの見切れリスクが
  最小 (HANDOVER §8 2026-07-08 確定方針)

IPAゴシックの再配布は IPA フォントライセンス v1.0 による (ライセンス全文を
`resources/fonts/` に同梱)。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

# QSS の font-family 第一候補と揃える。ここに列挙した family が全て存在する
# 環境では何もしない。
PREFERRED_FAMILIES = ("MS Gothic", "MS UI Gothic")

BUNDLED_FONT_RELPATH = Path("resources") / "fonts" / "ipag.ttf"


def ensure_gothic_fallback(base_path: Path) -> str | None:
    """MS Gothic 系が欠けた環境で同梱 IPAゴシックを代替登録する。

    QApplication 生成後・QSS 適用前に呼ぶ。戻り値は代替に使った family 名
    (フォールバック不要 = システムフォントで足りたときは None)。
    フォント読込みに失敗しても例外は投げない (従来どおり Qt の代替に任せる)。
    """
    installed = set(QFontDatabase.families())
    missing = [f for f in PREFERRED_FAMILIES if f not in installed]
    if not missing:
        return None

    font_path = base_path / BUNDLED_FONT_RELPATH
    if not font_path.is_file():
        return None
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        return None
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return None
    fallback = families[0]
    for name in missing:
        QFont.insertSubstitution(name, fallback)
    return fallback
