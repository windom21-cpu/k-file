"""core/undo_ops の純粋ロジック単体テスト (Qt 非依存)。

drop_history の 1 行を渡して、ファイルが正しく逆操作されるかを確認する。
"""
from __future__ import annotations

from pathlib import Path

from src.core.undo_ops import undo_action


def _row(action: str, src: Path, dst: Path | None = None) -> dict:
    """sqlite3.Row 風の dict をテスト入力に。"""
    return {"action": action, "src_path": str(src), "dst_path": str(dst) if dst else None}


def test_undo_inject(tmp_path: Path):
    """inject 逆実行: 投入先にあるファイルを元位置に戻す。"""
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    src = src_dir / "受領書.pdf"   # 既に消えている (inject 完了後)

    dst_dir = tmp_path / "case" / "3_受信"
    dst_dir.mkdir(parents=True)
    dst = dst_dir / "受領書.pdf"
    dst.write_bytes(b"data")

    ok, _msg = undo_action(_row("inject", src, dst))
    assert ok
    assert not dst.exists()
    assert src.exists() and src.read_bytes() == b"data"


def test_undo_move(tmp_path: Path):
    """move 逆実行: 同じく dst → src。"""
    src_dir = tmp_path / "caseA" / "1_文書"
    src_dir.mkdir(parents=True)
    src = src_dir / "資料.pdf"

    dst_dir = tmp_path / "caseB" / "1_文書"
    dst_dir.mkdir(parents=True)
    dst = dst_dir / "資料.pdf"
    dst.write_bytes(b"x")

    ok, _ = undo_action(_row("move", src, dst))
    assert ok
    assert not dst.exists()
    assert src.exists()


def test_undo_inject_dst_missing(tmp_path: Path):
    """dst が既に動いている場合は失敗 (二重 undo 等)。"""
    src = tmp_path / "inbox" / "a.pdf"
    dst = tmp_path / "case" / "1" / "a.pdf"
    ok, msg = undo_action(_row("inject", src, dst))
    assert not ok
    assert "見つかりません" in msg


def test_undo_inject_src_already_exists(tmp_path: Path):
    """戻し先に同名が既にある場合は失敗 (誤上書き防止)。"""
    src_dir = tmp_path / "inbox"
    src_dir.mkdir()
    src = src_dir / "a.pdf"
    src.write_bytes(b"existing")    # 戻し先に別の同名が既にある

    dst_dir = tmp_path / "case" / "1"
    dst_dir.mkdir(parents=True)
    dst = dst_dir / "a.pdf"
    dst.write_bytes(b"to-undo")

    ok, msg = undo_action(_row("inject", src, dst))
    assert not ok
    assert "既に" in msg
    # dst も src も両方そのまま残っている
    assert dst.exists() and src.exists()


def test_undo_rename(tmp_path: Path):
    """rename 逆実行: 現在の新名 → 旧名に戻す。"""
    src = tmp_path / "scan_001.pdf"     # 旧名 (消えている)
    dst = tmp_path / "受領書.pdf"        # 新名 (現存)
    dst.write_bytes(b"data")

    ok, _ = undo_action(_row("rename", src, dst))
    assert ok
    assert not dst.exists()
    assert src.exists()


def test_undo_trash_is_manual(tmp_path: Path):
    """trash の undo は OS ごみ箱からの手動復元案内で失敗扱い。

    ファイル名を含んだ具体メッセージが返ることを確認 (動線案内も含む)。
    """
    src = tmp_path / "受領書.pdf"
    ok, msg = undo_action(_row("trash", src, None))
    assert not ok
    assert "受領書.pdf" in msg
    assert "ごみ箱" in msg
    assert "元に戻す" in msg


def test_undo_unknown_action():
    """未対応の action は失敗。"""
    ok, msg = undo_action({"action": "weird", "src_path": "/a", "dst_path": "/b"})
    assert not ok
    assert "未対応" in msg
