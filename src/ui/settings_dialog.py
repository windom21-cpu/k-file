"""ツール → 設定… ダイアログ。

ユーザーが編集できる設定:
- Inbox 監視先 (label / path / cutoff_days) — 複数行のテーブル
- ksystemz.db のパス — RO で参照する K-SystemZ DB の場所
- kfile.db の場所 — 情報表示 (固定、変更不可)

設定値は `kfile.db.settings` テーブルに JSON / 文字列で保存。MainWindow が
ダイアログ accept 後に Inbox / CaseRepo を再構築する。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.core.inbox_watcher import InboxSource
from src.infra.kfile_db import KFileDB
from src.ui.title_bar import TitleBar


# settings table のキー名 (永続化に使う)
KEY_INBOX_SOURCES = "inbox_sources_json"
KEY_KSYSTEMZ_DB = "ksystemz_db_path"


def load_inbox_sources(db: KFileDB) -> list[InboxSource] | None:
    """settings から Inbox 監視先を復元。未設定なら None (呼び出し側で既定使用)。"""
    raw = db.get_setting(KEY_INBOX_SOURCES, "") or ""
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return [
            InboxSource(
                label=d["label"],
                path=Path(d["path"]),
                cutoff_days=d.get("cutoff_days"),
            )
            for d in data
        ]
    except (ValueError, KeyError, TypeError):
        return None


def save_inbox_sources(db: KFileDB, sources: list[InboxSource]) -> None:
    data = [
        {"label": s.label, "path": str(s.path), "cutoff_days": s.cutoff_days}
        for s in sources
    ]
    db.set_setting(KEY_INBOX_SOURCES, json.dumps(data, ensure_ascii=False))


class SettingsDialog(QDialog):
    """Win95 風 frameless モーダル。Inbox 監視先 + ksystemz.db 設定を編集。"""

    def __init__(
        self,
        db: KFileDB,
        current_sources: list[InboxSource],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("renameDialog")     # raised 外縁 QSS 流用
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.resize(620, 460)

        self._db = db
        self._sources: list[InboxSource] = list(current_sources)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        title = TitleBar(self, minimal=True)
        title.set_title("設定")
        outer.addWidget(title)

        body = QVBoxLayout()
        body.setContentsMargins(10, 8, 10, 8)
        body.setSpacing(8)

        # ── Inbox 監視先 ──
        body.addWidget(self._h2("Inbox 監視先"))
        body.addWidget(QLabel(
            "監視するフォルダの一覧。同じラベルは Inbox の同じタブにまとめて表示されます。\n"
            "「古さ制限」(日数) を入れると、それより古い更新日時のファイルは隠れます (空欄=全件)。"
        ))

        self._src_table = QTableWidget(0, 3)
        self._src_table.setHorizontalHeaderLabels(["ラベル", "パス", "古さ制限 (日)"])
        self._src_table.verticalHeader().setVisible(False)
        self._src_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._src_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._src_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        hdr = self._src_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self._src_table.setColumnWidth(0, 90)
        self._src_table.setColumnWidth(2, 90)
        body.addWidget(self._src_table, stretch=1)

        src_btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 追加")
        add_btn.clicked.connect(self._on_add_source)
        src_btn_row.addWidget(add_btn)
        del_btn = QPushButton("− 削除")
        del_btn.clicked.connect(self._on_remove_source)
        src_btn_row.addWidget(del_btn)
        browse_btn = QPushButton("選択行のパスを参照...")
        browse_btn.clicked.connect(self._on_browse_source_path)
        src_btn_row.addWidget(browse_btn)
        src_btn_row.addStretch(1)
        body.addLayout(src_btn_row)

        body.addWidget(self._sep())

        # ── ksystemz.db パス ──
        body.addWidget(self._h2("ksystemz.db のパス (読み取り専用で参照)"))
        ks_row = QHBoxLayout()
        self._ks_edit = QLineEdit(db.get_setting(KEY_KSYSTEMZ_DB, "") or "")
        self._ks_edit.setPlaceholderText("(未設定。ファイル→事件を開く で必要)")
        ks_row.addWidget(self._ks_edit, stretch=1)
        ks_browse = QPushButton("参照...")
        ks_browse.clicked.connect(self._on_browse_ksystemz)
        ks_row.addWidget(ks_browse)
        body.addLayout(ks_row)

        body.addWidget(self._sep())

        # ── kfile.db の場所 (情報表示) ──
        from src.infra.kfile_db import default_db_path
        body.addWidget(self._h2("kfile.db の場所 (情報のみ・変更不可)"))
        kf_label = QLineEdit(str(default_db_path()))
        kf_label.setReadOnly(True)
        body.addWidget(kf_label)

        # ── OK / キャンセル ──
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._ok_btn = QPushButton("OK")
        self._ok_btn.setDefault(True)
        self._ok_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._ok_btn)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        body.addLayout(btn_row)

        outer.addLayout(body)

        esc = QShortcut(QKeySequence("Escape"), self)
        esc.activated.connect(self.reject)

        self._populate_sources_table()

    # ───────── helpers ─────────

    def _h2(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: #000080;")
        return lbl

    def _sep(self) -> QFrame:
        sep = QFrame()
        sep.setObjectName("etchedLine")
        sep.setFixedHeight(2)
        return sep

    def _populate_sources_table(self) -> None:
        self._src_table.setRowCount(len(self._sources))
        for r, src in enumerate(self._sources):
            self._src_table.setItem(r, 0, QTableWidgetItem(src.label))
            self._src_table.setItem(r, 1, QTableWidgetItem(str(src.path)))
            cd = "" if src.cutoff_days is None else str(src.cutoff_days)
            self._src_table.setItem(r, 2, QTableWidgetItem(cd))
            self._src_table.setRowHeight(r, 18)

    def _collect_sources_from_table(self) -> list[InboxSource]:
        """テーブルの現状を InboxSource リストにシリアライズ。"""
        out: list[InboxSource] = []
        for r in range(self._src_table.rowCount()):
            label_item = self._src_table.item(r, 0)
            path_item = self._src_table.item(r, 1)
            cd_item = self._src_table.item(r, 2)
            if label_item is None or path_item is None:
                continue
            label = label_item.text().strip()
            path = path_item.text().strip()
            if not label or not path:
                continue
            cd_text = cd_item.text().strip() if cd_item is not None else ""
            cd: int | None = None
            if cd_text:
                try:
                    cd = int(cd_text)
                except ValueError:
                    cd = None
            out.append(InboxSource(label=label, path=Path(path), cutoff_days=cd))
        return out

    # ───────── 操作 ─────────

    def _on_add_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "監視するフォルダを選択")
        if not path:
            return
        # ラベル既定: scan/Desktop/作業 を頻出ヒントとして簡易判定
        lower = path.lower()
        if "desktop" in lower or "デスクトップ" in path:
            label = "Desktop"
        elif "scan" in lower or "スキャン" in path:
            label = "scan"
        else:
            label = "作業"
        # 末尾行に追加 (ユーザーがラベル/cutoff を後から編集)
        r = self._src_table.rowCount()
        self._src_table.insertRow(r)
        self._src_table.setItem(r, 0, QTableWidgetItem(label))
        self._src_table.setItem(r, 1, QTableWidgetItem(path))
        cd_default = "7" if label == "Desktop" else ""
        self._src_table.setItem(r, 2, QTableWidgetItem(cd_default))
        self._src_table.setRowHeight(r, 18)
        self._src_table.setCurrentCell(r, 0)

    def _on_remove_source(self) -> None:
        r = self._src_table.currentRow()
        if r >= 0:
            self._src_table.removeRow(r)

    def _on_browse_source_path(self) -> None:
        r = self._src_table.currentRow()
        if r < 0:
            return
        cur = self._src_table.item(r, 1)
        start = cur.text() if cur else ""
        path = QFileDialog.getExistingDirectory(self, "フォルダを選択", start)
        if path:
            self._src_table.setItem(r, 1, QTableWidgetItem(path))

    def _on_browse_ksystemz(self) -> None:
        start = self._ks_edit.text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "ksystemz.db を選択",
            start,
            "SQLite (*.db);; All files (*)",
        )
        if path:
            self._ks_edit.setText(path)

    def _on_accept(self) -> None:
        # 検証してから保存
        new_sources = self._collect_sources_from_table()
        save_inbox_sources(self._db, new_sources)
        self._db.set_setting(KEY_KSYSTEMZ_DB, self._ks_edit.text().strip())
        self._sources = new_sources
        self.accept()

    def applied_sources(self) -> list[InboxSource]:
        """accept 後の保存済 sources (MainWindow が InboxPane.reload_sources に渡す)。"""
        return self._sources
