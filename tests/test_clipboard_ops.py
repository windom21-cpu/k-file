"""clipboard_ops の単体テスト (Explorer 互換のファイル コピー/切り取り)。

グローバルの QApplication.clipboard() を触ると、Linux/offscreen の Qt では
インタプリタ終了時に QMimeData の破棄順序で segfault する (CI のテストゲートが
exit 139 で落ちる)。そこでクリップボード I/O 部分 (set_/read_) は薄いラッパに
留め、検証は QMimeData を直接作って往復する `build_file_mime` /
`parse_file_mime` に対して行う。実クリップボードと Explorer 相互運用は Windows
シェル依存なので実機確認に委ねる (build/parse が正しければラッパは自明)。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl

from src.ui import clipboard_ops


def test_copy_roundtrip(tmp_path: Path) -> None:
    """コピーで載せた mime がそのまま読み戻せ、cut=False になる。"""
    f1 = tmp_path / "a.pdf"
    f2 = tmp_path / "b.pdf"
    mime = clipboard_ops.build_file_mime([f1, f2], cut=False)

    result = clipboard_ops.parse_file_mime(mime)
    assert result is not None
    paths, cut = result
    assert cut is False
    assert {str(p) for p in paths} == {str(f1), str(f2)}


def test_cut_sets_move_effect(tmp_path: Path) -> None:
    """切り取りで載せた mime は parse 時に cut=True (Preferred DropEffect)。"""
    f1 = tmp_path / "a.pdf"
    mime = clipboard_ops.build_file_mime([f1], cut=True)

    result = clipboard_ops.parse_file_mime(mime)
    assert result is not None
    paths, cut = result
    assert cut is True
    assert [str(p) for p in paths] == [str(f1)]


def test_parse_none_returns_none() -> None:
    """mime が None なら None。"""
    assert clipboard_ops.parse_file_mime(None) is None


def test_parse_empty_mime_returns_none() -> None:
    """url が載っていない (空の) mime は None。"""
    assert clipboard_ops.parse_file_mime(QMimeData()) is None


def test_text_only_mime_returns_none() -> None:
    """テキストだけの mime (= フルパスコピー等) は None。"""
    mime = QMimeData()
    mime.setText("C:/foo/bar.pdf")
    assert clipboard_ops.parse_file_mime(mime) is None


def test_explorer_copy_effect_value_is_copy(tmp_path: Path) -> None:
    """Explorer 流の DropEffect=1 (COPY) を載せた mime は cut=False。"""
    from PySide6.QtCore import QByteArray
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "a.pdf"))])
    mime.setData("Preferred DropEffect", QByteArray((1).to_bytes(4, "little")))
    result = clipboard_ops.parse_file_mime(mime)
    assert result is not None and result[1] is False


def test_explorer_cut_effect_value_is_move(tmp_path: Path) -> None:
    """Explorer 流の DropEffect=2 (MOVE) を載せた mime は cut=True。"""
    from PySide6.QtCore import QByteArray
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "a.pdf"))])
    mime.setData("Preferred DropEffect", QByteArray((2).to_bytes(4, "little")))
    result = clipboard_ops.parse_file_mime(mime)
    assert result is not None and result[1] is True


def test_no_effect_defaults_to_copy(tmp_path: Path) -> None:
    """Preferred DropEffect が無い (= 素の url-list) 場合は安全側でコピー扱い。"""
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "a.pdf"))])
    result = clipboard_ops.parse_file_mime(mime)
    assert result is not None and result[1] is False
