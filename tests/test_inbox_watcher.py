"""inbox_watcher の純粋関数 list_inbox_files の単体テスト (Qt 非依存)。

cutoff_days による「N 日以内のみ表示」フィルタが期待どおり動くかを確認する。
ファイル種別 (PDF + 画像のみ、txt 等は除外) と複数ソース合流もチェック。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from src.core.inbox_watcher import InboxSource, list_inbox_files


def _touch(path: Path, body: bytes = b"x", days_old: int = 0) -> Path:
    """テスト用ファイル作成 + days_old 日前の mtime を仕込む。"""
    path.write_bytes(body)
    if days_old:
        ts = time.time() - days_old * 86400
        os.utime(str(path), (ts, ts))
    return path


def test_list_inbox_files_basic(tmp_path: Path):
    """PDF と画像は表示、txt は除外、フォルダも除外。"""
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    _touch(src_dir / "a.pdf")
    _touch(src_dir / "b.png")
    _touch(src_dir / "c.txt")           # 拡張子フィルタで除外
    (src_dir / "subfolder").mkdir()     # is_file=False で除外

    result = list_inbox_files([InboxSource("test", src_dir)])
    names = {f.name for f in result}
    assert names == {"a.pdf", "b.png"}


def test_list_inbox_files_no_cutoff_shows_old(tmp_path: Path):
    """cutoff_days=None なら古いファイルもそのまま表示。"""
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    _touch(src_dir / "new.pdf", days_old=0)
    _touch(src_dir / "old.pdf", days_old=100)

    result = list_inbox_files([InboxSource("test", src_dir, cutoff_days=None)])
    names = {f.name for f in result}
    assert names == {"new.pdf", "old.pdf"}


def test_list_inbox_files_cutoff_excludes_old(tmp_path: Path):
    """cutoff_days=7 なら 7 日より古いものは除外、新しいものは残る。"""
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    _touch(src_dir / "yesterday.pdf", days_old=1)
    _touch(src_dir / "weekago.pdf", days_old=6)
    _touch(src_dir / "twoweeks.pdf", days_old=14)
    _touch(src_dir / "ancient.pdf", days_old=100)

    result = list_inbox_files([InboxSource("test", src_dir, cutoff_days=7)])
    names = {f.name for f in result}
    assert names == {"yesterday.pdf", "weekago.pdf"}


def test_list_inbox_files_multiple_sources_same_label(tmp_path: Path):
    """同名ラベル (Desktop が 2 ソース) はマージされて両方表示される。"""
    d1 = tmp_path / "test_desktop"
    d1.mkdir()
    _touch(d1 / "test.pdf")
    d2 = tmp_path / "real_desktop"
    d2.mkdir()
    _touch(d2 / "real.pdf")

    sources = [
        InboxSource("Desktop", d1),
        InboxSource("Desktop", d2),
    ]
    result = list_inbox_files(sources)
    by_name = {f.name: f for f in result}
    assert set(by_name.keys()) == {"test.pdf", "real.pdf"}
    assert all(f.source == "Desktop" for f in result)


def test_list_inbox_files_cutoff_per_source(tmp_path: Path):
    """ソースごとに cutoff_days を分けられる: scan=無制限 / Desktop=7日。"""
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    _touch(scan_dir / "scan_old.pdf", days_old=100)   # scan の古いものも残す

    desk_dir = tmp_path / "desktop"
    desk_dir.mkdir()
    _touch(desk_dir / "desk_new.pdf", days_old=2)
    _touch(desk_dir / "desk_old.pdf", days_old=30)    # Desktop の古いものは除外

    sources = [
        InboxSource("scan", scan_dir, cutoff_days=None),
        InboxSource("Desktop", desk_dir, cutoff_days=7),
    ]
    result = list_inbox_files(sources)
    names = {f.name for f in result}
    assert names == {"scan_old.pdf", "desk_new.pdf"}


def test_list_inbox_files_missing_source_ignored(tmp_path: Path):
    """存在しないパスのソースは静かに無視される (起動時の早期 fail を避ける)。"""
    real = tmp_path / "real"
    real.mkdir()
    _touch(real / "ok.pdf")

    sources = [
        InboxSource("missing", tmp_path / "does-not-exist"),
        InboxSource("real", real),
    ]
    result = list_inbox_files(sources)
    assert {f.name for f in result} == {"ok.pdf"}
