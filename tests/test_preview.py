"""preview_pane の非同期読込ワーカー (_load_preview) のテスト。

フリーズ対策 (2026-05-29) で、X:(Dropbox) 上のファイルの stat/read を worker
スレッドへ逃がした。その worker 側の純 I/O 関数 `_load_preview` が、拡張子と
ファイル状態から正しい `_LoadResult.kind` と中身を返すことを確認する。

QImage を使うため offscreen の QGuiApplication を 1 つ用意する (表示はしない)。
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from src.ui.preview_pane import _load_preview  # noqa: E402

# QImage 生成のため最低限の Application を 1 度だけ作る (offscreen)。
_app = QGuiApplication.instance() or QGuiApplication([])


def test_missing_file_returns_missing(tmp_path):
    r = _load_preview(tmp_path / "does_not_exist.pdf", 1)
    assert r.kind == "missing"
    assert r.seq == 1


def test_directory_returns_missing(tmp_path):
    # ディレクトリは「通常ファイルでない」ので missing 扱い
    r = _load_preview(tmp_path, 2)
    assert r.kind == "missing"


def test_pdf_reads_bytes(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4 dummy bytes")
    r = _load_preview(f, 3)
    assert r.kind == "pdf"
    assert r.pdf_bytes == b"%PDF-1.4 dummy bytes"
    assert r.size == len(b"%PDF-1.4 dummy bytes")
    assert r.seq == 3


def test_text_reads_text(tmp_path):
    f = tmp_path / "memo.txt"
    # 改行は OS で \n / \r\n が変わりうるので、本文の有無で検証する
    f.write_bytes("こんにちは\nworld".encode("utf-8"))
    r = _load_preview(f, 4)
    assert r.kind == "text"
    assert r.text == "こんにちは\nworld"
    assert r.truncated is False


def test_json_kind(tmp_path):
    f = tmp_path / "data.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    r = _load_preview(f, 5)
    assert r.kind == "json"
    assert r.text == '{"a": 1}'


def test_kphoto_treated_as_json(tmp_path):
    # K-SystemZ サブアプリの保存形式 (.kphoto) は JSON 整形対象
    f = tmp_path / "evidence.kphoto"
    f.write_text('{"k": "v"}', encoding="utf-8")
    r = _load_preview(f, 6)
    assert r.kind == "json"


def test_unsupported_ext(tmp_path):
    f = tmp_path / "thing.xyz"
    f.write_bytes(b"\x00\x01\x02")
    r = _load_preview(f, 7)
    assert r.kind == "unsupported"
    assert r.ext == ".xyz"


def test_text_truncated_over_cap(tmp_path):
    from src.ui.preview_pane import _TEXT_PREVIEW_CAP
    f = tmp_path / "big.txt"
    f.write_text("a" * (_TEXT_PREVIEW_CAP + 100), encoding="utf-8")
    r = _load_preview(f, 8)
    assert r.kind == "text"
    assert r.truncated is True


def test_cp932_fallback(tmp_path):
    # UTF-8 で decode できない CP932 のテキストもフォールバックで読める
    f = tmp_path / "sjis.txt"
    f.write_bytes("日本語テキスト".encode("cp932"))
    r = _load_preview(f, 9)
    assert r.kind == "text"
    assert "日本語" in (r.text or "")


def test_corrupt_image_returns_error(tmp_path):
    # 拡張子は画像だが中身が壊れている → QImage.isNull → error
    f = tmp_path / "broken.png"
    f.write_bytes(b"not a real png")
    r = _load_preview(f, 10)
    assert r.kind == "error"
