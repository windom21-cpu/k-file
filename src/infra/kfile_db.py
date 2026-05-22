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

    def close(self) -> None:
        self._conn.close()
