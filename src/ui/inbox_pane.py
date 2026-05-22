"""左 Inbox ペイン (ペインタイトル + 出所フィルタタブ + 統合ファイル一覧)

M2: ダミーを廃し core/inbox_watcher で監視対象フォルダの実ファイルを読み込む。
PDF + 画像のみ表示。出所フィルタタブ (全て / scan / Desktop / 作業)。
QFileSystemWatcher でフォルダ変更を検知し自動更新、F5 で手動更新。

「無視」: 右クリック →「この一覧から無視」で個別除外 (kfile.db に記録、実ファイル
は触らない)。表示メニューの「無視したファイルも表示」で再表示・解除できる。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QMenu,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.inbox_watcher import InboxFile, InboxWatcher
from src.infra.kfile_db import KFileDB
from src.ui.pane_header import PaneHeader

# M2 dev: Inbox 監視対象フォルダ。M5 で settings (kfile.db) から読むようにする。
_DEV_INBOX_SOURCES: list[tuple[str, Path]] = [
    ("scan", Path.home() / "k-file-test-data" / "inbox-scan"),
    ("Desktop", Path.home() / "k-file-test-data" / "inbox-desktop"),
    ("作業", Path.home() / "k-file-test-data" / "inbox-work"),
]

# フィルタタブ。"全て" 以外は出所ラベルと一致させる。
FILTER_TABS = ["全て", "scan", "Desktop", "作業"]

_IGNORED_FG = QColor("#808080")  # 無視ファイルを表示する際のグレー


class InboxPane(QWidget):
    inboxChanged = Signal(int)   # 無視を除いた実ファイル数 (ステータスバー用)
    fileSelected = Signal(str)   # 選択ファイルのパス (プレビュー用、未選択は "")

    def __init__(self, db: KFileDB, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._files: list[InboxFile] = []
        self._shown: list[InboxFile] = []   # 現在テーブルに出している行
        self._ignored: set[str] = set()     # 無視ファイルの絶対パス
        self._show_ignored = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 上端: ペインタイトル (見出し + 彫り込み下線。3 ペイン共通)
        outer.addWidget(PaneHeader("INBOX"))

        # 出所フィルタタブ
        self.filter_tabs = QTabBar()
        self.filter_tabs.setObjectName("filterTabBar")
        self.filter_tabs.setDrawBase(False)
        self.filter_tabs.setExpanding(False)
        for name in FILTER_TABS:
            self.filter_tabs.addTab(name)
        self.filter_tabs.currentChanged.connect(self._refresh_view)
        outer.addWidget(self.filter_tabs)

        # ファイル一覧 (Name + 出所、行高 14px)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Name", "出所"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(14)
        self.table.verticalHeader().setMinimumSectionSize(14)
        self.table.horizontalHeader().setFixedHeight(15)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(1, 56)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_file_menu)
        self.table.itemSelectionChanged.connect(self._on_selection)
        outer.addWidget(self.table, stretch=1)

        # 監視対象フォルダを QFileSystemWatcher で監視 (変更で自動更新)
        self._watcher = InboxWatcher(_DEV_INBOX_SOURCES, self)
        self._watcher.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """監視対象フォルダを再走査して一覧を更新 (F5 / 自動更新)。"""
        self._ignored = self._db.ignored_paths()
        self._files = self._watcher.list_files()
        self._refresh_view()

    def set_show_ignored(self, on: bool) -> None:
        """「無視したファイルも表示」トグル (表示メニュー)。"""
        self._show_ignored = on
        self._refresh_view()

    def _refresh_view(self) -> None:
        """無視フィルタ + 出所フィルタを適用して表示を更新する。"""
        idx = self.filter_tabs.currentIndex()
        tab = FILTER_TABS[idx] if 0 <= idx < len(FILTER_TABS) else "全て"
        if self._show_ignored:
            pool = list(self._files)
        else:
            pool = [f for f in self._files if str(f.path) not in self._ignored]
        if tab != "全て":
            pool = [f for f in pool if f.source == tab]
        # Inbox は新しいファイルを上に (更新日時の降順)
        pool.sort(key=lambda f: f.mtime, reverse=True)
        self._shown = pool
        self._populate(pool)
        self.inboxChanged.emit(self.file_count())

    def _populate(self, files: list[InboxFile]) -> None:
        self.table.setRowCount(len(files))
        for r, f in enumerate(files):
            ignored = str(f.path) in self._ignored
            name_item = QTableWidgetItem(f.name)
            src_item = QTableWidgetItem(f.source)
            src_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if ignored:  # 無視ファイル (表示モード時) はグレー
                name_item.setForeground(_IGNORED_FG)
                src_item.setForeground(_IGNORED_FG)
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, src_item)
            self.table.setRowHeight(r, 14)

    def _show_file_menu(self, pos) -> None:
        """Inbox ファイルの右クリックメニュー (無視 / 無視を解除)。"""
        row = self.table.indexAt(pos).row()
        if not 0 <= row < len(self._shown):
            return
        f = self._shown[row]
        menu = QMenu(self)
        if str(f.path) in self._ignored:
            act = menu.addAction("無視を解除")
            act.triggered.connect(lambda: self._set_ignored(f, False))
        else:
            act = menu.addAction("この一覧から無視")
            act.triggered.connect(lambda: self._set_ignored(f, True))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _set_ignored(self, f: InboxFile, ignore: bool) -> None:
        if ignore:
            self._db.add_ignored(str(f.path))
        else:
            self._db.remove_ignored(str(f.path))
        self.refresh()

    def _on_selection(self) -> None:
        """行選択が変わったら選択ファイルのパスを通知 (プレビュー用)。"""
        row = self.table.currentRow()
        if 0 <= row < len(self._shown):
            self.fileSelected.emit(str(self._shown[row].path))
        else:
            self.fileSelected.emit("")

    def file_count(self) -> int:
        """無視を除いた実ファイル数 (ステータスバーの「Inbox N 件」用)。"""
        return sum(
            1 for f in self._files if str(f.path) not in self._ignored
        )

    def selected_file_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None
