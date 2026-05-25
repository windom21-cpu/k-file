"""左 Inbox ペイン (ペインタイトル + 出所フィルタタブ + 統合ファイル一覧)

M2: ダミーを廃し core/inbox_watcher で監視対象フォルダの実ファイルを読み込む。
PDF + 画像のみ表示。出所フィルタタブ (全て / scan / Desktop / 作業)。
QFileSystemWatcher でフォルダ変更を検知し自動更新、F5 で手動更新。

「無視」: 右クリック →「この一覧から無視」で個別除外 (kfile.db に記録、実ファイル
は触らない)。表示メニューの「無視したファイルも表示」で再表示・解除できる。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDrag, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHeaderView,
    QMenu,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.inbox_watcher import InboxFile, InboxSource, InboxWatcher
from src.infra.kfile_db import KFileDB
from src.ui.dnd import SRC_INBOX, make_drag_pixmap, make_kfile_mime_data
from src.ui.pane_header import PaneHeader


class _DragTable(QTableWidget):
    """Inbox 用の ドラッグ起点 QTableWidget。

    drag 開始時に「選択中ファイルの絶対パス + 起点=inbox」を MIME に載せる。
    drop 先 (サブフォルダボタン等) はこれを見て「投入」と分かる。
    """

    # Tab / Shift+Tab で 中央テーブルにフォーカス移動 (MainWindow が結線)
    tabPressed = Signal()

    def __init__(self, pane: "InboxPane") -> None:
        super().__init__(0, 4, pane)
        self._pane = pane
        self.setDragEnabled(True)
        self.setDragDropMode(QTableWidget.DragDropMode.DragOnly)

    def keyPressEvent(self, e) -> None:
        # Tab / Shift+Tab → 相手テーブルにフォーカス移動 (Qt 既定の focus
        # チェーン経由だと間にボタン等が挟まって遠回りになるため奪取)
        if e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.tabPressed.emit()
            e.accept()
            return
        super().keyPressEvent(e)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        # ペイン側のレスポンシブ列調整に通知 (狭い時は更新列を譲ってファイル名優先)
        if hasattr(self._pane, "_apply_responsive_columns"):
            self._pane._apply_responsive_columns()

    def startDrag(self, _actions) -> None:
        files = self._pane.selected_files()
        if not files:
            return
        drag = QDrag(self)
        drag.setMimeData(
            make_kfile_mime_data(SRC_INBOX, [f.path for f in files])
        )
        # ドラッグ中にカーソル横に黄色い付箋でファイル名表示 (掴んでいることの可視化)
        from PySide6.QtCore import QPoint
        drag.setPixmap(make_drag_pixmap([f.name for f in files]))
        drag.setHotSpot(QPoint(-12, -12))
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
                  Qt.DropAction.CopyAction)


def format_size(n: int, unit: str = "KB") -> str:
    """バイト数を 3 桁カンマ区切りで返す (単位文字は付けない)。

    ヘッダー右クリックメニューで KB/MB を切替可能 (両ペイン独立)。KB は整数、
    MB は小数 1 桁。単位はヘッダー右クリックメニューでユーザーが選んだ状態を
    覚えている前提なので、セル側には付けず数値だけ見せる (2026-05-25 要望)。
    """
    if unit == "MB":
        return f"{n / (1024 * 1024):,.1f}"
    return f"{n // 1024:,}"


class _SizeCell(QTableWidgetItem):
    """サイズセル: 表示は人間可読、ソートはバイト数で正しく行う。"""

    def __init__(self, size: int, unit: str = "KB") -> None:
        super().__init__(format_size(size, unit))
        self._size = size
        self.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _SizeCell):
            return self._size < other._size
        return self.text() < other.text()

# 初回起動 (settings 未保存) で使われる Inbox 監視先デフォルト。
# 設計上の役割は「業務上代表的な 3 出所」を 1 つずつ:
#   - scan: 複合機の取り込み先
#   - Desktop: ユーザーの実デスクトップ (round-trip 動線 ADR-9 の終点)
#   - 作業: 一時作業フォルダ
# Win 機本番で問題化した「Desktop が 2 件並び、両方とも実デスクトップに
# 向けると重複表示」(2026-05-25 本番テスト報告) を避けるため、dev fake
# デスクトップ (k-file-test-data/inbox-desktop) は撤去し Desktop は 1 件のみ。
# scan/作業 は Linux dev 環境向けの fake パスのまま (Win 機では存在せず
# 自然に無視される。ユーザーが設定ダイアログで実 Win パスに置き換える前提)。
_DEV_INBOX_SOURCES: list[InboxSource] = [
    InboxSource("scan", Path.home() / "k-file-test-data" / "inbox-scan"),
    InboxSource("Desktop", Path.home() / "デスクトップ", cutoff_days=7),
    InboxSource("作業", Path.home() / "k-file-test-data" / "inbox-work"),
]

# フィルタタブ。"全て" 以外は出所ラベルと一致させる。
FILTER_TABS = ["全て", "scan", "Desktop", "作業"]

_IGNORED_FG = QColor("#808080")  # 無視ファイルを表示する際のグレー


class InboxPane(QWidget):
    inboxChanged = Signal(int)   # 無視を除いた実ファイル数 (ステータスバー用)
    fileSelected = Signal(str)   # 選択ファイルのパス (プレビュー用、未選択は "")
    # Del キーで削除要求 (MainWindow が file_ops.trash + 履歴記録)
    deleteRequested = Signal(str)
    # Inbox に並んだフォルダ行のダブルクリック / Enter → 事件タブとして開く
    # (M6a 汎用ファイラー化と整合。k-file 内完結でデスクトップの作業フォルダを扱える)
    openFolderRequested = Signal(str)

    def __init__(
        self,
        db: KFileDB,
        sources: list[InboxSource] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("inboxPane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._db = db
        self._files: list[InboxFile] = []
        self._ignored: set[str] = set()     # 無視ファイルの絶対パス
        self._show_ignored = False
        self._size_unit = "KB"              # ヘッダー右クリックで KB/MB 切替
        # sources 未指定なら dev 既定 (実 Desktop 含む)。設定ダイアログ完了後は
        # MainWindow が settings 経由でパスを渡す。
        self._sources = sources if sources is not None else _DEV_INBOX_SOURCES

        outer = QVBoxLayout(self)
        # 右に 2px: #inboxPane の border-right (2px) を描画する領域を確保。
        # これがないと子の table が親幅いっぱいに広がって border を隠す。
        outer.setContentsMargins(0, 0, 2, 0)
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

        # ファイル一覧 (CasePane と列構成を統一: Name + EXT + 更新 + サイズ、行高 18px)
        # _DragTable は drag 起点 (サブフォルダボタンへ D&D 投入できる)。
        # サイズ列ヘッダーは KB/MB 切替に追従 (`ｻｲｽﾞ (KB)` ↔ `ｻｲｽﾞ (MB)`)。
        self.table = _DragTable(self)
        self.table.setHorizontalHeaderLabels(
            ["Name", "拡張子", "更新", "ｻｲｽﾞ (KB)"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(18)
        self.table.verticalHeader().setMinimumSectionSize(18)
        self.table.horizontalHeader().setFixedHeight(17)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(1, 60)    # 拡張子 (.PDF / .JPEG)
        # 更新 (YY-MM-DD HH:MM、14 文字)。初期表示で省略されないよう 130px 確保
        # (狭幅時は _apply_responsive_columns で縮小、最終的に非表示にもなる)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 90)    # サイズ
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 複数選択可能 (Shift で範囲 / Ctrl で個別 toggle)。投入 / 削除 / D&D は
        # 全選択行に対して順次実行される。
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        # 縦スクロールバーを常時表示 (CasePane と viewport 幅を揃え、Name 列幅を
        # 両ペインで一致させるため。AsNeeded だと片方だけ 12px 狭くなる)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # ヘッダー左クリック = ソート / 既定は「更新」降順 (新着順を維持)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_file_menu)
        self.table.itemSelectionChanged.connect(self._on_selection)
        # ダブルクリック / Enter → OS 既定アプリで開く
        self.table.cellDoubleClicked.connect(self._open_selected_with_default_app)
        sc_open = QShortcut(QKeySequence(Qt.Key.Key_Return), self.table)
        sc_open.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_open.activated.connect(self._open_selected_with_default_app)
        sc_open_kp = QShortcut(QKeySequence(Qt.Key.Key_Enter), self.table)
        sc_open_kp.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_open_kp.activated.connect(self._open_selected_with_default_app)
        # ヘッダー右クリック (サイズ列のみ) → KB/MB 切替メニュー
        hdr = self.table.horizontalHeader()
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._show_header_menu)
        outer.addWidget(self.table, stretch=1)

        # 監視対象フォルダを QFileSystemWatcher で監視 (変更で自動更新)
        self._watcher = InboxWatcher(self._sources, self)
        self._watcher.changed.connect(self.refresh)
        self.refresh()

    def set_compact(self, compact: bool) -> None:
        """プレビュー展開時 (3 カラムモード) は Name 列のみに絞り、
        ペインが狭くてもファイル名が読めるようにする。

        Inbox 幅 = 全体の 1/5 程度になるため EXT / 更新 / サイズ は
        並べる余地がない。F3 トグルで MainWindow から呼ばれる。
        """
        self._compact = compact
        self._apply_responsive_columns()

    def _apply_responsive_columns(self) -> None:
        """テーブル幅に応じて列の表示を調整する (ファイル名を最優先)。

        - compact (プレビュー展開時): EXT / 更新 / サイズ を全て隠す
        - 通常時: Name 最低 120px を確保した上で 更新 列を 0〜110px で伸縮、
          余地が 30px 未満なら更新列も隠す。EXT / サイズ は固定で維持。
        """
        if getattr(self, "_compact", False):
            for col in (1, 2, 3):
                self.table.setColumnHidden(col, True)
            return
        self.table.setColumnHidden(1, False)
        self.table.setColumnHidden(3, False)
        # ext(60) + size(90) + name_min(120) を引いた残りを 更新 列が使う
        viewport_w = self.table.viewport().width()
        date_avail = viewport_w - (60 + 90 + 120)
        if date_avail < 30:
            self.table.setColumnHidden(2, True)
        else:
            self.table.setColumnHidden(2, False)
            self.table.setColumnWidth(2, min(date_avail, 130))

    def reload_sources(self, sources: list[InboxSource]) -> None:
        """設定変更時に監視先を差し替える (古い QFileSystemWatcher を破棄)。"""
        if self._watcher is not None:
            try:
                self._watcher.changed.disconnect(self.refresh)
            except (TypeError, RuntimeError):
                pass
            self._watcher.deleteLater()
        self._sources = sources
        self._watcher = InboxWatcher(self._sources, self)
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
        # ソートはテーブル側 (setSortingEnabled) に任せる。
        # _populate の末尾で「更新降順」を既定として適用する。
        self._populate(pool)
        self.inboxChanged.emit(self.file_count())

    def _populate(self, files: list[InboxFile]) -> None:
        # ソート ON のまま行を入れると挙動が不安定。OFF にして挿入後 ON に戻す。
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(files))
        for r, f in enumerate(files):
            ignored = str(f.path) in self._ignored

            # Name は stem のみ、拡張子は別列 (例: .PDF .JPG)。
            # フォルダは name 全体を Name 列に出し、拡張子列は空にする。
            if f.is_dir:
                stem_display = f.path.name
                ext_upper = ""
            else:
                stem_display = f.path.stem
                ext_upper = f.path.suffix.upper()
            name_item = QTableWidgetItem(stem_display)
            # UserRole にパス文字列を埋め込む (ソートで行順が変わっても照合できる)
            name_item.setData(Qt.ItemDataRole.UserRole, str(f.path))
            # 長いファイル名がセル幅で省略表示された時のため、ホバーでフル名を見せる
            # (本番テスト要望 2026-05-25)。拡張子込みのフル名 + 出所ラベルを併記。
            name_item.setToolTip(f"{f.name}  ({f.source})")

            ext_item = QTableWidgetItem(ext_upper)
            ext_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

            # Inbox は「今日のスキャン / 昨日の作業」を区別したい用途。
            # `26-05-25 15:30` 形式 (西暦下 2 桁 + 月日 + 時分) で参照フォルダ
            # 側と揃える (2026-05-25 ユーザー要望)。
            date_str = datetime.fromtimestamp(f.mtime).strftime("%y-%m-%d %H:%M")
            date_item = QTableWidgetItem(date_str)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # ソートは mtime (float) で安定化するため UserRole に埋め込み、
            # 通常表示 (文字列) との二段構えで使う (ヘッダー左クリックで安定ソート)。
            date_item.setData(Qt.ItemDataRole.UserRole, f.mtime)

            # フォルダ行はサイズ列を `<DIR>` 表示 (case_pane と同じ DOS ファイラー風)
            if f.is_dir:
                size_item = QTableWidgetItem("<DIR>")
                size_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                size_item = _SizeCell(f.size, self._size_unit)

            if ignored:  # 無視ファイル (表示モード時) は 4 列ともグレー
                name_item.setForeground(_IGNORED_FG)
                ext_item.setForeground(_IGNORED_FG)
                date_item.setForeground(_IGNORED_FG)
                size_item.setForeground(_IGNORED_FG)

            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, ext_item)
            self.table.setItem(r, 2, date_item)
            self.table.setItem(r, 3, size_item)
            self.table.setRowHeight(r, 18)
        self.table.setSortingEnabled(True)
        # 初回 populate 時のみ既定 (更新降順 = 新着順) を採用。以降は
        # ユーザーがヘッダー左クリックで設定した順序を保持する
        # (KB/MB 切替や Inbox 再走査で勝手に既定に戻さない)。
        if not getattr(self, "_sort_initialized", False):
            self.table.sortItems(2, Qt.SortOrder.DescendingOrder)
            self._sort_initialized = True

    def _show_file_menu(self, pos) -> None:
        """Inbox ファイルの右クリックメニュー (無視/開く/コピー/Explorer)。"""
        f = self._row_file(self.table.indexAt(pos).row())
        if f is None:
            return
        menu = QMenu(self)
        act_open = menu.addAction("既定アプリで開く")
        act_open.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(f.path)))
        )
        act_reveal = menu.addAction("フォルダを開く (Explorer)")
        act_reveal.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(f.path.parent))
            )
        )
        act_copy = menu.addAction("フルパスをコピー")
        act_copy.triggered.connect(
            lambda: self._copy_to_clipboard(str(f.path))
        )
        menu.addSeparator()
        if str(f.path) in self._ignored:
            act = menu.addAction("無視を解除")
            act.triggered.connect(lambda: self._set_ignored(f, False))
        else:
            act = menu.addAction("この一覧から無視")
            act.triggered.connect(lambda: self._set_ignored(f, True))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_selected_with_default_app(self, *_args) -> None:
        """Inbox ダブルクリック / Enter キー:
          - ファイル: OS 既定アプリで開く
          - フォルダ: 事件タブとして開く (k-file 内完結。M6a 汎用ファイラー)
        複数選択時は先頭のみ (誤って大量起動するのを避ける)。"""
        f = self._row_file(self.table.currentRow())
        if f is None:
            return
        if f.is_dir:
            self.openFolderRequested.emit(str(f.path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(f.path)))

    def _copy_to_clipboard(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(text)

    def _show_header_menu(self, pos) -> None:
        """サイズ列ヘッダー右クリック → KB/MB 切替メニュー (他列は無反応)。"""
        hdr = self.table.horizontalHeader()
        col = hdr.logicalIndexAt(pos)
        if col != 3:    # 0=Name / 1=EXT / 2=更新 / 3=サイズ
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
            # ヘッダー表示の単位もユーザー選択に追従
            self.table.setHorizontalHeaderLabels(
                ["Name", "拡張子", "更新", f"ｻｲｽﾞ ({new_unit})"]
            )
            self._refresh_view()

    def _row_file(self, row: int) -> InboxFile | None:
        """テーブル row → 元の InboxFile を UserRole パスで引く。"""
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if not path_str:
            return None
        return next((f for f in self._files if str(f.path) == path_str), None)

    def _set_ignored(self, f: InboxFile, ignore: bool) -> None:
        if ignore:
            self._db.add_ignored(str(f.path))
        else:
            self._db.remove_ignored(str(f.path))
        self.refresh()

    def _on_selection(self) -> None:
        """行選択が変わったら選択ファイルのパスを通知 (プレビュー用)。"""
        f = self._row_file(self.table.currentRow())
        self.fileSelected.emit(str(f.path) if f else "")

    def file_count(self) -> int:
        """無視を除いた実ファイル数 (ステータスバーの「Inbox N 件」用)。"""
        return sum(
            1 for f in self._files if str(f.path) not in self._ignored
        )

    def toggle_ignore_selected(self) -> bool:
        """選択中ファイルの「無視」状態を切替 (multi-select 対応)。
        基準は「現在 cell」の状態 — 無視中なら全選択を解除、そうでなければ全選択を無視に。
        選択ゼロなら何もしない。True/False は「実行できたか」。"""
        files = self.selected_files()
        if not files:
            return False
        cur = self._row_file(self.table.currentRow())
        base_path = str(cur.path) if cur is not None else str(files[0].path)
        ignore = base_path not in self._ignored
        for f in files:
            self._set_ignored(f, ignore)
        return True

    def selected_file_name(self) -> str | None:
        """選択中ファイルの **フル名** (case_pane の右クリック投入メニュー表示用)。
        複数選択時は `N ファイル` 形式で返す (具体名は省略)。"""
        files = self.selected_files()
        if not files:
            return None
        if len(files) == 1:
            return files[0].name
        return f"{len(files)} ファイル"

    def selected_file(self) -> InboxFile | None:
        """選択中の Inbox ファイル (パス込み)。未選択 / 無視済なら None。"""
        return self._row_file(self.table.currentRow())

    def selected_files(self) -> list[InboxFile]:
        """選択中の Inbox ファイル全件 (multi-select 対応)。
        Shift/Ctrl で複数選択された行を順序保ったまま返す。"""
        rows = [
            ix.row() for ix in self.table.selectionModel().selectedRows()
        ]
        out: list[InboxFile] = []
        for r in sorted(set(rows)):
            f = self._row_file(r)
            if f is not None:
                out.append(f)
        return out

    def delete_selected(self) -> None:
        """Del キー: 選択中の Inbox ファイル群を削除要求 (multi-select 対応)。"""
        for f in self.selected_files():
            self.deleteRequested.emit(str(f.path))

    def select_path(self, path: Path) -> None:
        """指定パスの行を選択 (rename 直後の選択維持用)。"""
        target = str(path)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == target:
                self.table.setCurrentCell(row, 0)
                return
