"""中央 事件フォルダペイン (案件タブを内包・左右 sunken 縦枠)

レイアウト (上から): ペインタイトル「参照フォルダ」/ 事件タブ / 事件フォルダ
パス兼パンくず (ペイン全幅) / 下段 = 左:サブフォルダボタン + 右:ファイル一覧。

M2: ダミーを廃し core/folder_scanner で実フォルダを読み込む。

ナビゲーション:
  - 左サブフォルダボタン   … 上位ビュー (1〜6 / 0 直下) を表示。左クリック=閲覧
  - 子フォルダ            … ファイル一覧に「行」として表示 (先頭にまとめる)。
                            ダブルクリックで中へ入る (数が多くてもスクロールで対応)
  - パンくず (パスバー)    … 各区切りクリックで上の階層へ戻る
  - Alt+0〜9 / 右クリック  … 投入 (実投入は M3)

ペイン左右に sunken の縦枠 (上下枠は PaneHeader の彫り込み線が担当)。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.folder_scanner import (
    CaseScan,
    FileEntry,
    list_files,
    list_folder,
    scan_case_folder,
)
from src.ui.pane_header import PaneHeader

# M2 dev: 事件フォルダの親 (doc_root)。M5 で ksystemz.db +「事件を開く」
# ダイアログ経由に置き換える。
_DEV_DOC_ROOT = Path.home() / "k-file-test-data" / "事件"

# 「事件フォルダ直下」ビューの ID (サブフォルダ index 0..N-1 と衝突しない値)
ROOT_VIEW_ID = 999


def format_size(n: int, unit: str = "KB") -> str:
    """バイト数を KB 統一 (既定) または MB 統一でフォーマット。

    InboxPane と同じフォーマット規約。ヘッダー右クリックで KB/MB 切替。
    """
    if unit == "MB":
        return f"{n / (1024 * 1024):.1f}MB"
    return f"{n // 1024}KB"


def _parse_case(path: Path) -> tuple[str, str]:
    """事件フォルダ名 'R060200042 山田太郎 損害賠償' → (code, name)。"""
    parts = path.name.split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return path.name, ""


class _NameItem(QTableWidgetItem):
    """Name 列セル: フォルダを先頭にまとめ、各々名前順でソートする。

    行がフォルダかどうか・実パスを保持し、ダブルクリック時の判定に使う。
    `..` 行 (is_parent=True) はフォルダの中でも別格で常に最先頭。
    """

    def __init__(
        self, name: str, is_dir: bool, path: Path, is_parent: bool = False
    ) -> None:
        super().__init__(name)
        self.is_dir = is_dir
        self.path = path
        self.is_parent = is_parent

    def __lt__(self, other: QTableWidgetItem) -> bool:
        # PySide6 では super().__lt__() が再帰しクラッシュするため Python 側で比較
        if isinstance(other, _NameItem):
            if self.is_parent != other.is_parent:
                return self.is_parent   # ".." 行は常に最先頭
            if self.is_dir != other.is_dir:
                return self.is_dir       # フォルダを先頭へ
        return self.text().casefold() < other.text().casefold()


class _SizeItem(QTableWidgetItem):
    """サイズ列セル: 表示は人間可読 (KB/MB)、ソートはバイト数で正しく行う。"""

    def __init__(self, size: int, unit: str = "KB") -> None:
        super().__init__(format_size(size, unit))
        self._size = size
        self.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

    def __lt__(self, other: QTableWidgetItem) -> bool:
        # super().__lt__() は PySide6 で再帰落ちするため使わない
        if isinstance(other, _SizeItem):
            return self._size < other._size
        return self.text() < other.text()


class CasePane(QWidget):
    # 左クリック = 閲覧 (ファイルは動かさない)
    subfolderBrowsed = Signal(int, str)          # (view_id, view_name)
    # Alt+0〜9 / 右クリックメニュー = 投入要求 (実投入は M3)
    subfolderInjectRequested = Signal(int, str)  # (view_id, view_name)
    caseTabChanged = Signal(int, str, str)       # (idx, code, name)
    fileSelected = Signal(str)                   # 選択ファイルのパス (プレビュー用)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("casePane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 右クリック投入メニューが Inbox の選択ファイルを問い合わせる getter
        self._inbox_file_getter = None
        self._scan: CaseScan | None = None
        self._case_paths: list[Path] = []
        self._case_code = ""
        self._case_name = ""
        # view_id -> ボタン。0..N-1=サブフォルダ / ROOT_VIEW_ID=事件フォルダ直下
        self._view_btns: dict[int, QPushButton] = {}
        self._cur_view_id = ROOT_VIEW_ID   # 左ボタンのどれを選択中か
        self._cur_dir: Path | None = None  # 実際に表示中のフォルダ
        # パンくず: (フォルダ名, パス) を上位サブフォルダ→現在フォルダの順で保持
        self._crumb: list[tuple[str, Path]] = []
        self._size_unit = "KB"  # サイズ列ヘッダー ᴹ/ᴷ でトグル
        self._dir_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_DirIcon
        )

        outer = QVBoxLayout(self)
        # 上下マージン 0: #casePane の上下枠は撤去済 (左右のみ内側余白)
        outer.setContentsMargins(3, 0, 3, 0)
        outer.setSpacing(0)

        # ── 上端: ペインタイトル ──
        outer.addWidget(PaneHeader("参照フォルダ"))

        # ── 事件タブ ──
        self.case_tabs = QTabBar()
        self.case_tabs.setObjectName("caseTabBar")
        self.case_tabs.setDrawBase(False)
        self.case_tabs.setExpanding(False)
        self.case_tabs.setTabsClosable(True)
        self.case_tabs.setMovable(True)
        self.case_tabs.setUsesScrollButtons(True)
        self.case_tabs.currentChanged.connect(self._on_case_tab_changed)
        self.case_tabs.tabCloseRequested.connect(self._on_case_tab_close)
        outer.addWidget(self.case_tabs)

        # ── 事件フォルダパス兼パンくず: ペイン全幅・中央揃え ──
        self.path_label = QLabel("事件フォルダ:  (事件未選択)")
        self.path_label.setObjectName("casePath")
        self.path_label.setTextFormat(Qt.TextFormat.RichText)
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.path_label.linkActivated.connect(self._on_crumb_click)
        outer.addWidget(self.path_label)

        # ── 下段: 左=サブフォルダボタン / 右=ファイル一覧 ──
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(2)

        # サブフォルダボタン列 (事件ごとに動的再構築)
        self.btn_col = QVBoxLayout()
        self.btn_col.setContentsMargins(0, 0, 0, 0)
        self.btn_col.setSpacing(0)
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.button_group.idClicked.connect(self._on_folder_browse)
        btn_container = QWidget()
        btn_container.setLayout(self.btn_col)
        btn_container.setMaximumWidth(140)
        mid.addWidget(btn_container)

        # 右カラム: ファイル一覧テーブル (子フォルダも行として表示)
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "更新", "サイズ"])
        self.table.setIconSize(QSize(13, 13))
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
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 70)
        self.table.cellDoubleClicked.connect(self._on_table_double_click)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        # ヘッダー右クリック (サイズ列のみ) → KB/MB 切替メニュー
        # 左クリックはソートに専念させる (役割が違うので分離 — ユーザー要望)
        hdr = self.table.horizontalHeader()
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._show_header_menu)
        right_col.addWidget(self.table, stretch=1)
        right_container = QWidget()
        right_container.setLayout(right_col)
        mid.addWidget(right_container, stretch=1)

        outer.addLayout(mid, stretch=1)

        # Alt = 投入 (左クリック=閲覧 とは別系統)。Alt+0=直下 / Alt+1〜9=サブフォルダ。
        sc_root = QShortcut(QKeySequence("Alt+0"), self)
        sc_root.activated.connect(lambda: self._on_subfolder_inject(ROOT_VIEW_ID))
        for k in range(1, 10):
            sc = QShortcut(QKeySequence(f"Alt+{k}"), self)
            sc.activated.connect(lambda key=k: self._on_subfolder_inject(key - 1))

        # 事件タブを実フォルダ (doc_root) から構築
        self._load_case_tabs()

    # ───────── 事件タブ ─────────

    def _load_case_tabs(self) -> None:
        """doc_root 直下の事件フォルダを走査してタブを作る。"""
        if _DEV_DOC_ROOT.is_dir():
            for p in sorted(_DEV_DOC_ROOT.iterdir(), key=lambda x: x.name):
                if p.is_dir():
                    self._case_paths.append(p)
        self.case_tabs.blockSignals(True)
        for path in self._case_paths:
            code, name = _parse_case(path)
            self.case_tabs.addTab(f"{code} {name}")
        self.case_tabs.blockSignals(False)
        if self._case_paths:
            self._load_case(0)

    def _load_case(self, idx: int) -> None:
        """事件タブ idx の事件フォルダを読み込み、サブフォルダボタンを再構築。"""
        if not 0 <= idx < len(self._case_paths):
            return
        path = self._case_paths[idx]
        self._scan = scan_case_folder(path)
        self._case_code, self._case_name = _parse_case(path)
        self._rebuild_subfolder_buttons()
        # 初期表示: 最初のサブフォルダ (無ければ事件フォルダ直下)
        if self._scan.subfolders:
            self._browse(0)
        else:
            self._browse(ROOT_VIEW_ID)

    def _on_case_tab_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._case_paths):
            self._load_case(idx)
            self.caseTabChanged.emit(idx, self._case_code, self._case_name)

    def _on_case_tab_close(self, idx: int) -> None:
        if 0 <= idx < len(self._case_paths):
            self._case_paths.pop(idx)
        self.case_tabs.removeTab(idx)

    # ───────── サブフォルダボタン (事件ごとに再構築) ─────────

    def _rebuild_subfolder_buttons(self) -> None:
        """現在の事件のサブフォルダボタン + 「0 事件フォルダ直下」を作り直す。"""
        while self.btn_col.count():
            item = self.btn_col.takeAt(0)
            w = item.widget()
            if w is not None:
                self.button_group.removeButton(w)
                w.deleteLater()
        self._view_btns = {}
        if self._scan is None:
            return

        for i, sf in enumerate(self._scan.subfolders):
            num = f"{sf.alt_key}  " if sf.alt_key is not None else ""
            badge = f"  ({sf.file_count})" if sf.file_count else ""
            btn = self._make_view_button(i, num + sf.name + badge)
            self.btn_col.addWidget(btn)
            self._view_btns[i] = btn

        # 「0 事件フォルダ直下」ボタン (どのサブフォルダにも入っていない直下ファイル)
        rc = len(self._scan.root_files)
        root_label = "0  事件フォルダ直下" + (f"  ({rc})" if rc else "")
        root_btn = self._make_view_button(ROOT_VIEW_ID, root_label)
        self.btn_col.addWidget(root_btn)
        self._view_btns[ROOT_VIEW_ID] = root_btn

        self.btn_col.addStretch(1)

    def _make_view_button(self, view_id: int, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("folderBtn")
        btn.setCheckable(True)
        # 右クリック = 投入メニュー (左クリックは閲覧のみ)
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, vid=view_id, b=btn: self._show_folder_menu(vid, b, pos)
        )
        self.button_group.addButton(btn, view_id)
        return btn

    # ───────── ビュー / ネストナビゲーション ─────────

    def _browse(self, view_id: int) -> None:
        """左ボタン: 上位ビュー (サブフォルダ / 直下) へ移動。閲覧のみ。"""
        if self._scan is None:
            return
        btn = self._view_btns.get(view_id)
        if btn is None:
            return
        btn.setChecked(True)
        self._cur_view_id = view_id
        if view_id == ROOT_VIEW_ID:
            self._cur_dir = self._scan.root_path
            self._crumb = []
        else:
            sf = self._scan.subfolders[view_id]
            self._cur_dir = sf.path
            self._crumb = [(sf.name, sf.path)]
        self._show_current()

    def _show_current(self) -> None:
        """_cur_dir の中身を表示 (子フォルダ行 + ファイル行) + パンくず更新。"""
        if self._cur_dir is None:
            return
        # 「事件フォルダ直下」ビューは子フォルダ (= サブフォルダ = 左ボタン)
        # を出さず、直下ファイルのみ。サブフォルダ配下はフォルダ+ファイル。
        if self._cur_view_id == ROOT_VIEW_ID:
            entries = list_files(self._cur_dir)
        else:
            entries = list_folder(self._cur_dir)
        self._populate(entries, self._parent_target())
        self._update_breadcrumb()

    def _parent_target(self) -> Path | None:
        """`..` 行が指す親パス。実際の親階層がある時だけ返す (なければ None)。

        - ネスト中 (crumb 2 段以上): 一つ手前のパンくず階層へ戻れる → 表示
        - サブフォルダトップ / 事件フォルダ直下: 事件外には乗り出さない (ADR-2)、
          かつ「事件フォルダ直下へジャンプ」は物理的な親ではなく `..` の意味に
          反するため表示しない (左ボタン側で対応)
        """
        if len(self._crumb) >= 2:
            return self._crumb[-2][1]
        return None

    def _go_up(self) -> None:
        """`..` 行ダブルクリック: 一階層上 (パンくずを 1 段戻す)。"""
        if len(self._crumb) >= 2:
            self._crumb.pop()
            self._cur_dir = self._crumb[-1][1]
            self._show_current()

    def _on_table_double_click(self, row: int, _col: int) -> None:
        """ファイル一覧の行をダブルクリック: `..` は上へ、フォルダなら中へ入る。"""
        item = self.table.item(row, 0)
        if isinstance(item, _NameItem) and item.is_parent:
            self._go_up()
            return
        if isinstance(item, _NameItem) and item.is_dir:
            self._cur_dir = item.path
            self._crumb.append((item.text(), item.path))
            self._show_current()

    def _on_table_selection(self) -> None:
        """行選択が変わったら、ファイルならパスを通知 (フォルダ・未選択は "")。"""
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if isinstance(item, _NameItem) and not item.is_dir:
            self.fileSelected.emit(str(item.path))
        else:
            self.fileSelected.emit("")

    def _on_crumb_click(self, href: str) -> None:
        """パンくずのリンク: その階層まで戻る。"""
        try:
            level = int(href)
        except ValueError:
            return
        if 0 <= level < len(self._crumb):
            self._crumb = self._crumb[: level + 1]
            self._cur_dir = self._crumb[level][1]
            self._show_current()

    def _update_breadcrumb(self) -> None:
        """パスバーを「事件フォルダ: 〜 › サブ › サブサブ」のパンくず表示に。"""
        text = f"事件フォルダ:  {self._case_code}  {self._case_name}"
        last = len(self._crumb) - 1
        for i, (name, _path) in enumerate(self._crumb):
            if i == last:
                text += f"  ›  {name}"  # 現在地は非リンク
            else:
                text += f'  ›  <a href="{i}">{name}</a>'
        self.path_label.setText(text)

    def _on_folder_browse(self, view_id: int) -> None:
        """ボタン左クリック: 閲覧のみ。投入は一切行わない。"""
        self._browse(view_id)
        self.subfolderBrowsed.emit(view_id, self._view_name(view_id))

    def _on_subfolder_inject(self, view_id: int) -> None:
        """Alt+0〜9 / 右クリックメニュー: 投入要求 (実投入は M3)。"""
        if view_id not in self._view_btns:
            return
        self.subfolderInjectRequested.emit(view_id, self._view_name(view_id))
        # 投入先の中身を表示して、ファイルが入ったことを可視化する
        self._browse(view_id)

    def _view_name(self, view_id: int) -> str:
        if view_id == ROOT_VIEW_ID:
            return "事件フォルダ直下"
        if self._scan is not None and 0 <= view_id < len(self._scan.subfolders):
            return self._scan.subfolders[view_id].name
        return "?"

    def _show_folder_menu(self, view_id: int, btn: QPushButton, pos) -> None:
        """サブフォルダボタンの右クリックメニュー (D&D 以外のマウス投入手段)。"""
        menu = QMenu(self)
        inbox_file = self._inbox_file_getter() if self._inbox_file_getter else None
        if inbox_file:
            act = menu.addAction(f"「{inbox_file}」を ここへ投入")
            act.triggered.connect(lambda: self._on_subfolder_inject(view_id))
        else:
            act = menu.addAction("投入する Inbox ファイルが未選択")
            act.setEnabled(False)
        menu.exec(btn.mapToGlobal(pos))

    # ───────── ファイル一覧 ─────────

    def _populate(
        self, entries: list[FileEntry], parent_path: Path | None = None
    ) -> None:
        """一覧を更新。フォルダ先頭・名前昇順、`..` は更に最先頭 (_NameItem.__lt__)。"""
        self.table.setSortingEnabled(False)
        has_parent = parent_path is not None
        self.table.setRowCount(len(entries) + (1 if has_parent else 0))

        row = 0
        if has_parent:
            parent_item = _NameItem("..", True, parent_path, is_parent=True)
            self.table.setItem(row, 0, parent_item)
            empty_date = QTableWidgetItem("")
            empty_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, empty_date)
            size_cell = QTableWidgetItem("フォルダ")
            size_cell.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 2, size_cell)
            self.table.setRowHeight(row, 14)
            row += 1

        for e in entries:
            name_item = _NameItem(e.name, e.is_dir, e.path)
            if e.is_dir:
                name_item.setIcon(self._dir_icon)
            self.table.setItem(row, 0, name_item)

            date = datetime.fromtimestamp(e.mtime).strftime("%Y-%m-%d")
            item_date = QTableWidgetItem(date)
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, item_date)

            if e.is_dir:
                item_size = QTableWidgetItem("フォルダ")
                item_size.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row, 2, item_size)
            else:
                self.table.setItem(row, 2, _SizeItem(e.size, self._size_unit))
            self.table.setRowHeight(row, 14)
            row += 1

        self.table.setSortingEnabled(True)
        # 既定の並び: ".." > フォルダ > ファイル (各々名前昇順)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)

    def _show_header_menu(self, pos) -> None:
        """サイズ列ヘッダー右クリック → KB/MB 切替メニュー (他列は無反応)。"""
        hdr = self.table.horizontalHeader()
        col = hdr.logicalIndexAt(pos)
        if col != 2:
            return
        menu = QMenu(self)
        act_kb = menu.addAction("KB で表示")
        act_kb.setCheckable(True)
        act_kb.setChecked(self._size_unit == "KB")
        act_mb = menu.addAction("MB で表示")
        act_mb.setCheckable(True)
        act_mb.setChecked(self._size_unit == "MB")
        chosen = menu.exec(hdr.mapToGlobal(pos))
        if chosen is None:
            return
        new_unit = "KB" if chosen is act_kb else "MB"
        if new_unit != self._size_unit:
            self._size_unit = new_unit
            self._show_current()

    def inject_to_current_view(self) -> None:
        """中央コマンドストリップ ▶▶ ボタン用: 現在表示中のサブフォルダ
        (または「事件フォルダ直下」) に投入要求を発火 (実投入は M3)。"""
        self._on_subfolder_inject(self._cur_view_id)

    # ───────── 事件フォルダ自体の rename (Shift+F2) ─────────

    def rename_current_case_folder(self) -> None:
        """事件タブで選択中の事件フォルダ自体の名前を変更。

        ※ 先頭の case_code (例: R060200042) を変えると K-SystemZ から
        事件を引けなくなる (`doc_root` 直下を `{case_code}*` で前方一致)
        ため警告を出す (禁止はしない)。
        """
        idx = self.case_tabs.currentIndex()
        if not 0 <= idx < len(self._case_paths):
            return
        old_path = self._case_paths[idx]
        old_name = old_path.name
        old_code, _ = _parse_case(old_path)

        label = (
            "新しい事件フォルダ名を入力してください。\n"
            "※ 先頭の事件番号 (例: R060200042) を変えると\n"
            "  K-SystemZ から事件が引けなくなる可能性があります。"
        )
        new_name, ok = QInputDialog.getText(
            self,
            "事件フォルダ名を変更",
            label,
            QLineEdit.EchoMode.Normal,
            old_name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        forbidden = set('\\/:*?"<>|')
        if any(c in forbidden for c in new_name):
            QMessageBox.warning(
                self,
                "事件フォルダ名を変更",
                'ファイル名に使えない文字が含まれています:  \\ / : * ? " < > |',
            )
            return

        new_path = old_path.parent / new_name
        if new_path.exists():
            QMessageBox.warning(
                self,
                "事件フォルダ名を変更",
                f"同名のフォルダが既に存在します:\n{new_name}",
            )
            return

        new_code, _ = _parse_case(new_path)
        if new_code != old_code:
            ans = QMessageBox.warning(
                self,
                "事件番号が変わります",
                f"事件番号が「{old_code}」→「{new_code}」に変わります。\n"
                "K-SystemZ から事件を引けなくなる可能性があります。\n\n"
                "続行しますか?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        try:
            old_path.rename(new_path)
        except OSError as e:
            QMessageBox.critical(
                self,
                "事件フォルダ名を変更",
                f"名前を変更できませんでした:\n{e}",
            )
            return

        # 内部状態 + タブ表示 + 走査結果を更新
        self._case_paths[idx] = new_path
        code, name = _parse_case(new_path)
        self.case_tabs.blockSignals(True)
        self.case_tabs.setTabText(idx, f"{code} {name}")
        self.case_tabs.blockSignals(False)
        self._load_case(idx)

    # ───────── 外部 API ─────────

    def current_case(self) -> tuple[str, str]:
        idx = self.case_tabs.currentIndex()
        if 0 <= idx < len(self._case_paths):
            return _parse_case(self._case_paths[idx])
        return ("?", "?")

    def set_inbox_file_getter(self, getter) -> None:
        """右クリック投入メニューが Inbox の選択ファイル名を問い合わせる getter。

        getter() は選択中ファイル名 (str)、未選択なら None を返すこと。
        """
        self._inbox_file_getter = getter
