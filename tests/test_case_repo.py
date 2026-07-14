"""core/case_repo の単体テスト (Qt 非依存)。

モック ksystemz.db を tmp_path に都度生成して、検索とフォルダ解決の挙動を
確認する。実 ksystemz.db には触らない (ADR-14)。
"""
from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

import pytest

from src.core.case_repo import CaseRecord, CaseRepo
from tests.fixtures.build_mock_ksystemz_db import build


@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """テスト専用のモック ksystemz.db を tmp_path に生成。"""
    db = build(tmp_path / "ksystemz.db")
    # build() は doc_root を ~/k-file-test-data/事件 に設定するが、テストでは
    # tmp_path 配下に独立した事件フォルダを用意してそちらを指すように上書きする。
    doc_root = tmp_path / "事件"
    doc_root.mkdir()
    (doc_root / "R060200042 山田太郎 損害賠償").mkdir()
    (doc_root / "R060200043 ㈱A商事 売買代金").mkdir()
    (doc_root / "R060200044 鈴木花子 離婚").mkdir()
    # case_code 未登録のフォルダ (前方一致しないので resolve_folder 対象外)
    (doc_root / "K990000000 過去案件").mkdir()

    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE office_info SET doc_root_path = ?, doc_root_path_mac = ?",
        (str(doc_root), str(doc_root)),
    )
    conn.commit()
    conn.close()
    return db


def test_doc_root_returns_path(mock_db: Path, tmp_path: Path):
    repo = CaseRepo(mock_db)
    assert repo.doc_root() == tmp_path / "事件"
    repo.close()


def test_search_all_active(mock_db: Path):
    """既定 (active_only=True) は 顧問 + 終了 + 不受任 + 諸件 を除外。"""
    repo = CaseRepo(mock_db)
    results = repo.search()
    codes = {r.case_code for r in results}
    # 顧問 (R060200047) + 終了 (R060200046) は除外
    assert "R060200047" not in codes
    assert "R060200046" not in codes
    # 進行中 / 申立準備中 / 受任予定 は表示
    assert {"R060200042", "R060200043", "R060200044", "R060200045"} <= codes
    repo.close()


def test_search_inactive_included(mock_db: Path):
    """active_only=False で 顧問・終了 含む全件取得。"""
    repo = CaseRepo(mock_db)
    results = repo.search(active_only=False)
    codes = {r.case_code for r in results}
    assert "R060200046" in codes      # 終了
    assert "R060200047" in codes      # 顧問
    repo.close()


def test_search_keyword_case_code(mock_db: Path):
    repo = CaseRepo(mock_db)
    results = repo.search(keyword="42")    # case_code 末尾
    codes = [r.case_code for r in results]
    assert "R060200042" in codes
    assert "R060200043" not in codes
    repo.close()


def test_search_keyword_client_personal(mock_db: Path):
    """個人依頼者の姓で検索。"""
    repo = CaseRepo(mock_db)
    results = repo.search(keyword="山田")
    assert any(r.case_code == "R060200042" for r in results)
    repo.close()


def test_search_keyword_client_corp(mock_db: Path):
    """法人依頼者の法人名で検索。"""
    repo = CaseRepo(mock_db)
    results = repo.search(keyword="A商事")
    assert any(r.case_code == "R060200043" for r in results)
    repo.close()


def test_search_keyword_case_name(mock_db: Path):
    """事件名 (case_name) で検索。"""
    repo = CaseRepo(mock_db)
    results = repo.search(keyword="離婚")
    assert any(r.case_code == "R060200044" for r in results)
    repo.close()


def test_search_returns_case_records(mock_db: Path):
    """戻り値が CaseRecord で、display_label が組み立てられる。"""
    repo = CaseRepo(mock_db)
    results = repo.search(keyword="山田")
    rec = next(r for r in results if r.case_code == "R060200042")
    assert isinstance(rec, CaseRecord)
    assert rec.case_name == "損害賠償"
    assert rec.case_type == "民事"
    assert rec.client_display == "山田太郎"
    assert "山田太郎" in rec.display_label()
    assert "R060200042" in rec.display_label()
    repo.close()


def test_search_corp_displays_corp_name(mock_db: Path):
    """法人案件は client_display が法人名 (姓名は空)。"""
    repo = CaseRepo(mock_db)
    results = repo.search(keyword="A商事")
    rec = next(r for r in results if r.case_code == "R060200043")
    assert rec.client_display == "㈱A商事"
    repo.close()


def test_resolve_folder_prefix_match(mock_db: Path, tmp_path: Path):
    """case_code 前方一致で実フォルダを引く。"""
    repo = CaseRepo(mock_db)
    p = repo.resolve_folder("R060200042")
    assert p == tmp_path / "事件" / "R060200042 山田太郎 損害賠償"
    repo.close()


def test_resolve_folder_matches_across_unicode_normalization(
    mock_db: Path, tmp_path: Path
):
    """濁点の合成/分解が食い違っても引ける (macOS の readdir は NFD を返しうる)。

    現行の case_code は ASCII のみだが、かなを含む名前でも Mac だけ引けなくなる
    ことがないよう、両辺を NFC に揃えてから前方一致する。
    """
    doc_root = tmp_path / "事件"
    (doc_root / "R060200045ダミー商事 立替金").mkdir()   # NFC でフォルダ作成
    repo = CaseRepo(mock_db)
    # 分解形 (NFD) の code で引いても同じフォルダに解決する
    nfd_code = unicodedata.normalize("NFD", "R060200045ダミー商事")
    assert repo.resolve_folder(nfd_code) == doc_root / "R060200045ダミー商事 立替金"
    repo.close()


def test_resolve_folder_missing_returns_none(mock_db: Path):
    """case_code が存在しなければ None。"""
    repo = CaseRepo(mock_db)
    assert repo.resolve_folder("R999999999") is None
    repo.close()


def test_resolve_folder_empty_code_returns_none(mock_db: Path):
    repo = CaseRepo(mock_db)
    assert repo.resolve_folder("") is None
    repo.close()


def test_readonly_connection_prevents_write(mock_db: Path):
    """念のため: 書き込み試行が拒否されることを確認 (Dropbox 安全)。"""
    repo = CaseRepo(mock_db)
    with pytest.raises(sqlite3.OperationalError):
        repo._conn.execute("UPDATE cases SET status = 'X' WHERE id = 1")
    repo.close()


def test_missing_db_raises():
    """db ファイルがない時は FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        CaseRepo(Path("/nonexistent/path/ksystemz.db"))
