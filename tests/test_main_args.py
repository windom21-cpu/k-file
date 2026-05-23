"""src.main.parse_initial_paths の単体テスト。

CLI 引数 → 事件タブとして開くフォルダ抽出 (K-SystemZ 連携の入口)。
"""
from __future__ import annotations

from pathlib import Path

from src.main import parse_initial_paths


def test_no_args_returns_empty():
    """argv に実行ファイル名だけ (引数なし) → 空リスト。"""
    assert parse_initial_paths(["k-file.exe"]) == []


def test_single_dir_arg(tmp_path: Path):
    d = tmp_path / "事件A"
    d.mkdir()
    result = parse_initial_paths(["k-file.exe", str(d)])
    assert result == [d]


def test_multiple_dir_args_preserve_order(tmp_path: Path):
    a = tmp_path / "A"
    b = tmp_path / "B"
    c = tmp_path / "C"
    a.mkdir()
    b.mkdir()
    c.mkdir()
    result = parse_initial_paths(["k-file.exe", str(a), str(b), str(c)])
    assert result == [a, b, c]


def test_file_arg_ignored(tmp_path: Path):
    """ファイルは事件フォルダではないので無視。"""
    d = tmp_path / "事件"
    d.mkdir()
    f = tmp_path / "scan.pdf"
    f.write_bytes(b"x")
    result = parse_initial_paths(["k-file.exe", str(f), str(d)])
    assert result == [d]


def test_nonexistent_arg_ignored(tmp_path: Path):
    """存在しないパスは無視 (黙ってスキップ)。"""
    d = tmp_path / "real"
    d.mkdir()
    missing = tmp_path / "does-not-exist"
    result = parse_initial_paths(["k-file.exe", str(missing), str(d)])
    assert result == [d]


def test_empty_string_arg_ignored():
    """空文字列引数は無視 (誤って渡されるケース)。"""
    assert parse_initial_paths(["k-file.exe", "", ""]) == []


def test_arbitrary_folder_accepted(tmp_path: Path):
    """case_code パターン (\\d_) に合致しない任意フォルダも受け入れる
    (汎用ファイラー化: 事件フォルダ以外も開ける)。"""
    folder = tmp_path / "Random Project"
    folder.mkdir()
    assert parse_initial_paths(["k-file.exe", str(folder)]) == [folder]
