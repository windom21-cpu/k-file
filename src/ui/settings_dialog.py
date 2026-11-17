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
    QCheckBox,
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
from src.core.quick_launch import (
    MAX_QUICK_FOLDERS,
    QuickFolder,
    load_quick_folders,
    save_quick_folders,
    slot_name,
)
from src.infra.kfile_db import KFileDB
from src.ui._font_strategy import apply_bitmap_font_strategy
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
        # 9pt ダイアログサイズ。Inbox 監視先テーブルが既定 4 件 + α 追加可能で
        # スクロール無しで見える程度の高さを確保 (クイック起動の一覧/各種パス含む)
        self.resize(620, 780)

        self._db = db
        self._sources: list[InboxSource] = list(current_sources)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)   # raised 外縁 2px と重ならないため
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
        # 既定 4 件 + 数件の追加余地までスクロール無しで見える高さを保証
        # (ヘッダー 22 + 6 行 × 18 + ボーダー余裕 = ~140px)
        self._src_table.setMinimumHeight(160)
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

        # ── クイック起動フォルダ (F6〜F9 / Shift+F キー) ──
        body.addWidget(self._h2("クイック起動フォルダ (ファンクションキー 1 発で開く)"))
        body.addWidget(QLabel(
            "事件外で常用するフォルダ。上から順に F6 / F7 / F8 / F9、5 件目からは\n"
            "Shift+F6 … に割り当たります (↑↓ で並べ替え)。表示名は全角 4 文字程度が目安。"
        ))
        self._quick_table = QTableWidget(0, 3)
        self._quick_table.setHorizontalHeaderLabels(["キー", "表示名", "フォルダ"])
        self._quick_table.verticalHeader().setVisible(False)
        self._quick_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._quick_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self._quick_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        qhdr = self._quick_table.horizontalHeader()
        qhdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        qhdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        qhdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._quick_table.setColumnWidth(0, 70)
        self._quick_table.setColumnWidth(1, 100)
        # ヘッダー + 5 行程度がスクロール無しで見える高さ
        self._quick_table.setMinimumHeight(120)
        body.addWidget(self._quick_table, stretch=1)

        quick_btn_row = QHBoxLayout()
        q_add = QPushButton("+ 追加")
        q_add.clicked.connect(self._on_add_quick)
        quick_btn_row.addWidget(q_add)
        q_del = QPushButton("− 削除")
        q_del.clicked.connect(self._on_remove_quick)
        quick_btn_row.addWidget(q_del)
        q_up = QPushButton("↑ 上へ")
        q_up.clicked.connect(lambda: self._on_move_quick(-1))
        quick_btn_row.addWidget(q_up)
        q_down = QPushButton("↓ 下へ")
        q_down.clicked.connect(lambda: self._on_move_quick(1))
        quick_btn_row.addWidget(q_down)
        q_browse = QPushButton("選択行のフォルダを参照...")
        q_browse.clicked.connect(self._on_browse_quick)
        quick_btn_row.addWidget(q_browse)
        quick_btn_row.addStretch(1)
        body.addLayout(quick_btn_row)

        body.addWidget(self._sep())

        # ── kfile.db の場所 (情報表示) ──
        from src.infra.kfile_db import default_db_path
        body.addWidget(self._h2("kfile.db の場所 (情報のみ・変更不可)"))
        kf_label = QLineEdit(str(default_db_path()))
        kf_label.setReadOnly(True)
        body.addWidget(kf_label)

        body.addWidget(self._sep())

        # ── 自動アップデート ──
        body.addWidget(self._h2("自動アップデート"))
        body.addWidget(QLabel(
            "起動時に GitHub Releases をチェックして新版があれば通知します。\n"
            "通知から「更新...」をクリックすると DL → 再起動 → 新版に切替わります。"
        ))
        self._auto_update_cb = QCheckBox("起動時にアップデートを確認する")
        self._auto_update_cb.setChecked(
            (db.get_setting("auto_update_check_enabled", "1") or "1") == "1"
        )
        body.addWidget(self._auto_update_cb)

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
        self._populate_quick_table(load_quick_folders(db.get_setting))
        # 本体と同じ MS Gothic ビットマップ戦略を適用 (新規ダイアログは
        # 別 widget tree なので main.py の初期適用範囲外)
        apply_bitmap_font_strategy(self, point_size=9)

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

    # ───────── クイック起動フォルダ ─────────

    def _populate_quick_table(self, folders: list[QuickFolder]) -> None:
        self._quick_table.setRowCount(0)
        for q in folders:
            self._append_quick_row(q.label, q.path)

    def _append_quick_row(self, label: str, path: str) -> int:
        r = self._quick_table.rowCount()
        self._quick_table.insertRow(r)
        key_item = QTableWidgetItem(slot_name(r))
        # キー列は並び順から自動で決まる (編集不可)
        key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._quick_table.setItem(r, 0, key_item)
        self._quick_table.setItem(r, 1, QTableWidgetItem(label))
        self._quick_table.setItem(r, 2, QTableWidgetItem(path))
        self._quick_table.setRowHeight(r, 18)
        return r

    def _renumber_quick_keys(self) -> None:
        for r in range(self._quick_table.rowCount()):
            item = self._quick_table.item(r, 0)
            if item is not None:
                item.setText(slot_name(r))

    def _collect_quick_from_table(self) -> list[QuickFolder]:
        out: list[QuickFolder] = []
        for r in range(self._quick_table.rowCount()):
            label_item = self._quick_table.item(r, 1)
            path_item = self._quick_table.item(r, 2)
            label = label_item.text().strip() if label_item is not None else ""
            path = path_item.text().strip() if path_item is not None else ""
            if not label and not path:
                continue
            out.append(QuickFolder(label=label or Path(path).name, path=path))
        return out

    def _on_add_quick(self) -> None:
        if self._quick_table.rowCount() >= MAX_QUICK_FOLDERS:
            return
        path = QFileDialog.getExistingDirectory(
            self, "クイック起動に登録するフォルダを選択", str(Path.home())
        )
        if not path:
            return
        # 表示名の既定 = フォルダ名 (あとからダブルクリックで編集)
        r = self._append_quick_row(Path(path).name, path)
        self._quick_table.setCurrentCell(r, 1)

    def _on_remove_quick(self) -> None:
        r = self._quick_table.currentRow()
        if r >= 0:
            self._quick_table.removeRow(r)
            self._renumber_quick_keys()

    def _on_move_quick(self, delta: int) -> None:
        """選択行を上 (-1) / 下 (+1) へ。キー列は位置に固定で、中身だけ入れ替える。"""
        r = self._quick_table.currentRow()
        t = r + delta
        if r < 0 or not 0 <= t < self._quick_table.rowCount():
            return
        for col in (1, 2):
            a = self._quick_table.takeItem(r, col)
            b = self._quick_table.takeItem(t, col)
            self._quick_table.setItem(r, col, b)
            self._quick_table.setItem(t, col, a)
        self._quick_table.setCurrentCell(t, 1)

    def _on_browse_quick(self) -> None:
        r = self._quick_table.currentRow()
        if r < 0:
            return
        cur = self._quick_table.item(r, 2)
        start = (cur.text() if cur else "") or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "フォルダを選択", start)
        if path:
            self._quick_table.setItem(r, 2, QTableWidgetItem(path))

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
        save_quick_folders(self._db.set_setting, self._collect_quick_from_table())
        self._db.set_setting(
            "auto_update_check_enabled",
            "1" if self._auto_update_cb.isChecked() else "0",
        )
        self._sources = new_sources
        self.accept()

    def applied_sources(self) -> list[InboxSource]:
        """accept 後の保存済 sources (MainWindow が InboxPane.reload_sources に渡す)。"""
        return self._sources
