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
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
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
from src.ui.command_strip import CommandStrip
from src.ui.function_keys_bar import FunctionKeysBar
from src.ui.inbox_pane import InboxPane
from src.ui.preview_pane import PreviewPane
from src.ui.title_bar import TitleBar

# 動的レイアウト用の定数 — _apply_pane_layout の視覚均等計算に使う。
# 中央ペイン側の「ファイル一覧より左の総幅」(サブフォルダボタン列 + 中央枠 ≈ 144px)
_CASE_LEFT_OFFSET = 144


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("k-file")
        self.resize(1400, 860)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._inbox_count = 0
        self._preview_visible = False  # 初期は 1:1 二カラム (F3 で展開)
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

        # 3 ペイン (1:2:2) — 中央は [CommandStrip + CasePane] の合成
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        # handle 幅 0: 動的計算でペイン幅を決めるので drag 不要。
        # 副次効果として Inbox 右辺 / CasePane 左辺の sunken 縁がきれいに揃う。
        self.splitter.setHandleWidth(0)
        self.splitter.setChildrenCollapsible(False)
        self.db = KFileDB()
        self.inbox_pane = InboxPane(self.db)
        self.case_pane = CasePane()
        self.command_strip = CommandStrip()
        self.preview_pane = PreviewPane()

        # 中央コンテナ: 左に CommandStrip (固定幅) / 右に CasePane (stretch)
        center = QWidget()
        center_lay = QHBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(0)
        center_lay.addWidget(self.command_strip)
        center_lay.addWidget(self.case_pane, stretch=1)

        self.splitter.addWidget(self.inbox_pane)
        self.splitter.addWidget(center)
        self.splitter.addWidget(self.preview_pane)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 2)
        self._apply_pane_layout()
        root_layout.addWidget(self.splitter, stretch=1)

        # ── ファンクションキーバー (DOS ファイラー風、ステータスバー直上) ──
        self.fn_bar = FunctionKeysBar()
        self.fn_bar.set_slot(1, "ヘルプ", enabled=False)
        self.fn_bar.set_slot(
            2, "名変更",
            enabled=False,
            tooltip="F2: ファイル名変更 (M3 で実装) / Shift+F2: 事件フォルダ名を変更",
        )
        self.fn_bar.set_slot(
            3, "ﾌﾟﾚﾋﾞｭｰ", enabled=True,
            tooltip="F3: プレビュー開閉 (二カラム ↔ 三カラム)",
        )
        self.fn_bar.set_slot(5, "更新", enabled=True, tooltip="F5: Inbox を更新")
        self.fn_bar.set_slot(8, "削除", enabled=False)
        self.fn_bar.set_slot(
            10, "メニュー", enabled=False,
            tooltip="F10: メニューバーをアクティブ化 (Windows 標準)",
        )
        self.fn_bar.set_slot(12, "履歴", enabled=False)
        self.fn_bar.keyTriggered.connect(self._on_fn_key)
        root_layout.addWidget(self.fn_bar)

        self.setCentralWidget(root)

        # Shift+F2: 事件フォルダ自体の rename (滅多に使わない用途)
        sc_rename_case = QShortcut(QKeySequence("Shift+F2"), self)
        sc_rename_case.activated.connect(self.case_pane.rename_current_case_folder)

        # F3: プレビュー開閉トグル (二カラム ↔ 三カラム)
        sc_toggle_preview = QShortcut(QKeySequence("F3"), self)
        sc_toggle_preview.activated.connect(self._toggle_preview)

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
        # 中央コマンドストリップ ▶▶ / ✕ ボタン
        self.command_strip.injectClicked.connect(self._on_strip_inject)
        self.command_strip.ignoreClicked.connect(self._on_strip_ignore)
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

    def _on_strip_inject(self) -> None:
        """▶▶: Inbox 選択ファイルをアクティブなサブフォルダへ投入要求。"""
        if not self.inbox_pane.selected_file_name():
            self.statusBar().showMessage(
                "投入する Inbox ファイルが未選択です", 3000
            )
            return
        self.case_pane.inject_to_current_view()

    def _on_strip_ignore(self) -> None:
        """✕: Inbox 選択ファイルの「無視」を切替。"""
        if not self.inbox_pane.toggle_ignore_selected():
            self.statusBar().showMessage(
                "選択中の Inbox ファイルがありません", 3000
            )

    def _on_fn_key(self, k: int) -> None:
        """ファンクションキーバーのセルクリック (enabled なものだけ届く)。"""
        if k == 3:
            self._toggle_preview()
        elif k == 5:
            self.inbox_pane.refresh()

    def _toggle_preview(self) -> None:
        """F3 / bar の F3 クリック: プレビュー開閉 (1:1 ↔ 1:2:2)。"""
        self._preview_visible = not self._preview_visible
        self._apply_pane_layout()

    def _apply_pane_layout(self) -> None:
        """プレビュー有無に応じてスプリッタを動的計算で再配置。

        2 カラム時は「Inbox 幅 ≒ 中央のファイル一覧幅」を視覚的に成立させる:
          inbox = (total - strip - case_left_offset - handle) / 2
          中央コンテナ = 残り
        3 カラム時は従来どおり 1:2:2。
        """
        total = self.splitter.size().width() or self.width()
        handle = self.splitter.handleWidth()
        strip = CommandStrip.STRIP_WIDTH
        if self._preview_visible:
            self.preview_pane.setVisible(True)
            usable = total - handle * 2
            unit = max(usable // 5, 0)
            self.splitter.setSizes([unit, unit * 2, usable - 3 * unit])
        else:
            self.preview_pane.setVisible(False)
            usable = total - handle
            inbox = max((usable - strip - _CASE_LEFT_OFFSET) // 2, 100)
            self.splitter.setSizes([inbox, usable - inbox, 0])

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
