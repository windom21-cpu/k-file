"""font_fallback (同梱 IPAゴシックの MS Gothic 代替) のテスト。

実行環境に MS Gothic がある場合 (Office 入り Mac / Win) と無い場合 (CI の
ubuntu 等) の両方で通るよう、PREFERRED_FAMILIES を monkeypatch して
「全部ある」「欠けている」の両経路を強制的に踏む。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QFontInfo

from src.ui import font_fallback

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_bundled_font_and_license_exist():
    """同梱フォント本体と IPA ライセンス全文が揃っていること (再配布条件)。"""
    fonts_dir = REPO_ROOT / "resources" / "fonts"
    assert (fonts_dir / "ipag.ttf").is_file()
    assert (fonts_dir / "IPA_Font_License_Agreement_v1.0.txt").is_file()


def test_no_substitution_when_preferred_exists(monkeypatch):
    """優先 family が全て存在する環境では何もしない (システムフォント優先)。"""
    existing = QFontDatabase.families()[0]
    monkeypatch.setattr(font_fallback, "PREFERRED_FAMILIES", (existing,))
    assert font_fallback.ensure_gothic_fallback(REPO_ROOT) is None


def test_fallback_registers_ipa_when_missing(monkeypatch):
    """欠けた family がある環境では IPAゴシックを登録し、代替解決させる。"""
    fake_missing = "kfile-no-such-family-xyz"
    monkeypatch.setattr(
        font_fallback, "PREFERRED_FAMILIES", (fake_missing,)
    )
    fallback = font_fallback.ensure_gothic_fallback(REPO_ROOT)
    assert fallback is not None
    assert "IPA" in fallback  # IPAゴシック / IPAGothic
    assert fallback in QFontDatabase.families()
    # QFont("欠けた名前") が IPA へ解決される (QSS / tooltip_font と同じ経路)
    resolved = QFontInfo(QFont(fake_missing, 12)).family()
    assert resolved == fallback


def test_missing_bundle_file_is_silent(monkeypatch, tmp_path):
    """フォントファイルが無くても例外を投げず None (Qt の代替に任せる)。"""
    monkeypatch.setattr(
        font_fallback, "PREFERRED_FAMILIES", ("kfile-no-such-family-abc",)
    )
    assert font_fallback.ensure_gothic_fallback(tmp_path) is None
