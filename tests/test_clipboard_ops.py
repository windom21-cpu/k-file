"""clipboard_ops の単体テスト (OS クリップボード経由のファイル コピー/切り取り)。

QApplication.clipboard() を使うので conftest の widget 対応 QApplication が要る。
offscreen プラットフォームでも QClipboard は in-process で機能するため、set →
read のラウンドトリップ・cut/copy 判別・空判定を検証できる (Explorer 相互運用
そのものは Windows シェル依存なので実機確認に委ねる)。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.ui import clipboard_ops


def _clear() -> None:
    cb = QApplication.clipboard()
    if cb is not None:
        cb.clear()


def test_copy_roundtrip(tmp_path: Path) -> None:
    """コピーで載せたファイルがそのまま読み戻せ、cut=False になる。"""
    f1 = tmp_path / "a.pdf"
    f2 = tmp_path / "b.pdf"
    f1.write_text("x")
    f2.write_text("y")
    clipboard_ops.set_file_clipboard([f1, f2], cut=False)

    result = clipboard_ops.read_file_clipboard()
    assert result is not None
    paths, cut = result
    assert cut is False
    assert {str(p) for p in paths} == {str(f1), str(f2)}


def test_cut_sets_move_effect(tmp_path: Path) -> None:
    """切り取りで載せると read 時に cut=True が返る (Preferred DropEffect)。"""
    f1 = tmp_path / "a.pdf"
    f1.write_text("x")
    clipboard_ops.set_file_clipboard([f1], cut=True)

    result = clipboard_ops.read_file_clipboard()
    assert result is not None
    paths, cut = result
    assert cut is True
    assert [str(p) for p in paths] == [str(f1)]


def test_has_files_reflects_state(tmp_path: Path) -> None:
    """clipboard_has_files がファイル有無を正しく返す。"""
    _clear()
    assert clipboard_ops.clipboard_has_files() is False
    f1 = tmp_path / "a.pdf"
    f1.write_text("x")
    clipboard_ops.set_file_clipboard([f1], cut=False)
    assert clipboard_ops.clipboard_has_files() is True


def test_read_empty_returns_none() -> None:
    """ファイルが載っていなければ read は None。"""
    _clear()
    assert clipboard_ops.read_file_clipboard() is None


def test_text_only_clipboard_returns_none() -> None:
    """テキストだけが載っている (= フルパスコピー等) 場合は None。"""
    _clear()
    cb = QApplication.clipboard()
    assert cb is not None
    cb.setText("C:/foo/bar.pdf")
    assert clipboard_ops.read_file_clipboard() is None


def test_clear_empties_clipboard(tmp_path: Path) -> None:
    """clear_file_clipboard で載せたファイルが消える (切り取り→貼り付け後)。"""
    f1 = tmp_path / "a.pdf"
    f1.write_text("x")
    clipboard_ops.set_file_clipboard([f1], cut=True)
    assert clipboard_ops.clipboard_has_files() is True
    clipboard_ops.clear_file_clipboard()
    assert clipboard_ops.clipboard_has_files() is False
    assert clipboard_ops.read_file_clipboard() is None


def test_set_empty_paths_noop(tmp_path: Path) -> None:
    """空リストを set しても既存クリップボードを壊さない。"""
    f1 = tmp_path / "a.pdf"
    f1.write_text("x")
    clipboard_ops.set_file_clipboard([f1], cut=False)
    clipboard_ops.set_file_clipboard([], cut=False)
    # 空 set は no-op なので直前のコピーが残る
    assert clipboard_ops.clipboard_has_files() is True
