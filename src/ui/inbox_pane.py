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

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDrag
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
from src.ui.dnd import SRC_INBOX, make_kfile_mime_data
from src.ui.pane_header import PaneHeader


class _DragTable(QTableWidget):
    """Inbox 用の ドラッグ起点 QTableWidget。

    drag 開始時に「選択中ファイルの絶対パス + 起点=inbox」を MIME に載せる。
    drop 先 (サブフォルダボタン等) はこれを見て「投入」と分かる。
    """

    def __init__(self, pane: "InboxPane") -> None:
        super().__init__(0, 3, pane)
        self._pane = pane
        self.setDragEnabled(True)
        self.setDragDropMode(QTableWidget.DragDropMode.DragOnly)

    def startDrag(self, _actions) -> None:
        f = self._pane.selected_file()
        if f is None:
            return
        drag = QDrag(self)
        drag.setMimeData(make_kfile_mime_data(SRC_INBOX, f.path))
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
                  Qt.DropAction.CopyAction)


def format_size(n: int, unit: str = "KB") -> str:
    """バイト数を KB 統一 (既定) または MB 統一でフォーマット。

    ヘッダー右クリックのメニューで KB/MB を切替可能 (両ペイン独立)。
    KB は整数で粒度十分、MB は小数 1 桁で見やすさ優先。
    """
    if unit == "MB":
        return f"{n / (1024 * 1024):.1f}MB"
    return f"{n // 1024}KB"


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

# M2 dev: Inbox 監視対象フォルダ。M5 で settings (kfile.db) から読むようにする。
# Desktop は << で戻したファイルが round-trip できるよう、実デスクトップも
# 同じ "Desktop" ラベルで合流させる (同名ラベル → 同じフィルタタブに集約)。
# 実 Desktop は長期蓄積場所なので cutoff_days=7 で過去 PDF を自動非表示。
_DEV_INBOX_SOURCES: list[InboxSource] = [
    InboxSource("scan", Path.home() / "k-file-test-data" / "inbox-scan"),
    InboxSource("Desktop", Path.home() / "k-file-test-data" / "inbox-desktop"),
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

        # ファイル一覧 (CasePane と列構成を統一: Name + 更新 + サイズ、行高 14px)
        # _DragTable は drag 起点 (サブフォルダボタンへ D&D 投入できる)。
        self.table = _DragTable(self)
        self.table.setHorizontalHeaderLabels(["Name", "更新", "サイズ"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(14)
        self.table.verticalHeader().setMinimumSectionSize(14)
        self.table.horizontalHeader().setFixedHeight(15)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 70)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        # ヘッダー左クリック = ソート / 既定は「更新」降順 (新着順を維持)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_file_menu)
        self.table.itemSelectionChanged.connect(self._on_selection)
        # ヘッダー右クリック (サイズ列のみ) → KB/MB 切替メニュー
        hdr = self.table.horizontalHeader()
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._show_header_menu)
        outer.addWidget(self.table, stretch=1)

        # 監視対象フォルダを QFileSystemWatcher で監視 (変更で自動更新)
        self._watcher = InboxWatcher(self._sources, self)
        self._watcher.changed.connect(self.refresh)
        self.refresh()

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

            name_item = QTableWidgetItem(f.name)
            # UserRole にパス文字列を埋め込む (ソートで行順が変わっても照合できる)
            name_item.setData(Qt.ItemDataRole.UserRole, str(f.path))

            date_str = datetime.fromtimestamp(f.mtime).strftime("%Y-%m-%d")
            date_item = QTableWidgetItem(date_str)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            size_item = _SizeCell(f.size, self._size_unit)

            if ignored:  # 無視ファイル (表示モード時) は 3 列ともグレー
                name_item.setForeground(_IGNORED_FG)
                date_item.setForeground(_IGNORED_FG)
                size_item.setForeground(_IGNORED_FG)

            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, date_item)
            self.table.setItem(r, 2, size_item)
            self.table.setRowHeight(r, 14)
        self.table.setSortingEnabled(True)
        # 既定: 更新降順 (新着順)。ユーザーがヘッダー左クリックで他列に変更可。
        self.table.sortItems(1, Qt.SortOrder.DescendingOrder)

    def _show_file_menu(self, pos) -> None:
        """Inbox ファイルの右クリックメニュー (無視 / 無視を解除)。"""
        f = self._row_file(self.table.indexAt(pos).row())
        if f is None:
            return
        menu = QMenu(self)
        if str(f.path) in self._ignored:
            act = menu.addAction("無視を解除")
            act.triggered.connect(lambda: self._set_ignored(f, False))
        else:
            act = menu.addAction("この一覧から無視")
            act.triggered.connect(lambda: self._set_ignored(f, True))
        menu.exec(self.table.viewport().mapToGlobal(pos))

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
        """選択中ファイルの「無視」状態を切替 (中央コマンドストリップ ✕ ボタン用)。

        選択がなければ何もしない。True/False は「実行できたか」。
        """
        f = self._row_file(self.table.currentRow())
        if f is None:
            return False
        self._set_ignored(f, str(f.path) not in self._ignored)
        return True

    def selected_file_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def selected_file(self) -> InboxFile | None:
        """選択中の Inbox ファイル (パス込み)。未選択 / 無視済なら None。"""
        return self._row_file(self.table.currentRow())

    def delete_selected(self) -> None:
        """Del キー: 選択中の Inbox ファイルを削除要求。"""
        f = self.selected_file()
        if f is None:
            return
        self.deleteRequested.emit(str(f.path))

    def select_path(self, path: Path) -> None:
        """指定パスの行を選択 (rename 直後の選択維持用)。"""
        target = str(path)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == target:
                self.table.setCurrentCell(row, 0)
                return
