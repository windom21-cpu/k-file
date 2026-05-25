"""k-file 専用 SQLite (kfile.db) ラッパー。

k-file 自身の状態 — 投入履歴・最近使った名前・無視ファイル・開いていたタブ・
設定 — を保持する。K-SystemZ DB とは別物で、必ずローカル (Dropbox 同期外) の
OS ごとの app data ディレクトリに置く。

infra 層: sqlite3 + pathlib のみ。Qt 非依存。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 全テーブルのスキーマ (HANDOVER §9)。M2 で作成、各テーブルは順次 M3〜M5 で使う。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS ignored_files (
    src_path   TEXT PRIMARY KEY,
    ignored_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drop_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    action        TEXT NOT NULL,
    src_path      TEXT,
    dst_path      TEXT,
    case_code     TEXT,
    category      TEXT,
    renamed_to    TEXT,
    original_name TEXT,
    status        TEXT,
    executed_at   TEXT NOT NULL,
    thumb_cache_path TEXT
);
CREATE TABLE IF NOT EXISTS recent_names (
    name         TEXT PRIMARY KEY,
    last_used_at TEXT NOT NULL,
    use_count    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS open_tabs (
    case_code      TEXT PRIMARY KEY,
    tab_order      INTEGER NOT NULL,
    last_opened_at TEXT NOT NULL
);
"""


def app_data_dir() -> Path:
    """OS ごとの k-file 専用データディレクトリ (Dropbox 同期外)。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "k-file"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "k-file"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "k-file"


def default_db_path() -> Path:
    return app_data_dir() / "kfile.db"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class KFileDB:
    """kfile.db への接続とアクセスをまとめるラッパー。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # autocommit (isolation_level=None): k-file の用途は単純なため
        self._conn = sqlite3.connect(str(self.path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # 単独プロセス前提だが、複数 instance 起動の過渡期 (M6b IPC 切替前等)
        # に備えて busy_timeout を設定 (ksystemz.db と同じ運用基準)。
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.executescript(_SCHEMA)

    # ───────── ignored_files (Inbox の「無視」フラグ) ─────────

    def add_ignored(self, src_path: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO ignored_files(src_path, ignored_at) "
            "VALUES (?, ?)",
            (src_path, _now()),
        )

    def remove_ignored(self, src_path: str) -> None:
        self._conn.execute(
            "DELETE FROM ignored_files WHERE src_path = ?", (src_path,)
        )

    def ignored_paths(self) -> set[str]:
        rows = self._conn.execute("SELECT src_path FROM ignored_files")
        return {r["src_path"] for r in rows}

    # ───────── settings (key/value) ─────────

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            (key, value),
        )

    # ───────── drop_history (投入・rename・削除・移動の履歴 / Undo の元) ─────────

    def record_history(
        self,
        action: str,
        src_path: str,
        dst_path: str | None,
        case_code: str,
        category: str,
        renamed_to: str,
        original_name: str,
        status: str = "ok",
    ) -> int:
        """履歴を 1 件追加し、付与された id を返す。

        action は "inject" / "move" / "rename" / "trash" のいずれか。M4 の Undo
        ではこの id を逆順に辿って逆操作を実行する。
        """
        cur = self._conn.execute(
            "INSERT INTO drop_history "
            "(action, src_path, dst_path, case_code, category, renamed_to, "
            " original_name, status, executed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (action, src_path, dst_path, case_code, category, renamed_to,
             original_name, status, _now()),
        )
        return int(cur.lastrowid or 0)

    def recent_history(self, limit: int = 50) -> list[sqlite3.Row]:
        """新しい順に履歴を取得 (M4 の F12 履歴ビュー用)。"""
        rows = self._conn.execute(
            "SELECT * FROM drop_history ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return list(rows)

    def last_undoable_entry(self) -> sqlite3.Row | None:
        """Ctrl+Z 対象: 最新の status='ok' な inject/move/rename 行。

        trash は OS ごみ箱からの復元動線が別 (Win では右クリック「元に戻す」)
        なので Ctrl+Z スタックから除外。F12 履歴ビューでは行ごとに表示する。
        """
        return self._conn.execute(
            "SELECT * FROM drop_history "
            "WHERE status = 'ok' AND action != 'trash' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def undoable_count(self) -> int:
        """Ctrl+Z で戻せる件数 (trash 除く)。"""
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM drop_history "
            "WHERE status = 'ok' AND action != 'trash'"
        ).fetchone()
        return int(row["c"]) if row else 0

    def mark_undone(self, entry_id: int) -> None:
        """履歴 1 行を status='undone' に更新 (Ctrl+Z 成功時に呼ぶ)。"""
        self._conn.execute(
            "UPDATE drop_history SET status = 'undone' WHERE id = ?",
            (entry_id,),
        )

    # ───────── recent_names (rename ダイアログの候補) ─────────

    def add_recent_name(self, name: str) -> None:
        """rename で使った名前を頻度カウント込みで記録。"""
        if not name:
            return
        row = self._conn.execute(
            "SELECT use_count FROM recent_names WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO recent_names(name, last_used_at, use_count) "
                "VALUES (?, ?, 1)",
                (name, _now()),
            )
        else:
            self._conn.execute(
                "UPDATE recent_names SET last_used_at = ?, use_count = ? "
                "WHERE name = ?",
                (_now(), int(row["use_count"]) + 1, name),
            )

    def recent_names(self, limit: int = 20) -> list[str]:
        """よく使う順 → 最近順 で候補を返す (rename ダイアログの combobox 用)。"""
        rows = self._conn.execute(
            "SELECT name FROM recent_names "
            "ORDER BY use_count DESC, last_used_at DESC LIMIT ?",
            (limit,),
        )
        return [r["name"] for r in rows]

    # ───────── open_tabs (セッション復元: 前回開いていた事件タブ) ─────────

    def open_tab_codes(self) -> list[str]:
        """前回保存された事件タブの case_code を順序通りに取得。"""
        rows = self._conn.execute(
            "SELECT case_code FROM open_tabs ORDER BY tab_order ASC"
        )
        return [r["case_code"] for r in rows]

    def save_open_tabs(self, case_codes: list[str]) -> None:
        """現在開いている事件タブの case_code 群で open_tabs を置き換える。"""
        self._conn.execute("DELETE FROM open_tabs")
        for i, code in enumerate(case_codes):
            self._conn.execute(
                "INSERT INTO open_tabs (case_code, tab_order, last_opened_at) "
                "VALUES (?, ?, ?)", (code, i, _now()),
            )

    def close(self) -> None:
        self._conn.close()
