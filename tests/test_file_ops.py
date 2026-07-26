"""core/file_ops の純粋ロジック単体テスト (Qt 非依存)。

Inbox→事件投入の不変条件 (Copy 成功時は元が消える / 失敗時は元が残る /
衝突時は自動連番 / 禁則文字は弾く) を検証する。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.file_ops import (
    FORBIDDEN_CHARS,
    ensure_suffix,
    inject,
    move,
    rename,
    resolve_collision,
    validate_name,
)


# ─────────── validate_name ───────────

def test_validate_name_ok():
    assert validate_name("受領書.pdf") is None
    assert validate_name("a.txt") is None


@pytest.mark.parametrize("bad", ["", "  ", ".", ".."])
def test_validate_name_empty_or_reserved(bad):
    assert validate_name(bad) is not None


@pytest.mark.parametrize("c", list(FORBIDDEN_CHARS))
def test_validate_name_forbidden_chars(c):
    assert validate_name(f"x{c}y.pdf") is not None


def test_validate_name_trailing_space_or_dot():
    assert validate_name("foo.pdf ") is not None
    assert validate_name("foo.pdf.") is not None


# ─────────── ensure_suffix (F2 拡張子保護) ───────────

def test_ensure_suffix_restores_dropped_extension():
    # 全選択で打ち直して拡張子が消えた → 従前の拡張子を補う
    assert ensure_suffix("受領書.pdf", "訴状副本") == "訴状副本.pdf"


def test_ensure_suffix_keeps_deliberate_change():
    # あえて別の拡張子を付けた → 尊重してそのまま
    assert ensure_suffix("受領書.pdf", "受領書.txt") == "受領書.txt"
    assert ensure_suffix("メモ.txt", "メモ.md") == "メモ.md"


def test_ensure_suffix_unchanged_extension_is_noop():
    assert ensure_suffix("受領書.pdf", "訴状副本.pdf") == "訴状副本.pdf"
    # 大文字小文字違いも「拡張子あり」として維持
    assert ensure_suffix("受領書.PDF", "訴状副本.pdf") == "訴状副本.pdf"


def test_ensure_suffix_numeric_or_japanese_dot_is_not_extension():
    # ".2" や ".控訴審" は名前の一部 → 従前の拡張子を補う
    assert ensure_suffix("報告書.pdf", "報告書v1.2") == "報告書v1.2.pdf"
    assert ensure_suffix("判決.pdf", "判決.控訴審") == "判決.控訴審.pdf"


def test_ensure_suffix_original_without_extension_is_noop():
    # 元が拡張子なし (フォルダや拡張子なしファイル) → 何も補わない
    assert ensure_suffix("メモ", "備忘録") == "備忘録"
    # 元の suffix が拡張子に見えない (".控訴審") 場合も補わない
    assert ensure_suffix("判決.控訴審", "判決メモ") == "判決メモ"


def test_ensure_suffix_short_and_alnum_extensions():
    # ".7z" のような数字始まり + 英字を含む suffix は拡張子扱い
    assert ensure_suffix("資料.7z", "証拠一式") == "証拠一式.7z"
    assert ensure_suffix("資料.7z", "証拠一式.zip") == "証拠一式.zip"
    assert ensure_suffix("写真.kphoto", "現場写真") == "現場写真.kphoto"


# ─────────── resolve_collision ───────────

def test_resolve_collision_no_existing(tmp_path: Path):
    p, collided = resolve_collision(tmp_path, "a.pdf")
    assert p == tmp_path / "a.pdf"
    assert collided is False


def test_resolve_collision_one_existing(tmp_path: Path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    p, collided = resolve_collision(tmp_path, "a.pdf")
    assert p == tmp_path / "a (2).pdf"
    assert collided is True


def test_resolve_collision_multiple_existing(tmp_path: Path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "a (2).pdf").write_bytes(b"x")
    (tmp_path / "a (3).pdf").write_bytes(b"x")
    p, collided = resolve_collision(tmp_path, "a.pdf")
    assert p == tmp_path / "a (4).pdf"
    assert collided is True


# ─────────── inject ───────────

def _make_src(tmp_path: Path, name: str = "受領書.pdf", body: bytes = b"hello") -> Path:
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    p = src_dir / name
    p.write_bytes(body)
    return p


def test_inject_success_moves_file(tmp_path: Path):
    src = _make_src(tmp_path)
    dst_dir = tmp_path / "case" / "3_受信"

    r = inject(src, dst_dir)

    assert r.ok and r.action == "inject"
    assert not src.exists()                       # 元は消えた
    assert r.dst is not None and r.dst.exists()   # 投入先に存在
    assert r.dst.read_bytes() == b"hello"
    assert r.collided is False
    assert r.renamed_to == "受領書.pdf"
    assert r.original_name == "受領書.pdf"


def test_inject_with_rename(tmp_path: Path):
    src = _make_src(tmp_path, "scan_001.pdf")
    dst_dir = tmp_path / "case" / "1_文書"

    r = inject(src, dst_dir, new_name="委任状.pdf")

    assert r.ok
    assert (dst_dir / "委任状.pdf").exists()
    assert not src.exists()
    assert r.original_name == "scan_001.pdf"
    assert r.renamed_to == "委任状.pdf"


def test_inject_collision_auto_renumbers(tmp_path: Path):
    src = _make_src(tmp_path)
    dst_dir = tmp_path / "case" / "3_受信"
    dst_dir.mkdir(parents=True)
    (dst_dir / "受領書.pdf").write_bytes(b"existing")

    r = inject(src, dst_dir)

    assert r.ok
    assert r.collided is True
    assert r.renamed_to == "受領書 (2).pdf"
    assert (dst_dir / "受領書.pdf").read_bytes() == b"existing"  # 既存は無傷
    assert (dst_dir / "受領書 (2).pdf").read_bytes() == b"hello"
    assert not src.exists()


def test_inject_missing_src(tmp_path: Path):
    r = inject(tmp_path / "missing.pdf", tmp_path / "case" / "1_文書")
    assert not r.ok
    assert "見つかりません" in r.error


def test_inject_bad_name(tmp_path: Path):
    src = _make_src(tmp_path)
    r = inject(src, tmp_path / "case" / "1_文書", new_name="a/b.pdf")
    assert not r.ok
    assert src.exists()                            # 元は残る


def test_inject_folder_moves_recursively(tmp_path: Path):
    """フォルダ inject: デスクトップに作った作業フォルダごと事件サブフォルダへ移動。

    2026-05-25 追加。k-systemz サブアプリ生成物や作業中フォルダを Inbox 経由で
    丸ごと運ぶ用途。フォルダ配下のファイル構造はそのまま保持される。
    """
    src_dir = tmp_path / "案件メモ"
    src_dir.mkdir()
    (src_dir / "覚書.txt").write_bytes(b"hello")
    (src_dir / "サブ").mkdir()
    (src_dir / "サブ" / "添付.pdf").write_bytes(b"pdfdata")

    dst_dir = tmp_path / "case" / "4_資料"
    r = inject(src_dir, dst_dir)

    assert r.ok
    assert r.action == "inject"
    moved = dst_dir / "案件メモ"
    assert moved.is_dir()
    assert (moved / "覚書.txt").read_bytes() == b"hello"
    assert (moved / "サブ" / "添付.pdf").read_bytes() == b"pdfdata"
    assert not src_dir.exists()                    # 元は消える


def test_inject_folder_collision_renumbers(tmp_path: Path):
    """フォルダ衝突時は ` (2)` 連番付与で回避 (ファイルと同方式)。"""
    src_dir = tmp_path / "案件メモ"
    src_dir.mkdir()
    (src_dir / "a.txt").write_bytes(b"new")

    dst_dir = tmp_path / "case" / "4_資料"
    dst_dir.mkdir(parents=True)
    (dst_dir / "案件メモ").mkdir()                 # 既存衝突
    (dst_dir / "案件メモ" / "old.txt").write_bytes(b"old")

    r = inject(src_dir, dst_dir)
    assert r.ok
    assert r.collided is True
    assert r.renamed_to == "案件メモ (2)"
    assert (dst_dir / "案件メモ" / "old.txt").exists()    # 既存は残る
    assert (dst_dir / "案件メモ (2)" / "a.txt").exists()  # 新規が連番で入る


# ─────────── move ───────────

def test_move_success(tmp_path: Path):
    src_dir = tmp_path / "caseA" / "1_文書"
    src_dir.mkdir(parents=True)
    src = src_dir / "資料.pdf"
    src.write_bytes(b"data")

    dst_dir = tmp_path / "caseB" / "4_資料"
    r = move(src, dst_dir)

    assert r.ok and r.action == "move"
    assert not src.exists()
    assert (dst_dir / "資料.pdf").read_bytes() == b"data"


def test_move_collision_auto_renumbers(tmp_path: Path):
    src_dir = tmp_path / "caseA" / "1_文書"
    src_dir.mkdir(parents=True)
    src = src_dir / "資料.pdf"
    src.write_bytes(b"new")

    dst_dir = tmp_path / "caseB" / "4_資料"
    dst_dir.mkdir(parents=True)
    (dst_dir / "資料.pdf").write_bytes(b"existing")

    r = move(src, dst_dir)

    assert r.ok and r.collided is True
    assert (dst_dir / "資料.pdf").read_bytes() == b"existing"
    assert (dst_dir / "資料 (2).pdf").read_bytes() == b"new"


# ─────────── rename ───────────

def test_rename_success(tmp_path: Path):
    p = tmp_path / "scan_001.pdf"
    p.write_bytes(b"x")

    r = rename(p, "受領書.pdf")

    assert r.ok and r.action == "rename"
    assert not p.exists()
    assert (tmp_path / "受領書.pdf").exists()


def test_rename_unchanged_is_noop(tmp_path: Path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"x")
    r = rename(p, "a.pdf")
    assert r.ok
    assert p.exists()


def test_rename_collision_auto_renumbers(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"a")
    b.write_bytes(b"b")

    r = rename(a, "b.pdf")
    assert r.ok and r.collided is True
    assert r.renamed_to == "b (2).pdf"
    assert (tmp_path / "b.pdf").read_bytes() == b"b"
    assert (tmp_path / "b (2).pdf").read_bytes() == b"a"
