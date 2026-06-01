"""folder_scanner の走査ロジックのテスト (Qt 非依存)。

2026-05-31 のフリーズ対策 Phase 2 (①) で、事件フォルダ走査を
`Path.iterdir()` + 個別 `stat()` から `os.scandir()` の DirEntry キャッシュ
利用へ置き換えた (X:=Dropbox 上の metadata 取得でメインスレッドが固まる主因の
除去)。出力 (CaseScan / FileEntry) は従来と完全に同一であることを固定するため、
ここで挙動を網羅する。symlink/.lnk/broken-link の分岐が繊細なので重点的に。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.folder_scanner import (  # noqa: E402
    MAX_ALT_SUBFOLDERS,
    list_files,
    list_folder,
    scan_case_folder,
)


def _supports_symlink(tmp_path: Path) -> bool:
    """この環境で symlink を張れるか (Win は権限次第で不可)。"""
    try:
        target = tmp_path / "_lnk_probe_target"
        target.mkdir()
        link = tmp_path / "_lnk_probe"
        os.symlink(target, link)
        link.unlink()
        target.rmdir()
        return True
    except (OSError, NotImplementedError):
        return False


# ───────── list_folder / list_files ─────────

def test_list_folder_files_and_dirs(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"hello")
    (tmp_path / "sub").mkdir()
    entries = {e.name: e for e in list_folder(tmp_path)}
    assert set(entries) == {"a.pdf", "sub"}
    assert entries["a.pdf"].is_dir is False
    assert entries["a.pdf"].size == 5
    assert entries["a.pdf"].mtime > 0
    assert entries["sub"].is_dir is True
    assert entries["sub"].size == 0   # フォルダは size 0


def test_list_folder_nonexistent_returns_empty(tmp_path):
    assert list_folder(tmp_path / "nope") == []


def test_list_folder_on_file_returns_empty(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"x")
    # ディレクトリでないパスは空 (os.scandir が NotADirectoryError)
    assert list_folder(f) == []


def test_list_files_excludes_dirs(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    names = {e.name for e in list_files(tmp_path)}
    assert names == {"a.pdf"}


# ───────── scan_case_folder: 並び順 / Alt 割当 ─────────

def test_scan_orders_pattern_dirs_first(tmp_path):
    for name in ["2_発信", "1_文書", "参考", "3_受信"]:
        (tmp_path / name).mkdir()
    scan = scan_case_folder(tmp_path)
    names = [sf.name for sf in scan.subfolders]
    # \d_ パターンが名前順で先、その後その他フォルダ
    assert names == ["1_文書", "2_発信", "3_受信", "参考"]
    assert [sf.alt_key for sf in scan.subfolders] == [1, 2, 3, 4]


def test_scan_alt_key_caps_at_max(tmp_path):
    # 0_〜9_ の 10 個 (全て \d_ パターン)。先頭 9 個に 1〜9、10 個目は None
    for d in range(10):
        (tmp_path / f"{d}_x").mkdir()
    scan = scan_case_folder(tmp_path)
    assert len(scan.subfolders) == 10
    assert [sf.alt_key for sf in scan.subfolders[:MAX_ALT_SUBFOLDERS]] == list(
        range(1, MAX_ALT_SUBFOLDERS + 1)
    )
    assert scan.subfolders[MAX_ALT_SUBFOLDERS].alt_key is None


def test_scan_root_files_and_badges(tmp_path):
    # 事件フォルダ直下のファイルは root_files、サブフォルダには入れない
    (tmp_path / "直下.pdf").write_bytes(b"x")
    sub = tmp_path / "1_文書"
    sub.mkdir()
    (sub / "f1.pdf").write_bytes(b"a")
    (sub / "f2.pdf").write_bytes(b"bb")
    (sub / "nested").mkdir()
    scan = scan_case_folder(tmp_path)
    assert [e.name for e in scan.root_files] == ["直下.pdf"]
    assert len(scan.subfolders) == 1
    sf = scan.subfolders[0]
    assert sf.file_count == 2          # ファイル 2 個 (nested フォルダは数えない)
    assert sf.has_child_dirs is True   # 子フォルダ nested あり


def test_scan_empty_or_missing(tmp_path):
    scan = scan_case_folder(tmp_path / "missing")
    assert scan.subfolders == []
    assert scan.root_files == []


# ───────── symlink / .lnk の分岐 (事件ショートカット扱い) ─────────

def test_symlink_dir_goes_to_root_files_not_subfolder(tmp_path):
    if not _supports_symlink(tmp_path):
        import pytest
        pytest.skip("この環境では symlink を作成できない")
    # 別事件 (= ショートカット先) は走査対象フォルダの「外」にある想定。
    # 対象フォルダ内に置くと、それ自体が実サブフォルダになってしまう。
    case_root = tmp_path / "case"
    case_root.mkdir()
    other_case = tmp_path / "external_case"   # 走査対象の外
    other_case.mkdir()
    real_sub = case_root / "1_文書"
    real_sub.mkdir()
    link = case_root / "B事件へ"
    os.symlink(other_case, link)
    scan = scan_case_folder(case_root)
    # symlink(→dir) は左ボタン列のサブフォルダにせず root_files に入れる
    assert [sf.name for sf in scan.subfolders] == ["1_文書"]
    root_names = {e.name: e for e in scan.root_files}
    assert "B事件へ" in root_names
    assert root_names["B事件へ"].is_link is True


def test_broken_symlink_is_skipped_without_crash(tmp_path):
    if not _supports_symlink(tmp_path):
        import pytest
        pytest.skip("この環境では symlink を作成できない")
    (tmp_path / "a.pdf").write_bytes(b"x")
    os.symlink(tmp_path / "does_not_exist", tmp_path / "dangling")
    # stat に失敗する dangling link はスキップされ、例外を投げない
    names = {e.name for e in list_folder(tmp_path)}
    assert "a.pdf" in names
    assert "dangling" not in names
    # scan_case_folder も同様にクラッシュしない
    scan = scan_case_folder(tmp_path)
    assert "dangling" not in {e.name for e in scan.root_files}
