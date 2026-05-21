"""k-file メインウインドウ (M1 凝縮 r3 — 2026-05-22)

- 事件タブは CasePane 内に移動 (Inbox 領域にかからない)
- 中央ペインに sunken 枠で視覚分離
- 1:2:2 比率
- 全要素の高さ統一 (≈ 14-16px)
- F1〜F6 押下時 (CasePane.subfolderInvoked 経由) で main_window がステータス通知
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
        self.inbox_pane = InboxPane()
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
        sb.showMessage("準備完了 — Inbox 7 件 / Undo 0 段")
        sb.addPermanentWidget(QSizeGrip(self))
        self.setStatusBar(sb)

        # シグナル接続
        self.case_pane.subfolderInvoked.connect(self._on_subfolder_invoked)
        self.case_pane.caseTabChanged.connect(self._on_case_tab_changed)

    def _build_menus(self, mb: QMenuBar) -> None:
        m_file = mb.addMenu("ファイル(&F)")
        act_open_case = QAction("事件を開く(&O)…", self)
        act_open_case.setShortcut(QKeySequence("Ctrl+O"))
        m_file.addAction(act_open_case)
        m_file.addSeparator()
        act_quit = QAction("終了(&X)", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_edit = mb.addMenu("編集(&E)")
        act_undo = QAction("元に戻す(&U)", self)
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        m_edit.addAction(act_undo)
        m_edit.addSeparator()
        act_history = QAction("投入履歴(&H)…", self)
        act_history.setShortcut(QKeySequence("F12"))
        m_edit.addAction(act_history)

        m_view = mb.addMenu("表示(&V)")
        # サブフォルダは Alt+1〜6 に移したので F5 は Windows 標準どおり Refresh に
        act_refresh = QAction("Inbox を更新(&R)", self)
        act_refresh.setShortcut(QKeySequence("F5"))
        m_view.addAction(act_refresh)
        # F2 は M3 で「選択中ファイルをリネーム」に充てる予定 (Windows 標準)

        m_help = mb.addMenu("ヘルプ(&H)")
        m_help.addAction(QAction("k-file について(&A)", self))

    def _on_case_tab_changed(self, idx: int, code: str, name: str) -> None:
        self.statusBar().showMessage(f"事件タブ切替 → {code}  {name}", 3000)

    def _on_subfolder_invoked(self, idx: int, folder_name: str) -> None:
        code, _ = self.case_pane.current_case()
        inbox_file = self.inbox_pane.selected_file_name()
        if inbox_file:
            self.statusBar().showMessage(
                f"[ダミー] {inbox_file} → {code} / {folder_name} (実投入は M3)", 4000
            )
        else:
            self.statusBar().showMessage(
                f"サブフォルダ → {code} / {folder_name} (Inbox 未選択)", 3000
            )
