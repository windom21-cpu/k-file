"""左 Inbox ペイン (ペインタイトル + 出所フィルタタブ + ファイル一覧)"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from src.ui.pane_header import PaneHeader

DUMMY_INBOX: list[tuple[str, str]] = [
    ("scan_001.pdf", "scan"),
    ("scan_002.pdf", "scan"),
    ("FAX結果_20260521.pdf", "Desktop"),
    ("写真撮影報告書.pdf", "Desktop"),
    ("受領書スキャン.pdf", "作業"),
    ("連絡書草稿.pdf", "作業"),
    ("scan_003.pdf", "scan"),
]

FILTER_TABS: list[str] = ["全て", "scan", "Desktop", "作業"]


class InboxPane(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

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
        self.filter_tabs.currentChanged.connect(self._apply_filter)
        outer.addWidget(self.filter_tabs)

        # ファイル一覧 (Name 1 列、行高 14px 強制)
        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Name"])
        self.table.horizontalHeader().setVisible(False)  # 1 列で自明
        self.table.verticalHeader().setVisible(False)
        # 全行を 14px に固定 (Fixed モード + 後で setRowHeight)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(14)
        self.table.verticalHeader().setMinimumSectionSize(14)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        outer.addWidget(self.table, stretch=1)

        self._populate(DUMMY_INBOX)

    def _populate(self, rows: list[tuple[str, str]]) -> None:
        self.table.setRowCount(len(rows))
        for r, (name, _source) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setRowHeight(r, 14)

    def _apply_filter(self, idx: int) -> None:
        tab_name = FILTER_TABS[idx]
        if tab_name == "全て":
            self._populate(DUMMY_INBOX)
        else:
            self._populate([r for r in DUMMY_INBOX if r[1] == tab_name])

    def selected_file_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None
