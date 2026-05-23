"""K-SystemZ の `ksystemz.db` を模した dev/test 用モックを生成する。

本物の ksystemz.db は Win 機の業務環境にあり持ち出せないため (HANDOVER §15
ADR-14)、引き継ぎ書のスキーマと API ロジックを元に **完全に架空の事件データ**
を持ったモックを Linux 本機で作る。これに対して `case_repo` を実装・テスト
する。

スキーマは K-SystemZ 引き継ぎ書 v22 から抽出:
- office_info: id 固定 = 1、doc_root_path / doc_root_path_mac
- cases: case_code (R{令和2桁}02{連番4桁})、case_name (事件名)、case_type、status、
  folder_path、is_deleted など
- persons: 関与者マスタ (last_name, first_name, corp_name, attribute)
- case_persons: 事件と関与者の紐付け (role='依頼者' AND role_order=1 が主たる依頼者)

実行:
    python -m tests.fixtures.build_mock_ksystemz_db
        → ~/k-file-test-data/ksystemz.db を (再) 生成

リポジトリには ksystemz.db を含めない (.gitignore で除外)。このスクリプトの
出力ファイルは dev 環境ローカル限定。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# 既存テストフォルダ (~/k-file-test-data/事件/R0602004x ...) と整合する case_code。
# 同一案件で 1 件追加 (R060200045) してタブ未追加状態の動作確認用にする。
_MOCK_CASES: list[dict] = [
    # (case_code, case_type, status, case_name, 依頼者属性, 姓, 名, 法人名)
    {
        "case_code": "R060200042", "case_type": "民事",
        "status": "進行中", "case_name": "損害賠償",
        "p_attribute": "個人", "p_last": "山田", "p_first": "太郎",
        "p_corp": None,
    },
    {
        "case_code": "R060200043", "case_type": "民事",
        "status": "進行中", "case_name": "売買代金",
        "p_attribute": "法人", "p_last": None, "p_first": None,
        "p_corp": "㈱A商事",
    },
    {
        "case_code": "R060200044", "case_type": "家事",
        "status": "申立準備中", "case_name": "離婚",
        "p_attribute": "個人", "p_last": "鈴木", "p_first": "花子",
        "p_corp": None,
    },
    {
        "case_code": "R060200045", "case_type": "民事",
        "status": "受任予定", "case_name": "貸金返還請求",
        "p_attribute": "個人", "p_last": "佐藤", "p_first": "次郎",
        "p_corp": None,
    },
    {
        "case_code": "R060200046", "case_type": "刑事",
        "status": "終了", "case_name": "傷害被告事件",
        "p_attribute": "個人", "p_last": "高橋", "p_first": "三郎",
        "p_corp": None,
    },
    # 顧問・諸件は active_only=False のテスト用 (実 K-SystemZ で除外される条件)
    {
        "case_code": "R060200047", "case_type": "顧問",
        "status": "進行中", "case_name": "顧問契約",
        "p_attribute": "法人", "p_last": None, "p_first": None,
        "p_corp": "㈱B工業",
    },
]

# 引き継ぎ書 v22 スキーマ (k-file が読む最小集合 + 周辺)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS office_info (
    id                INTEGER PRIMARY KEY DEFAULT 1,
    office_name       TEXT,
    doc_root_path     TEXT,           -- Windows 用ルートパス
    doc_root_path_mac TEXT,           -- Mac 用 (v22 追加)
    doc_subfolders    TEXT,
    updated_at        TIMESTAMP
);
CREATE TABLE IF NOT EXISTS cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_code   TEXT UNIQUE NOT NULL,
    case_name   TEXT,
    case_type   TEXT,
    status      TEXT,
    folder_path TEXT,                  -- 旧仕様の格納パス (k-file は使わない)
    is_deleted  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS persons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_code TEXT UNIQUE,
    attribute   TEXT,                  -- '個人' / '法人' / '裁判所' 等
    last_name   TEXT,
    first_name  TEXT,
    corp_name   TEXT,
    is_deleted  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS case_persons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES persons(id),
    role        TEXT,                  -- '依頼者' / '相手方' / '裁判所' 等
    role_order  INTEGER DEFAULT 1,     -- 主たる依頼者は role='依頼者' AND role_order=1
    position    TEXT
);
"""


def _detect_doc_root() -> Path:
    """既存テストフォルダの親 = doc_root_path として使う。"""
    candidate = Path.home() / "k-file-test-data" / "事件"
    if candidate.is_dir():
        return candidate
    # 自動生成しない (フォルダがないなら手動で用意する前提)
    return candidate


def build(db_path: Path | None = None) -> Path:
    """モック ksystemz.db を生成。既存ファイルがあれば一旦削除して作り直す。"""
    if db_path is None:
        db_path = Path.home() / "k-file-test-data" / "ksystemz.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA)
        conn.execute("PRAGMA foreign_keys = ON")

        doc_root = _detect_doc_root()
        conn.execute(
            "INSERT INTO office_info (id, office_name, doc_root_path, "
            "doc_root_path_mac, doc_subfolders) VALUES (?, ?, ?, ?, ?)",
            (
                1,
                "(モック) k-file dev 法律事務所",
                str(doc_root),
                str(doc_root),    # Linux dev では Mac と同一パスでよい
                "1_文書,2_発信,3_受信,4_資料,5_申立書類,6_訟務資料",
            ),
        )

        for i, c in enumerate(_MOCK_CASES, start=1):
            # cases
            conn.execute(
                "INSERT INTO cases (case_code, case_name, case_type, status) "
                "VALUES (?, ?, ?, ?)",
                (c["case_code"], c["case_name"], c["case_type"], c["status"]),
            )
            case_id = conn.execute(
                "SELECT id FROM cases WHERE case_code = ?",
                (c["case_code"],),
            ).fetchone()[0]

            # persons (依頼者を 1 件追加)
            conn.execute(
                "INSERT INTO persons (person_code, attribute, last_name, "
                "first_name, corp_name) VALUES (?, ?, ?, ?, ?)",
                (f"P{i:06d}", c["p_attribute"], c["p_last"], c["p_first"], c["p_corp"]),
            )
            person_id = conn.execute(
                "SELECT id FROM persons WHERE person_code = ?",
                (f"P{i:06d}",),
            ).fetchone()[0]

            # case_persons (役割 = 依頼者、順位 = 1)
            conn.execute(
                "INSERT INTO case_persons (case_id, person_id, role, role_order) "
                "VALUES (?, ?, ?, ?)",
                (case_id, person_id, "依頼者", 1),
            )

        conn.commit()
    finally:
        conn.close()
    return db_path


def main() -> int:
    path = build()
    print(f"モック ksystemz.db を生成: {path}")
    print(f"  cases: {len(_MOCK_CASES)} 件")
    print(f"  doc_root_path: {_detect_doc_root()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
