"""K-SystemZ の ksystemz.db を読み取り専用で参照する事件レポジトリ。

K-SystemZ は別アプリ (FastAPI+React+SQLite) で、k-file から見ると **データ源**。
書き込みは絶対禁止 (`mode=ro` URI 接続)。Dropbox 同期下にあるため Win/Mac
間で共有されている。

提供する操作:
- doc_root() — OS に応じた文書フォルダのルートパス (`office_info`)
- search(keyword, active_only) — 事件検索 (cases ⨯ case_persons ⨯ persons join)
- resolve_folder(case_code) — `doc_root/{case_code}*` 前方一致で実フォルダ解決
  (K-SystemZ の `GET /api/cases/{id}/open-folder` と同じロジック)

Qt 非依存・モック DB で完結テスト可能 (HANDOVER §15 ADR-14)。
"""
from __future__ import annotations

import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CaseRecord:
    """事件 1 件の表示用レコード (open ダイアログ等で扱う)。"""

    case_code: str
    case_name: str           # 「損害賠償」「離婚」等
    case_type: str           # 「民事」「家事」「刑事」「顧問」等
    status: str              # 「進行中」「申立準備中」「終了」「不受任」「諸件」「受任予定」等
    client_display: str      # 主たる依頼者の表示名 (個人=姓名 / 法人=法人名 / 不在は空)

    def display_label(self) -> str:
        """open ダイアログ等で 1 行表示する文字列。"""
        return f"{self.case_code}  {self.client_display}  {self.case_name}"


# K-SystemZ の「現在進行中」フィルタ条件 (引き継ぎ書 §4 より)
_ACTIVE_WHERE = (
    "c.status NOT IN ('不受任', '諸件', '終了') AND c.case_type != '顧問'"
)


def _ro_connect(path: Path) -> sqlite3.Connection:
    """sqlite3 を read-only URI で開く (Dropbox 同期下の書込事故防止)。

    K-SystemZ 側が write 中だと SQLITE_BUSY が瞬間的に発生するので
    busy_timeout=5000ms を設定して合計 5 秒間ロック解放を待つ
    (K-SystemZ 側も同じ値を採用済み・2026-05-25 連携実装)。
    """
    if not path.is_file():
        raise FileNotFoundError(f"ksystemz.db が見つかりません: {path}")
    # `file:` URI + mode=ro。同名ファイル末尾の `?` は URI 解釈の問題を避けるため
    # as_posix() でなく str() で渡し、Windows のドライブレターパスも素直に通す。
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


class CaseRepo:
    """ksystemz.db への RO アクセサ。コンストラクタで接続を開く。"""

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._conn = _ro_connect(self._path)

    def close(self) -> None:
        self._conn.close()

    # ───────── office_info / doc_root ─────────

    def doc_root(self) -> Path:
        """OS に応じて doc_root_path (Win) or doc_root_path_mac (Mac/Linux) を返す。

        Linux dev では Mac 用パスを流用 (引き継ぎ書: Mac 値があれば優先)。
        どちらも空の場合は OSError。
        """
        row = self._conn.execute(
            "SELECT doc_root_path, doc_root_path_mac FROM office_info "
            "WHERE id = 1"
        ).fetchone()
        if row is None:
            raise OSError("office_info に id=1 のレコードがありません")
        if sys.platform == "win32":
            chosen = row["doc_root_path"] or row["doc_root_path_mac"]
        else:
            chosen = row["doc_root_path_mac"] or row["doc_root_path"]
        if not chosen:
            raise OSError("doc_root_path / doc_root_path_mac が両方とも空です")
        return Path(chosen)

    # ───────── 事件検索 ─────────

    def search(
        self, keyword: str = "", active_only: bool = True, limit: int = 200,
    ) -> list[CaseRecord]:
        """事件を検索。keyword は case_code / case_name / 姓名 / 法人名 に部分一致。

        active_only=True なら「現在進行中」フィルタ (K-SystemZ と同一条件)。
        """
        params: list = []
        where = ["c.is_deleted = 0"]

        if active_only:
            where.append(_ACTIVE_WHERE)

        if keyword:
            w = f"%{keyword}%"
            where.append(
                "(c.case_code LIKE ? OR c.case_name LIKE ? OR "
                " p.last_name LIKE ? OR p.first_name LIKE ? OR p.corp_name LIKE ?)"
            )
            params.extend([w] * 5)
        params.append(limit)

        sql = f"""
            SELECT
                c.case_code,
                c.case_name,
                c.case_type,
                c.status,
                COALESCE(
                    CASE
                        WHEN p.corp_name IS NOT NULL AND p.corp_name != ''
                        THEN p.corp_name
                        ELSE COALESCE(p.last_name, '') || COALESCE(p.first_name, '')
                    END,
                    ''
                ) AS client_display
            FROM cases c
            LEFT JOIN case_persons cp
                ON cp.case_id = c.id AND cp.role = '依頼者' AND cp.role_order = 1
            LEFT JOIN persons p
                ON p.id = cp.person_id AND p.is_deleted = 0
            WHERE {' AND '.join(where)}
            ORDER BY c.case_code DESC
            LIMIT ?
        """
        rows = self._conn.execute(sql, params).fetchall()
        return [
            CaseRecord(
                case_code=r["case_code"],
                case_name=r["case_name"] or "",
                case_type=r["case_type"] or "",
                status=r["status"] or "",
                client_display=r["client_display"] or "",
            )
            for r in rows
        ]

    # ───────── case_code → 実フォルダ解決 ─────────

    def resolve_folder(self, case_code: str) -> Path | None:
        """`doc_root` 直下を `{case_code}*` で前方一致して実フォルダを返す。

        K-SystemZ `GET /api/cases/{id}/open-folder` と同じロジック。
        - 複数候補は名前昇順の最初を採用 (実運用ではほぼ衝突しない、
          R060200042 と R0602000420 のような prefix 衝突は事務所内で発生しない命名)
        - 0 件 / doc_root が存在しない場合は None
        """
        if not case_code:
            return None
        try:
            root = self.doc_root()
        except OSError:
            return None
        if not root.is_dir():
            return None
        # macOS の readdir は名前を NFD (濁点分解) で返しうるため、両辺を NFC に
        # 揃えてから前方一致する (現行の case_code は ASCII だけだが、K-SystemZ 側の
        # 命名が将来かなを含んでも Mac だけ引けなくなることを防ぐ)
        needle = unicodedata.normalize("NFC", case_code)
        try:
            for p in sorted(root.iterdir(), key=lambda x: x.name):
                if p.is_dir() and unicodedata.normalize("NFC", p.name).startswith(needle):
                    return p
        except OSError:
            return None
        return None
