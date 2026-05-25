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
    """ブラックリスト方式: 一時/システムファイル以外は全て表示 (フォルダ含む)。

    2026-05-25 設計変更: 「Inbox は監視先フォルダの中身をそのまま見せる」方針
    に転換。k-systemz サブアプリの `.k-photo` 等 JSON 一時保存ファイル / デスク
    トップに作る作業フォルダ等が業務上 Inbox に必要なため、ホワイトリストを撤去。
    """
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    _touch(src_dir / "a.pdf")
    _touch(src_dir / "b.png")
    _touch(src_dir / "c.txt")
    _touch(src_dir / "d.docx")
    _touch(src_dir / "e.heic")           # 未知拡張子 → 表示する (ブラックリスト方式)
    _touch(src_dir / "memo.k-photo")     # k-systemz サブアプリ JSON → 表示する
    _touch(src_dir / "Thumbs.db")        # Win サムネキャッシュ → 隠す
    _touch(src_dir / ".DS_Store")        # macOS → 隠す
    _touch(src_dir / "wip.tmp")          # 一時ファイル → 隠す
    _touch(src_dir / ".hidden")          # 一般のドット隠しファイル → 隠す
    (src_dir / "subfolder").mkdir()      # フォルダ → 表示する (Inbox 経路で運ぶ)

    result = list_inbox_files([InboxSource("test", src_dir)])
    names = {f.name for f in result}
    assert names == {
        "a.pdf", "b.png", "c.txt", "d.docx",
        "e.heic", "memo.k-photo", "subfolder",
    }


def test_list_inbox_files_folder_marked_as_dir(tmp_path: Path):
    """フォルダは is_dir=True, size=0 で返る (UI 側で `<DIR>` 表示するため)。"""
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    _touch(src_dir / "doc.pdf", body=b"abc")
    (src_dir / "案件A").mkdir()

    result = list_inbox_files([InboxSource("test", src_dir)])
    by_name = {f.name: f for f in result}
    assert by_name["doc.pdf"].is_dir is False
    assert by_name["doc.pdf"].size == 3
    assert by_name["案件A"].is_dir is True
    assert by_name["案件A"].size == 0


def test_list_inbox_files_excludes_zero_byte_recent(tmp_path: Path):
    """0 バイトかつ更新 5 秒以内のファイルは「書き込み中」扱いで除外。

    複合機がスキャン PDF を書き始めた直後に Inbox が refresh されると、
    0KB のファイルが並ぶ問題への対策 (2026-05-25 本番テスト報告)。
    """
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    # 0 バイトで現在時刻に作成 → 書き込み中扱い
    fresh_zero = src_dir / "fresh_zero.pdf"
    fresh_zero.write_bytes(b"")
    # 0 バイトだが mtime を十分過去にする → 実体として空のファイル扱いで表示
    old_zero = src_dir / "old_zero.pdf"
    old_zero.write_bytes(b"")
    past = time.time() - 60.0
    os.utime(str(old_zero), (past, past))
    # 中身ありは普通に表示
    _touch(src_dir / "normal.pdf", body=b"abc")

    result = list_inbox_files([InboxSource("test", src_dir)])
    names = {f.name for f in result}
    assert names == {"old_zero.pdf", "normal.pdf"}


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


def test_list_inbox_files_dedup_same_path(tmp_path: Path):
    """同じパスを 2 つのソースで指定しても、ファイルは 1 回だけ出る。

    本番テスト (2026-05-25) で「Desktop 2 件を両方とも実 Win デスクトップに
    変えたら各ファイルが 2 倍表示」事故が発生 → resolve 済みパスで dedupe する
    保険を入れた。先に来たソースのラベルが採用される。
    """
    desk = tmp_path / "desktop"
    desk.mkdir()
    _touch(desk / "a.pdf")
    _touch(desk / "b.png")

    sources = [
        InboxSource("Desktop", desk),
        InboxSource("Desktop", desk),     # 同じパスを 2 回登録
    ]
    result = list_inbox_files(sources)
    names = [f.name for f in result]
    assert sorted(names) == ["a.pdf", "b.png"]    # 2 倍にならない


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
