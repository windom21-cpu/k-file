"""k-file メインウインドウ (M1 凝縮 r3 — 2026-05-22)

- 事件タブは CasePane 内に移動 (Inbox 領域にかからない)
- 中央ペインに sunken 枠で視覚分離
- 1:2:2 比率
- 全要素の高さ統一 (≈ 14-16px)
- サブフォルダ操作: 左クリック=閲覧 / Alt+1〜6・右クリック=投入。
  CasePane の subfolderBrowsed / subfolderInjectRequested を受けてステータス通知
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QMenuBar,
    QSizeGrip,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.infra.kfile_db import KFileDB
from src.ui.about_dialog import AboutDialog
from src.ui.case_pane import CasePane
from src.ui.inbox_pane import InboxPane
from src.ui.preview_pane import PreviewPane
from src.ui.title_bar import TitleBar


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("k-file")
        self.resize(1400, 860)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._inbox_count = 0
        self._build_layout()

    def _build_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        root_layout.addWidget(self.title_bar)

        self.menu_bar = QMenuBar()
        self._build_menus(self.menu_bar)
        root_layout.addWidget(self.menu_bar)

        # 3 ペイン (1:2:2)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setChildrenCollapsible(False)
        self.db = KFileDB()
        self.inbox_pane = InboxPane(self.db)
        self.case_pane = CasePane()
        self.preview_pane = PreviewPane()
        self.splitter.addWidget(self.inbox_pane)
        self.splitter.addWidget(self.case_pane)
        self.splitter.addWidget(self.preview_pane)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 2)
        total = self.width()
        unit = total // 5
        self.splitter.setSizes([unit, unit * 2, total - 3 * unit])
        root_layout.addWidget(self.splitter, stretch=1)

        self.setCentralWidget(root)

        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        sb.addPermanentWidget(QSizeGrip(self))
        self.setStatusBar(sb)

        # シグナル接続
        self.case_pane.subfolderBrowsed.connect(self._on_subfolder_browsed)
        self.case_pane.subfolderInjectRequested.connect(
            self._on_subfolder_inject_requested
        )
        self.case_pane.caseTabChanged.connect(self._on_case_tab_changed)
        # 右クリック投入メニューが参照する Inbox 選択ファイルの getter
        self.case_pane.set_inbox_file_getter(self.inbox_pane.selected_file_name)
        # Inbox 件数をステータスバーに反映
        self.inbox_pane.inboxChanged.connect(self._on_inbox_changed)
        self._on_inbox_changed(self.inbox_pane.file_count())
        # ファイル選択 → 右ペインでプレビュー
        self.inbox_pane.fileSelected.connect(self.preview_pane.show_file)
        self.case_pane.fileSelected.connect(self.preview_pane.show_file)

    def _build_menus(self, mb: QMenuBar) -> None:
        # M1 で実動するのは「終了」「k-file について」のみ。
        # M2〜M5 で実装する項目は disabled (グレーアウト) で配置し、
        # 各マイルストーンで setEnabled(True) + slot 結線していく。
        m_file = mb.addMenu("ファイル(&F)")
        act_open_case = QAction("事件を開く(&O)…", self)
        act_open_case.setShortcut(QKeySequence("Ctrl+O"))
        act_open_case.setEnabled(False)  # M5 で実装
        m_file.addAction(act_open_case)
        m_file.addSeparator()
        act_quit = QAction("終了(&X)", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_edit = mb.addMenu("編集(&E)")
        act_undo = QAction("元に戻す(&U)", self)
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.setEnabled(False)  # M4 で実装
        m_edit.addAction(act_undo)
        m_edit.addSeparator()
        act_history = QAction("投入履歴(&H)…", self)
        act_history.setShortcut(QKeySequence("F12"))
        act_history.setEnabled(False)  # M4 で実装
        m_edit.addAction(act_history)

        m_view = mb.addMenu("表示(&V)")
        # サブフォルダは Alt+1〜6 に移したので F5 は Windows 標準どおり Refresh に
        act_refresh = QAction("Inbox を更新(&R)", self)
        act_refresh.setShortcut(QKeySequence("F5"))
        act_refresh.triggered.connect(lambda: self.inbox_pane.refresh())
        m_view.addAction(act_refresh)
        act_show_ignored = QAction("無視したファイルも表示(&I)", self)
        act_show_ignored.setCheckable(True)
        act_show_ignored.toggled.connect(
            lambda on: self.inbox_pane.set_show_ignored(on)
        )
        m_view.addAction(act_show_ignored)
        # F2 は M3 で「選択中ファイルをリネーム」に充てる予定 (Windows 標準)

        # ツールメニュー: 設定 (Inbox 監視パス・ksystemz.db パス等) の入口。
        # 将来「フォルダ整合チェック」「履歴の掃除」等もここへ集約する。
        m_tools = mb.addMenu("ツール(&T)")
        act_settings = QAction("設定(&S)…", self)
        act_settings.setEnabled(False)  # M2 で実装
        m_tools.addAction(act_settings)

        m_help = mb.addMenu("ヘルプ(&H)")
        act_about = QAction("k-file について(&A)", self)
        act_about.triggered.connect(self._on_about)
        m_help.addAction(act_about)

    def _on_about(self) -> None:
        AboutDialog(self).exec()

    def _on_inbox_changed(self, count: int) -> None:
        self._inbox_count = count
        self._update_idle_status()

    def _update_idle_status(self) -> None:
        self.statusBar().showMessage(
            f"準備完了 — Inbox {self._inbox_count} 件 / Undo 0 段"
        )

    def _on_case_tab_changed(self, idx: int, code: str, name: str) -> None:
        self.statusBar().showMessage(f"事件タブ切替 → {code}  {name}", 3000)

    def _on_subfolder_browsed(self, idx: int, folder_name: str) -> None:
        code, _ = self.case_pane.current_case()
        self.statusBar().showMessage(f"{code} / {folder_name} を表示", 2000)

    def _on_subfolder_inject_requested(self, idx: int, folder_name: str) -> None:
        code, _ = self.case_pane.current_case()
        inbox_file = self.inbox_pane.selected_file_name()
        if inbox_file:
            self.statusBar().showMessage(
                f"[ダミー] {inbox_file} → {code} / {folder_name} (実投入は M3)", 4000
            )
        else:
            self.statusBar().showMessage(
                "投入する Inbox ファイルが未選択です", 3000
            )
