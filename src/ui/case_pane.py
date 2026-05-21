"""中央 事件フォルダペイン (案件タブを内包・sunken 枠)

レイアウト (上から):
  ┌── 事件タブ (この pane の上部) ─────────────────┐
  ├──────────────┬───────────────────────────────┤
  │  F1 文書 (2) │ 事件フォルダ                    │
  │  F2 発信 (1) │ R060200042 山田太郎              │
  │  F3 受信 (5) │ ────────────────────            │
  │  F4 資料     │ Name      更新       サイズ      │
  │  F5 申立     │ • 受領書.pdf 5-20    2.3MB       │
  │  F6 訟務(12) │ ...                              │
  └──────────────┴───────────────────────────────┘

ペイン全体に sunken (くぼみ) 枠を付けて左右の Inbox / Preview と視覚的に分離する。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

DUMMY_CASE_TABS: list[tuple[str, str]] = [
    ("R060200042", "山田太郎 損害賠償"),
    ("R060200043", "㈱A商事 売買代金"),
    ("R060200044", "鈴木花子 離婚"),
]

DUMMY_SUBFOLDERS: list[tuple[str, int]] = [
    ("1_文書", 2),
    ("2_発信", 1),
    ("3_受信", 5),
    ("4_資料", 0),
    ("5_申立書類", 0),
    ("6_訟務資料", 12),
]

DUMMY_FILES_RECEIVED: list[tuple[str, str, str]] = [
    ("受領書.pdf", "2026-05-20", "2.3MB"),
    ("連絡書_甲山.pdf", "2026-05-19", "1.1MB"),
    ("FAX結果_20260519.pdf", "2026-05-19", "340KB"),
    ("郵便スキャン_001.pdf", "2026-05-18", "5.8MB"),
    ("受領通知.pdf", "2026-05-17", "210KB"),
]
DUMMY_FILES_LITIGATION: list[tuple[str, str, str]] = [
    (f"訟務資料_{i:03d}.pdf", "2026-05-15", "1.2MB") for i in range(1, 13)
]


class CasePane(QWidget):
    subfolderInvoked = Signal(int, str)  # F1〜F6 押下時 (idx, folder_name)
    caseTabChanged = Signal(int, str, str)  # 事件タブ切替時 (idx, code, name)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("casePane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(3, 3, 3, 3)
        outer.setSpacing(0)

        # ── 上端: 事件タブ ──
        self.case_tabs = QTabBar()
        self.case_tabs.setObjectName("caseTabBar")
        self.case_tabs.setDrawBase(False)
        self.case_tabs.setExpanding(False)
        self.case_tabs.setTabsClosable(True)
        self.case_tabs.setMovable(True)
        self.case_tabs.setUsesScrollButtons(True)
        for code, name in DUMMY_CASE_TABS:
            self.case_tabs.addTab(f"{code} {name}")
        self.case_tabs.currentChanged.connect(self._on_case_tab_changed)
        self.case_tabs.tabCloseRequested.connect(self._on_case_tab_close)
        outer.addWidget(self.case_tabs)

        # ── 下段: 左=F1〜F6 / 右=ヘッダー+パス+ファイル一覧 ──
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(2)

        # F1〜F6 縦ボタン (右側「事件フォルダ」見出し + パス + テーブルヘッダの高さ分、
        # 上に空白を入れて、ボタンの位置をテーブル行 (Name 列) と揃える)
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(1)
        # 右カラムの 事件フォルダ:パス 1 行 (14) + テーブルヘッダ (15) ≒ 29px
        btn_col.addSpacing(29)
        self.folder_btns: list[QPushButton] = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        for i, (name, count) in enumerate(DUMMY_SUBFOLDERS, start=1):
            # ラベル先頭の "&i" で Alt+i を自動的にショートカット化 (mnemonic)
            label = f"&{i}  {name}" + (f"  ({count})" if count else "")
            btn = QPushButton(label)
            btn.setObjectName("folderBtn")
            btn.setCheckable(True)
            # 明示的にも Alt+i をセット (mnemonic と二重で安全)
            btn.setShortcut(QKeySequence(f"Alt+{i}"))
            self.button_group.addButton(btn, i - 1)
            self.folder_btns.append(btn)
            btn_col.addWidget(btn)
        btn_col.addStretch(1)
        btn_container = QWidget()
        btn_container.setLayout(btn_col)
        btn_container.setMaximumWidth(140)
        mid.addWidget(btn_container)

        # 右カラム
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)

        # 「事件フォルダ:」見出しとパスを 1 行に統合 (縦スペース節約)
        self.path_label = QLabel("事件フォルダ:  (事件未選択)")
        self.path_label.setObjectName("casePath")
        right_col.addWidget(self.path_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "更新", "サイズ"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(14)
        self.table.verticalHeader().setMinimumSectionSize(14)
        self.table.horizontalHeader().setFixedHeight(15)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 70)
        right_col.addWidget(self.table, stretch=1)

        right_container = QWidget()
        right_container.setLayout(right_col)
        mid.addWidget(right_container, stretch=1)

        outer.addLayout(mid, stretch=1)

        self.button_group.idClicked.connect(self._on_folder_clicked)

        # 初期表示
        code, name = DUMMY_CASE_TABS[0]
        self.set_case(code, name)
        self.folder_btns[2].setChecked(True)
        self._populate(DUMMY_FILES_RECEIVED)

    def set_case(self, case_code: str, case_name: str) -> None:
        self.path_label.setText(f"事件フォルダ:  {case_code}  {case_name}")

    def _on_case_tab_changed(self, idx: int) -> None:
        if 0 <= idx < len(DUMMY_CASE_TABS):
            code, name = DUMMY_CASE_TABS[idx]
            self.set_case(code, name)
            self.caseTabChanged.emit(idx, code, name)

    def _on_case_tab_close(self, idx: int) -> None:
        self.case_tabs.removeTab(idx)

    def _on_folder_clicked(self, idx: int) -> None:
        if idx == 2:
            self._populate(DUMMY_FILES_RECEIVED)
        elif idx == 5:
            self._populate(DUMMY_FILES_LITIGATION)
        else:
            self._populate([])
        name = DUMMY_SUBFOLDERS[idx][0]
        self.subfolderInvoked.emit(idx, name)

    def _populate(self, rows: list[tuple[str, str, str]]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, (name, date, size) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(name))
            item_date = QTableWidgetItem(date)
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 1, item_date)
            item_size = QTableWidgetItem(size)
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 2, item_size)
            self.table.setRowHeight(r, 14)
        self.table.setSortingEnabled(True)

    def current_case(self) -> tuple[str, str]:
        idx = self.case_tabs.currentIndex()
        if 0 <= idx < len(DUMMY_CASE_TABS):
            return DUMMY_CASE_TABS[idx]
        return ("?", "?")
