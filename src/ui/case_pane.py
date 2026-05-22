"""中央 事件フォルダペイン (案件タブを内包・sunken 枠)

レイアウト (上から):
  ┌── ペインタイトル「参照フォルダ」───────────────┐
  ├── 事件タブ (この pane の上部) ─────────────────┤
  ├── 事件フォルダ: R060200042 山田太郎 (ペイン全幅) ┤
  ├──────────────┬───────────────────────────────┤
  │  1 文書 (2)  │ Name      更新       サイズ      │
  │  2 発信 (1)  │ • 受領書.pdf 5-20    2.3MB       │
  │  3 受信 (5)  │ ...                              │
  │  4 資料      │                                  │
  │  5 申立      │                                  │
  │  6 訟務(12)  │                                  │
  │  0 直下 (3)  │  ← 事件フォルダ直下のファイル     │
  └──────────────┴───────────────────────────────┘

サブフォルダボタンの操作:
  - 左クリック       … そのサブフォルダの中身を表示 (閲覧のみ・移動なし)
  - Alt+0〜9         … 選択中の Inbox ファイルを投入 (実投入は M3)
  - 右クリックメニュー … D&D 以外のマウス投入手段
Alt キー割当: 0 = 事件フォルダ直下 / 1〜9 = サブフォルダ先頭 9 個。
10 個目以降のサブフォルダは Alt 割当なし (番号も付かずクリック専用)。

ペイン左右に sunken (くぼみ) の縦枠を付けて Inbox / Preview と視覚的に分離する
(上下の枠は PaneHeader の彫り込み線が担うため撤去)。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.pane_header import PaneHeader

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
# 事件フォルダ直下 (どのサブフォルダにも入っていない) ファイル
DUMMY_FILES_ROOT: list[tuple[str, str, str]] = [
    ("方針メモ.txt", "2026-05-21", "4KB"),
    ("名刺_相手方代理人.pdf", "2026-05-20", "180KB"),
    ("未分類スキャン.pdf", "2026-05-18", "920KB"),
]

# ビュー ID: 0〜5 = サブフォルダ (Alt+1〜6) / ROOT_VIEW_ID = 事件フォルダ直下
ROOT_VIEW_ID = 6


class CasePane(QWidget):
    # 左クリック = 閲覧 (ファイルは動かさない)
    subfolderBrowsed = Signal(int, str)          # (idx, folder_name)
    # Alt+1〜6 / 右クリックメニュー = 投入要求 (実投入は M3)
    subfolderInjectRequested = Signal(int, str)  # (idx, folder_name)
    caseTabChanged = Signal(int, str, str)       # 事件タブ切替 (idx, code, name)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("casePane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 右クリック投入メニューが Inbox の選択ファイルを問い合わせる getter
        self._inbox_file_getter = None

        outer = QVBoxLayout(self)
        # 上下マージン 0: #casePane の上下枠を撤去したので左右のみ内側余白。
        # これで見出しの上端が左右ペインと揃う。
        outer.setContentsMargins(3, 0, 3, 0)
        outer.setSpacing(0)

        # ── 上端: ペインタイトル (見出し + 彫り込み下線。3 ペイン共通) ──
        outer.addWidget(PaneHeader("参照フォルダ"))

        # ── 事件タブ ──
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

        # ── 事件フォルダパス: ペイン全幅 (事件タブ左端〜右端まで) ──
        # F1〜F6 ボタン列の上にも被せるため right_col ではなく outer に置く。
        self.path_label = QLabel("事件フォルダ:  (事件未選択)")
        self.path_label.setObjectName("casePath")
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.path_label)

        # ── 下段: 左=F1〜F6 / 右=テーブルヘッダ+ファイル一覧 ──
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(2)

        # サブフォルダ (Alt+1〜6) 縦ボタン。上の空白は入れず mid 上端から
        # 詰めて配置し、右テーブルと上端を揃える。ボタン間も詰める (spacing 0)。
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(0)
        self.folder_btns: list[QPushButton] = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        for i, (name, count) in enumerate(DUMMY_SUBFOLDERS, start=1):
            btn_idx = i - 1
            # 先頭の数字 i は Alt+i のキー番号。フォルダ名の数字とは別概念
            # (欠番繰り上げ時は一致しないため明示表示する)。
            label = f"{i}  {name}" + (f"  ({count})" if count else "")
            btn = QPushButton(label)
            btn.setObjectName("folderBtn")
            btn.setCheckable(True)
            # 右クリック = 投入メニュー (左クリックは閲覧のみ・ファイルは動かさない)
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, x=btn_idx, b=btn: self._show_folder_menu(x, b, pos)
            )
            self.button_group.addButton(btn, btn_idx)
            self.folder_btns.append(btn)
            btn_col.addWidget(btn)

        # 「0  事件フォルダ直下」ボタン: どのサブフォルダにも入っていない
        # 事件フォルダ直下のファイルを表示する。番号 0 = Alt+0 で投入可。
        # 他のボタンと同じ高密度の並びに揃える (仕切り線なし)。
        root_count = len(DUMMY_FILES_ROOT)
        root_label = "0  事件フォルダ直下" + (f"  ({root_count})" if root_count else "")
        self.root_btn = QPushButton(root_label)
        self.root_btn.setObjectName("folderBtn")
        self.root_btn.setCheckable(True)
        self.root_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.root_btn.customContextMenuRequested.connect(
            lambda pos: self._show_folder_menu(ROOT_VIEW_ID, self.root_btn, pos)
        )
        self.button_group.addButton(self.root_btn, ROOT_VIEW_ID)
        btn_col.addWidget(self.root_btn)
        btn_col.addStretch(1)
        btn_container = QWidget()
        btn_container.setLayout(btn_col)
        btn_container.setMaximumWidth(140)
        mid.addWidget(btn_container)

        # 右カラム (テーブルのみ。パス表示は上部にペイン全幅で移動済み)
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)

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

        # 左クリック = 閲覧。Alt = 投入 (ボタンとは別系統のショートカット)。
        # Alt+0 = 事件フォルダ直下 / Alt+1〜9 = サブフォルダ先頭 9 個まで。
        # 10 個目以降のサブフォルダは Alt 割当なし (クリック専用)。
        self.button_group.idClicked.connect(self._on_folder_browse)
        sc_root = QShortcut(QKeySequence("Alt+0"), self)
        sc_root.activated.connect(lambda: self._on_subfolder_inject(ROOT_VIEW_ID))
        for btn_idx in range(min(len(self.folder_btns), 9)):
            sc = QShortcut(QKeySequence(f"Alt+{btn_idx + 1}"), self)
            sc.activated.connect(lambda i=btn_idx: self._on_subfolder_inject(i))

        # 初期表示
        code, name = DUMMY_CASE_TABS[0]
        self.set_case(code, name)
        self._browse(2)

    def set_case(self, case_code: str, case_name: str) -> None:
        self.path_label.setText(f"事件フォルダ:  {case_code}  {case_name}")

    def _on_case_tab_changed(self, idx: int) -> None:
        if 0 <= idx < len(DUMMY_CASE_TABS):
            code, name = DUMMY_CASE_TABS[idx]
            self.set_case(code, name)
            self.caseTabChanged.emit(idx, code, name)

    def _on_case_tab_close(self, idx: int) -> None:
        self.case_tabs.removeTab(idx)

    def set_inbox_file_getter(self, getter) -> None:
        """右クリック投入メニューが Inbox の選択ファイル名を問い合わせる getter。

        getter() は選択中ファイル名 (str)、未選択なら None を返すこと。
        """
        self._inbox_file_getter = getter

    def _view_button(self, idx: int) -> QPushButton | None:
        """ビュー idx のボタン (0〜5=サブフォルダ / ROOT_VIEW_ID=事件フォルダ直下)。"""
        if idx == ROOT_VIEW_ID:
            return self.root_btn
        if 0 <= idx < len(self.folder_btns):
            return self.folder_btns[idx]
        return None

    def _view_name(self, idx: int) -> str:
        """ステータス通知・シグナル用のビュー名。"""
        if idx == ROOT_VIEW_ID:
            return "事件フォルダ直下"
        return DUMMY_SUBFOLDERS[idx][0]

    def _dummy_files(self, idx: int) -> list[tuple[str, str, str]]:
        """M1 ダミーのファイル一覧。M2 で実フォルダ読込に置き換える。"""
        if idx == ROOT_VIEW_ID:
            return DUMMY_FILES_ROOT
        if idx == 2:
            return DUMMY_FILES_RECEIVED
        if idx == 5:
            return DUMMY_FILES_LITIGATION
        return []

    def _browse(self, idx: int) -> None:
        """ビュー idx の中身を表示する (閲覧のみ・ファイルは動かさない)。"""
        btn = self._view_button(idx)
        if btn is None:
            return
        btn.setChecked(True)
        self._populate(self._dummy_files(idx))

    def _on_folder_browse(self, idx: int) -> None:
        """ボタン左クリック: 閲覧のみ。投入は一切行わない。"""
        self._browse(idx)
        self.subfolderBrowsed.emit(idx, self._view_name(idx))

    def _on_subfolder_inject(self, idx: int) -> None:
        """Alt+1〜6 / 右クリックメニュー: 投入要求 (実投入は M3)。"""
        if self._view_button(idx) is None:
            return
        self.subfolderInjectRequested.emit(idx, self._view_name(idx))
        # 投入先の中身を表示して、ファイルが入ったことを可視化する
        self._browse(idx)

    def _show_folder_menu(self, idx: int, btn: QPushButton, pos) -> None:
        """サブフォルダボタンの右クリックメニュー (D&D 以外のマウス投入手段)。"""
        menu = QMenu(self)
        inbox_file = self._inbox_file_getter() if self._inbox_file_getter else None
        if inbox_file:
            act = menu.addAction(f"「{inbox_file}」を ここへ投入")
            act.triggered.connect(lambda: self._on_subfolder_inject(idx))
        else:
            act = menu.addAction("投入する Inbox ファイルが未選択")
            act.setEnabled(False)
        menu.exec(btn.mapToGlobal(pos))

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
