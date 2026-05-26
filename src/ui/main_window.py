"""k-file メインウインドウ (M1 凝縮 r3 — 2026-05-22)

- 事件タブは CasePane 内に移動 (Inbox 領域にかからない)
- 中央ペインに sunken 枠で視覚分離
- 1:2:2 比率
- 全要素の高さ統一 (≈ 14-16px)
- サブフォルダ操作: 左クリック=閲覧 / Alt+1〜6・右クリック=投入。
  CasePane の subfolderBrowsed / subfolderInjectRequested を受けてステータス通知
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QSizeGrip,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.core import file_ops, undo_ops
from src.core.case_repo import CaseRepo
from src.infra.kfile_db import KFileDB
from src.infra.recycle_bin import open_recycle_bin
from src.ui.about_dialog import AboutDialog
from src.ui.case_pane import CasePane, _parse_case
from src.ui.command_strip import CommandStrip
from src.ui.function_keys_bar import FunctionKeysBar
from src.ui.history_view import HistoryDialog
from src.ui.inbox_pane import InboxPane
from src.ui.open_case_dialog import OpenCaseDialog
from src.ui.preview_pane import PreviewPane
from src.ui.rename_dialog import RenameDialog
from src.ui.settings_dialog import (
    KEY_QUICK_NOTES,
    KEY_QUICK_TEMP,
    SettingsDialog,
    load_inbox_sources,
)
from src.ui.title_bar import TitleBar

# 動的レイアウト用の定数 — _apply_pane_layout の視覚均等計算に使う。
# 中央ペイン側で「ファイル一覧より左外」に取られる総幅 (= CasePane Name 列幅と
# Inbox Name 列幅を一致させるための補正)。内訳:
#   3 (outer left margin) + 2 (border-left) + 140 (btn_container fixed) +
#   2 (mid spacing) + 2 (border-right) + 3 (outer right margin) - 4 (Inbox 側の
#   border-right 2 + 右margin 2 を差し引き) = 148
_CASE_LEFT_OFFSET = 148


class MainWindow(QMainWindow):
    def __init__(self, initial_paths: list[Path] | None = None) -> None:
        super().__init__()
        self.setWindowTitle("K-FILE")
        self.resize(1400, 860)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        # フォルダを k-file ウインドウへ D&D で事件タブ追加 (HANDOVER §2)
        self.setAcceptDrops(True)

        self._inbox_count = 0
        self._preview_visible = False  # 初期は 1:1 二カラム (F3 で展開)
        self._repo_cache: CaseRepo | None = None
        # CLI 引数で渡されたフォルダ (K-SystemZ 連携 / 「k-file で開く」の窓口)。
        # セッション復元の後で追加し、最後の引数をアクティブタブにする (M6a / ADR-17)。
        self._initial_paths: list[Path] = list(initial_paths or [])
        # 自前の modal dialog (RenameDialog 等) を開いている間は preview を維持
        # する用カウンタ。changeEvent の ActivationChange ハンドラが参照し、
        # 外部アプリへの切替 (counter==0) のみ preview をクリアする (ADR-22 補足)。
        self._internal_modal_count = 0
        self._build_layout()
        # _build_layout 完了後にセッション復元 + CLI 引数を順次オープン
        self._restore_window_size()
        self._restore_session()
        self._open_initial_paths()

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
        # 設定から Inbox 監視先を復元 (未設定なら InboxPane の dev 既定が使われる)
        configured_sources = load_inbox_sources(self.db)
        self.inbox_pane = InboxPane(self.db, sources=configured_sources)
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
        # stretch factor は使わない: resizeEvent → _apply_pane_layout で
        # ウインドウサイズに応じて毎回 setSizes を呼ぶ方式。stretch factor を
        # 1:2:2 にしておくと、プレビュー非表示時にその 2/5 が中央に流れて
        # Inbox/CasePane の Name 列幅が大きくずれる原因になる。
        self._apply_pane_layout()
        root_layout.addWidget(self.splitter, stretch=1)

        # ── ファンクションキーバー (DOS ファイラー風、ステータスバー直上) ──
        self.fn_bar = FunctionKeysBar()
        self.fn_bar.set_slot(1, "ヘルプ", enabled=False)
        self.fn_bar.set_slot(
            2, "名変更",
            enabled=True,
            tooltip="F2: 選択中ファイル/フォルダ名変更 / Shift+F2: 事件フォルダ名を変更",
        )
        self.fn_bar.set_slot(
            3, "ﾌﾟﾚﾋﾞｭｰ", enabled=True,
            tooltip="F3: プレビュー開閉 (二カラム ↔ 三カラム)",
        )
        self.fn_bar.set_slot(5, "更新", enabled=True, tooltip="F5: Inbox を更新")
        self.fn_bar.set_slot(
            8, "削除", enabled=True,
            tooltip="F8/Del: 選択行を OS ごみ箱へ送る",
        )
        self.fn_bar.set_slot(
            10, "メニュー", enabled=False,
            tooltip="F10: メニューバーをアクティブ化 (Windows 標準)",
        )
        self.fn_bar.set_slot(
            12, "履歴", enabled=True, tooltip="F12: 投入履歴ビュー (個別 Undo 可能)",
        )
        self.fn_bar.keyTriggered.connect(self._on_fn_key)
        root_layout.addWidget(self.fn_bar)
        # F6 雑記録 / F7 一時保管 はパス設定状況で動的に enable/label を切替
        self._refresh_quick_slots()

        self.setCentralWidget(root)

        # F2: フォーカスのあるペインで選択中ファイル/フォルダの rename
        # (Windows 標準。Inbox / 中央 どちらでも動く)
        sc_rename_case = QShortcut(QKeySequence("F2"), self.case_pane)
        sc_rename_case.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_rename_case.activated.connect(self._on_rename_in_case)
        sc_rename_inbox = QShortcut(QKeySequence("F2"), self.inbox_pane)
        sc_rename_inbox.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_rename_inbox.activated.connect(self._on_rename_in_inbox)

        # Del: フォーカスのあるペインで選択行を OS ごみ箱へ
        sc_del_case = QShortcut(QKeySequence("Delete"), self.case_pane)
        sc_del_case.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_del_case.activated.connect(self.case_pane.delete_selected_row)
        sc_del_inbox = QShortcut(QKeySequence("Delete"), self.inbox_pane)
        sc_del_inbox.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_del_inbox.activated.connect(self.inbox_pane.delete_selected)


        # Shift+F2: 事件フォルダ自体の rename (滅多に使わない用途)
        sc_rename_case = QShortcut(QKeySequence("Shift+F2"), self)
        sc_rename_case.activated.connect(self.case_pane.rename_current_case_folder)

        # F3: プレビュー開閉トグル (二カラム ↔ 三カラム)
        sc_toggle_preview = QShortcut(QKeySequence("F3"), self)
        sc_toggle_preview.activated.connect(self._toggle_preview)

        # F6 / F7: クイック起動フォルダ (雑記録 / 一時保管) をタブで開く
        sc_quick_notes = QShortcut(QKeySequence("F6"), self)
        sc_quick_notes.activated.connect(lambda: self._open_quick_folder("notes"))
        sc_quick_temp = QShortcut(QKeySequence("F7"), self)
        sc_quick_temp.activated.connect(lambda: self._open_quick_folder("temp"))

        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        # 右側に「選択中ファイルのフルパス」を 2 分割で常設表示。
        # 左 = showMessage の通常スロット (準備完了 / 一時通知)、
        # 右 = 選択行パス。複数選択時は <複数選択>。境界に Win95 風 sunken 縦線。
        self.path_status_label = QLabel("")
        self.path_status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.path_status_label.setStyleSheet(
            "border-left: 1px solid #808080; padding-left: 6px;"
            " font-size: 9pt;"
        )
        # stretch=0 (= addPermanentWidget の既定): showMessage の通常スロットが
        # 左を伸縮で確保し、path ラベルは内容に合わせた幅で右側に座る。これで
        # 「移動しました」などのトーストメッセージと共存できる。
        sb.addPermanentWidget(self.path_status_label)
        sb.addPermanentWidget(QSizeGrip(self))
        self.setStatusBar(sb)
        # 両ペインの選択モデル変化で path 表示を更新
        self.inbox_pane.table.selectionModel().selectionChanged.connect(
            self._update_path_status
        )
        self.case_pane.table.selectionModel().selectionChanged.connect(
            self._update_path_status
        )

        # シグナル接続
        self.case_pane.subfolderBrowsed.connect(self._on_subfolder_browsed)
        self.case_pane.subfolderInjectRequested.connect(
            self._on_subfolder_inject_requested
        )
        # D&D: Inbox → サブフォルダボタン (rename ダイアログを挟まず即投入)
        self.case_pane.inboxDropToFolderRequested.connect(
            self._on_inbox_drop_to_folder
        )
        self.case_pane.inboxDropInjectRequested.connect(
            self._on_inbox_drop_inject
        )
        # D&D: 事件A → 事件B タブ (クロス事件 Move)
        self.case_pane.caseTabDropMoveRequested.connect(
            self._on_case_tab_drop_move
        )
        self.case_pane.caseTabDropCopyRequested.connect(
            self._on_case_tab_drop_copy
        )
        # 右クリック明示: 「他事件へコピー/移動 → サブフォルダ」(B 案)
        self.case_pane.caseExplicitCrossCaseRequested.connect(
            self._on_case_explicit_op
        )
        self.case_pane.caseTabChanged.connect(self._on_case_tab_changed)
        # 右クリック投入メニューが参照する Inbox 選択ファイルの getter
        self.case_pane.set_inbox_file_getter(self.inbox_pane.selected_file_name)
        # 事件ショートカット (B 内の A symlink) ダブルクリックの target 判定用に
        # ksystemz の doc_root を引く getter を注入 (CaseRepo 未設定なら None)
        self.case_pane.set_doc_root_getter(self._safe_doc_root)
        # 事件ショートカット activate → 対象事件のタブに切替 (なければ新タブ)
        self.case_pane.caseShortcutActivated.connect(self._on_case_shortcut)
        # 中央コマンドストリップ: 数字ボタン (動的) / << / ✕ / ↶ ボタン
        self.command_strip.subfolderClicked.connect(self._on_strip_subfolder)
        self.command_strip.returnToDesktopClicked.connect(
            self._on_strip_return_to_desktop
        )
        self.command_strip.ignoreClicked.connect(self._on_strip_ignore)
        self.command_strip.deleteClicked.connect(self._on_strip_delete)
        self.command_strip.undoClicked.connect(self._on_undo)
        # 事件タブ変更 / サブフォルダ構成変更でストリップの数字ボタンを再構築
        self.case_pane.subfoldersChanged.connect(self._sync_strip_targets)
        self._sync_strip_targets()
        # サブフォルダ +/- / ショートカット作成等の通知をステータスバーへ
        self.case_pane.actionStatus.connect(
            lambda msg: self.statusBar().showMessage(msg, 4000)
        )
        # Del / − ボタン: 中央 = case 削除 / Inbox = inbox 削除 (経路で履歴の文脈分け)
        self.case_pane.deleteRequested.connect(self._on_case_delete)
        self.inbox_pane.deleteRequested.connect(self._on_inbox_delete)
        # 事件タブの追加/閉鎖を open_tabs に永続化 (セッション復元用)
        self.case_pane.casePathsChanged.connect(self._save_open_tabs)
        # Inbox 件数をステータスバーに反映
        self.inbox_pane.inboxChanged.connect(self._on_inbox_changed)
        self._on_inbox_changed(self.inbox_pane.file_count())
        # ファイル選択 → 右ペインでプレビュー
        self.inbox_pane.fileSelected.connect(self.preview_pane.show_file)
        self.case_pane.fileSelected.connect(self.preview_pane.show_file)
        # Inbox に並んだフォルダ行のダブルクリック → 事件タブで開く
        self.inbox_pane.openFolderRequested.connect(self._open_inbox_folder)
        # Tab / Shift+Tab で Inbox ↔ 中央ファイル一覧の往復
        self.inbox_pane.table.tabPressed.connect(self._focus_case_table)
        self.case_pane.table.tabPressed.connect(self._focus_inbox_table)
        # クリック等でフォーカスが Inbox ↔ 中央 を切り替わった瞬間に、相手側の
        # 選択を解除する (ユーザー要望: 「フォーカスが離れたら選択も離れる」)。
        # preview pane や他の widget へのフォーカス移動には反応しない。
        self.inbox_pane.table.installEventFilter(self)
        self.case_pane.table.installEventFilter(self)


    def _build_menus(self, mb: QMenuBar) -> None:
        # M1 で実動するのは「終了」「k-file について」のみ。
        # M2〜M5 で実装する項目は disabled (グレーアウト) で配置し、
        # 各マイルストーンで setEnabled(True) + slot 結線していく。
        m_file = mb.addMenu("ﾌｧｲﾙ(&F)")
        act_open_case = QAction("事件を開く(&O)…", self)
        act_open_case.setShortcut(QKeySequence("Ctrl+O"))
        act_open_case.triggered.connect(self._on_open_case)
        m_file.addAction(act_open_case)
        m_file.addSeparator()
        act_quit = QAction("終了(&X)", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_edit = mb.addMenu("編集(&E)")
        self.act_undo = QAction("元に戻す(&U)", self)
        self.act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.act_undo.setEnabled(False)  # 履歴が空のうちは無効、_refresh_undo_state で更新
        self.act_undo.triggered.connect(self._on_undo)
        m_edit.addAction(self.act_undo)
        m_edit.addSeparator()
        act_history = QAction("投入履歴(&H)…", self)
        act_history.setShortcut(QKeySequence("F12"))
        act_history.triggered.connect(self._show_history)
        m_edit.addAction(act_history)
        m_edit.addSeparator()
        act_trash = QAction("ごみ箱を開く(&T)", self)
        act_trash.setToolTip("削除済ファイルを Windows のごみ箱で復元する")
        act_trash.triggered.connect(self._open_recycle_bin)
        m_edit.addAction(act_trash)

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
        m_tools = mb.addMenu("ﾂｰﾙ(&T)")
        act_settings = QAction("設定(&S)…", self)
        act_settings.triggered.connect(self._on_settings)
        m_tools.addAction(act_settings)

        m_help = mb.addMenu("ﾍﾙﾌﾟ(&H)")
        act_about = QAction("K-FILE について(&A)", self)
        act_about.triggered.connect(self._on_about)
        m_help.addAction(act_about)

    def _on_strip_subfolder(self, view_id: int) -> None:
        """中央ストリップの数字ボタン: 選択中 → 投入、未選択 → 閲覧のみ。"""
        has_inbox = self.inbox_pane.selected_file() is not None
        self.case_pane.trigger_subfolder_action(view_id, has_inbox=has_inbox)

    def _sync_strip_targets(self) -> None:
        """事件・サブフォルダ構成の変化に合わせて数字ボタンを並べ直す。"""
        self.command_strip.set_subfolder_targets(
            self.case_pane.subfolder_button_targets()
        )

    def _on_strip_return_to_desktop(self) -> None:
        """<<: 中央ペイン選択ファイルを実デスクトップへ戻す (一時保留)。

        デスクトップは OS 管理なので消えない。ユーザーがあとで実 Desktop を
        Inbox 監視対象に追加していれば、そのまま Inbox に再表示されて再投入
        できる (M5 設定ダイアログで構成可)。
        """
        entry = self.case_pane.selected_entry()
        if entry is None:
            self.statusBar().showMessage(
                "デスクトップへ送るファイルが選択されていません", 3000
            )
            return
        path, is_dir = entry
        if is_dir:
            self.statusBar().showMessage(
                "フォルダはデスクトップへ送れません (ファイルのみ)", 3000
            )
            return
        from src.infra.folder_shortcut import detect_desktop_dir
        desktop = detect_desktop_dir()
        if not desktop.is_dir():
            self.statusBar().showMessage(
                f"デスクトップが見つかりません: {desktop}", 5000
            )
            return
        # PDF プレビューが掴んでいると move 失敗するため明示クリア
        self.preview_pane.clear()
        result = file_ops.move(path, desktop)
        if not result.ok:
            self.statusBar().showMessage(
                f"デスクトップへ送れませんでした: {result.error}", 6000
            )
            return
        # << で運んだファイルは「今これから再仕分けする」アクティブ対象。
        # Inbox の cutoff_days フィルタ (Desktop は 7 日) で古い PDF が隠れて
        # 別事件に運べない問題を避けるため mtime を現在時刻に更新する。
        # PDF 内部の作成日メタデータは無傷、FS の mtime のみ更新。Win/Linux 共通。
        if result.dst is not None:
            try:
                import os
                os.utime(str(result.dst), None)
            except OSError:
                pass    # mtime 更新失敗は致命的でない (フィルタで隠れるだけ)
        code, _ = self.case_pane.current_case()
        self._record_history(
            action="move",
            src_path=str(result.src),
            dst_path=str(result.dst) if result.dst else None,
            case_code=code,
            category="→ Desktop",
            renamed_to=result.renamed_to,
            original_name=result.original_name,
        )
        self.case_pane.refresh_current_view()
        if result.collided:
            self.statusBar().showMessage(
                f"{result.original_name} → Desktop "
                f"(衝突を回避して {result.renamed_to})", 5000,
            )
        else:
            self.statusBar().showMessage(
                f"{result.renamed_to} を {code} からデスクトップへ送りました", 4000,
            )

    def _on_strip_ignore(self) -> None:
        """無視: Inbox 選択ファイルの「無視」を切替 (実ファイルは触らない)。"""
        if not self.inbox_pane.toggle_ignore_selected():
            self.statusBar().showMessage(
                "選択中の Inbox ファイルがありません", 3000
            )

    def _on_strip_delete(self) -> None:
        """削除: 選択ファイルを OS ごみ箱へ (Inbox 優先 → 中央)。"""
        if self.inbox_pane.selected_file() is not None:
            self.inbox_pane.delete_selected()
        elif self.case_pane.selected_entry() is not None:
            self.case_pane.delete_selected_row()
        else:
            self.statusBar().showMessage(
                "削除する行が選択されていません", 3000
            )

    def _on_fn_key(self, k: int) -> None:
        """ファンクションキーバーのセルクリック (enabled なものだけ届く)。"""
        if k == 2:
            self._on_rename_in_case()
        elif k == 3:
            self._toggle_preview()
        elif k == 5:
            self.inbox_pane.refresh()
        elif k == 6:
            self._open_quick_folder("notes")
        elif k == 7:
            self._open_quick_folder("temp")
        elif k == 8:
            # F8: 中央ペイン優先 (フォーカス問わず)。Inbox の削除は Del を推奨。
            self.case_pane.delete_selected_row()
        elif k == 12:
            self._show_history()

    def _focus_inbox_table(self) -> None:
        """Tab from case → Inbox に focus 移動。元ペインの選択は解除して
        プレビューも閉じる (ユーザー要望: 「フォーカスが離れたら選択も離れる」)。"""
        self.case_pane.table.clearSelection()
        self.case_pane.table.setCurrentCell(-1, -1)
        self.preview_pane.clear()
        t = self.inbox_pane.table
        t.setFocus()
        if t.currentRow() < 0 and t.rowCount() > 0:
            t.setCurrentCell(0, 0)

    def _focus_case_table(self) -> None:
        """Tab from Inbox → 中央テーブルに focus 移動。元ペインの選択は解除して
        プレビューも閉じる (ユーザー要望: 「フォーカスが離れたら選択も離れる」)。"""
        self.inbox_pane.table.clearSelection()
        self.inbox_pane.table.setCurrentCell(-1, -1)
        self.preview_pane.clear()
        t = self.case_pane.table
        t.setFocus()
        if t.currentRow() < 0 and t.rowCount() > 0:
            t.setCurrentCell(0, 0)

    def _refresh_quick_slots(self) -> None:
        """F6 / F7 セルのラベルと enabled 状態を設定値から再構築。"""
        notes = (self.db.get_setting(KEY_QUICK_NOTES, "") or "").strip()
        temp = (self.db.get_setting(KEY_QUICK_TEMP, "") or "").strip()
        notes_ok = bool(notes) and Path(notes).is_dir()
        temp_ok = bool(temp) and Path(temp).is_dir()
        self.fn_bar.set_slot(
            6, "雑記録", enabled=notes_ok,
            tooltip=f"F6: 雑記録フォルダを開く\n{notes}" if notes_ok else
            "F6: 雑記録 (ツール→設定で パス指定すると有効)",
        )
        self.fn_bar.set_slot(
            7, "一時保管", enabled=temp_ok,
            tooltip=f"F7: 一時保管フォルダを開く\n{temp}" if temp_ok else
            "F7: 一時保管 (ツール→設定で パス指定すると有効)",
        )

    def _open_quick_folder(self, kind: str) -> None:
        """F6/F7: 雑記録 or 一時保管 を case_pane のタブとして開く。"""
        key = KEY_QUICK_NOTES if kind == "notes" else KEY_QUICK_TEMP
        label = "雑記録" if kind == "notes" else "一時保管"
        path_str = (self.db.get_setting(key, "") or "").strip()
        if not path_str:
            self.statusBar().showMessage(
                f"{label} のパスが未設定です (ツール→設定…)", 4000
            )
            return
        path = Path(path_str)
        if not path.is_dir():
            self.statusBar().showMessage(
                f"{label} のフォルダが見つかりません: {path}", 5000
            )
            return
        self.case_pane.add_case_tab(path)

    def _case_repo(self) -> CaseRepo | None:
        """ksystemz.db への RO 接続を遅延作成 (Ctrl+O / セッション復元 等で使う)。

        設定の `ksystemz_db_path` を優先、未設定なら dev fallback
        (`~/k-file-test-data/ksystemz.db`)。ファイルが無ければ None。
        """
        if getattr(self, "_repo_cache", None) is not None:
            return self._repo_cache
        path_str = self.db.get_setting("ksystemz_db_path", "") or ""
        if not path_str:
            fallback = Path.home() / "k-file-test-data" / "ksystemz.db"
            if fallback.is_file():
                path_str = str(fallback)
        if not path_str:
            return None
        try:
            self._repo_cache = CaseRepo(Path(path_str))
        except FileNotFoundError:
            return None
        return self._repo_cache

    def _safe_doc_root(self) -> Path | None:
        """case_pane の doc_root getter 用 (例外を抑えて Path or None を返す)。"""
        repo = self._case_repo()
        if repo is None:
            return None
        try:
            return repo.doc_root()
        except OSError:
            return None

    def _on_case_shortcut(self, target_path: str) -> None:
        """B フォルダ内 A symlink ダブルクリック → A のタブに切替。"""
        target = Path(target_path)
        self.case_pane.add_case_tab(target)
        code, _ = _parse_case(target)
        self.statusBar().showMessage(f"事件ショートカットを開きました: {code}", 3000)

    def _open_inbox_folder(self, path_str: str) -> None:
        """Inbox のフォルダ行ダブルクリック → 事件タブで開く (汎用ファイラー動線)。"""
        p = Path(path_str)
        if p.is_dir():
            self.case_pane.add_case_tab(p)

    def _open_initial_paths(self) -> None:
        """CLI 引数で渡されたフォルダを順次タブに追加 (K-SystemZ 連携用)。

        セッション復元の後に呼ばれる。add_case_tab は重複時に既存タブへ切替
        するので、前回開いていた事件と同じ path が CLI から来てもダブらない。
        最後の path がアクティブタブになる (subprocess.Popen で呼んだ K-SystemZ
        側の意図する事件が前面に出る)。
        """
        if not self._initial_paths:
            return
        opened = 0
        for p in self._initial_paths:
            try:
                if p.is_dir():
                    self.case_pane.add_case_tab(p)
                    opened += 1
            except OSError:
                continue
        if opened:
            self.statusBar().showMessage(
                f"コマンドライン引数から {opened} 件のフォルダを開きました", 4000
            )

    def _restore_session(self) -> None:
        """前回 open_tabs に保存されていた事件を順次タブに復元。

        repo が未設定 / 該当事件フォルダが見つからない場合はその case_code は
        スキップ (静かに無視、ステータスバーで件数のみ報告)。
        """
        codes = self.db.open_tab_codes()
        if not codes:
            return
        repo = self._case_repo()
        if repo is None:
            return
        restored = 0
        skipped: list[str] = []
        for code in codes:
            folder = repo.resolve_folder(code)
            if folder is not None:
                self.case_pane.add_case_tab(folder)
                restored += 1
            else:
                skipped.append(code)
        if restored:
            msg = f"前回のセッションを復元: {restored} 件"
            if skipped:
                msg += f" (未解決 {len(skipped)} 件)"
            self.statusBar().showMessage(msg, 4000)

    def _save_open_tabs(self) -> None:
        """case_pane の現タブ構成を open_tabs テーブルに永続化。"""
        codes: list[str] = []
        for p in self.case_pane.case_paths():
            code, _ = _parse_case(p)
            if code:
                codes.append(code)
        self.db.save_open_tabs(codes)

    # ───────── 外部フォルダの D&D で事件タブ追加 ─────────

    def dragEnterEvent(self, e) -> None:
        # k-file 内部の D&D (text/uri-list + x-kfile-source) はサブフォルダボタン /
        # 事件タブが処理するので、MainWindow は手を出さない。
        from src.ui.dnd import kfile_source_of
        if kfile_source_of(e.mimeData()) is not None:
            e.ignore()
            return
        # OS ファイラー等からの「フォルダ」を 1 個以上含む drop だけ受け入れる
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                if url.isLocalFile() and Path(url.toLocalFile()).is_dir():
                    e.acceptProposedAction()
                    return
        e.ignore()

    def dragMoveEvent(self, e) -> None:
        # dragEnterEvent と同条件で accept (Qt のお作法上、両方実装が必要)
        from src.ui.dnd import kfile_source_of
        if kfile_source_of(e.mimeData()) is not None:
            e.ignore()
            return
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                if url.isLocalFile() and Path(url.toLocalFile()).is_dir():
                    e.acceptProposedAction()
                    return
        e.ignore()

    def dropEvent(self, e) -> None:
        from src.ui.dnd import kfile_source_of
        if kfile_source_of(e.mimeData()) is not None:
            e.ignore()
            return
        added = 0
        for url in e.mimeData().urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if p.is_dir():
                self.case_pane.add_case_tab(p)
                added += 1
        if added:
            e.acceptProposedAction()
            self.statusBar().showMessage(f"事件タブを追加: {added} 件 (フォルダ D&D)", 4000)
        else:
            e.ignore()

    def _on_settings(self) -> None:
        """ツール → 設定…: Inbox 監視先 / ksystemz.db パス を編集。"""
        current = self.inbox_pane._sources
        dlg = SettingsDialog(self.db, current, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # Inbox 監視先を即時反映
        self.inbox_pane.reload_sources(dlg.applied_sources())
        # ksystemz.db のキャッシュを破棄 (次回 Ctrl+O で新パスを再オープン)
        self._repo_cache = None
        # F6/F7 クイック起動セルも再構築 (パス変更/追加を反映)
        self._refresh_quick_slots()
        self.statusBar().showMessage("設定を保存しました", 4000)

    def _on_open_case(self) -> None:
        """Ctrl+O / ファイル→事件を開く: ksystemz から検索して事件タブ追加。"""
        repo = self._case_repo()
        if repo is None:
            self.statusBar().showMessage(
                "ksystemz.db のパスが未設定です (ツール→設定…で指定)", 5000
            )
            return
        dlg = OpenCaseDialog(repo, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rec = dlg.selected()
        if rec is None:
            return
        folder = repo.resolve_folder(rec.case_code)
        if folder is None:
            self.statusBar().showMessage(
                f"事件フォルダが見つかりません: {rec.case_code}", 5000
            )
            return
        self.case_pane.add_case_tab(folder)
        self.statusBar().showMessage(
            f"事件タブを開きました: {rec.case_code} {rec.client_display}", 4000
        )

    def _open_recycle_bin(self) -> None:
        """編集→ごみ箱を開く: OS ネイティブのごみ箱ウインドウを起動。"""
        ok, msg = open_recycle_bin()
        self.statusBar().showMessage(msg, 4000 if ok else 6000)

    def _show_history(self) -> None:
        """F12 / 編集→投入履歴: 履歴ダイアログを開く。"""
        dlg = HistoryDialog(self.db, parent=self)
        dlg.exec()
        if dlg.any_undone():
            self.inbox_pane.refresh()
            self.case_pane.refresh_current_view()
            self._refresh_undo_state()

    def _toggle_preview(self) -> None:
        """F3 / bar の F3 クリック: プレビュー開閉 (1:1 ↔ 1:2:2)。

        閉じる時は QPdfDocument を明示的に close してファイルロックを解放
        (見えなくなっても document を保持していると Win で削除/移動が
        失敗する。バグ報告: 2026-05-25 本番テスト)。
        """
        self._preview_visible = not self._preview_visible
        if not self._preview_visible:
            self.preview_pane.clear()
        self._apply_pane_layout()

    def eventFilter(self, obj, e) -> bool:  # noqa: N802 (Qt override)
        """Inbox / 中央テーブル の focus 切替で互いの選択を解除する。"""
        if e.type() == QEvent.Type.FocusIn:
            if obj is self.inbox_pane.table:
                self.case_pane.table.clearSelection()
                self.case_pane.table.setCurrentCell(-1, -1)
            elif obj is self.case_pane.table:
                self.inbox_pane.table.clearSelection()
                self.inbox_pane.table.setCurrentCell(-1, -1)
        return super().eventFilter(obj, e)

    def changeEvent(self, e) -> None:
        """ウインドウのアクティブ状態が変わった時に preview を閉じる。

        ユーザーが別アプリ (ブラウザ等) に切り替えた瞬間に PDF ハンドルが
        解放されるので、Explorer から直接そのファイルを削除/移動できる。
        次にアクティブに戻ってきても、現選択行で再 load されるだけで支障なし。

        ただし「自前 modal dialog (rename 等) を開いた瞬間」も非アクティブ化と
        して扱われるため、`_internal_modal_count > 0` の時はスキップして
        preview を維持する (プレビューを見ながらのリネーム操作に対応)。
        """
        super().changeEvent(e)
        if e.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            if self._internal_modal_count > 0:
                return  # 自前 modal: preview 維持
            if hasattr(self, "preview_pane"):
                self.preview_pane.clear()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        # ウインドウサイズ変化のたびに「Inbox 幅 ≒ 中央ファイル一覧幅」を再計算。
        # 注: この時点ではまだ splitter のサイズは古い (Qt のレイアウトパスが
        # この後に走る) ため、QTimer.singleShot(0) で 1tick 遅らせて
        # レイアウト確定後に呼ぶ。
        if hasattr(self, "splitter"):
            QTimer.singleShot(0, self._apply_pane_layout)

    def closeEvent(self, e) -> None:
        """終了時に現在のウインドウサイズを kfile.db に保存 (次回起動で復元)。"""
        if hasattr(self, "db"):
            try:
                self.db.set_setting("window_width", str(self.width()))
                self.db.set_setting("window_height", str(self.height()))
                self.db.set_setting(
                    "window_maximized", "1" if self.isMaximized() else "0"
                )
            except Exception:
                pass    # 保存失敗は致命的でない (次回 既定サイズで起動)
        super().closeEvent(e)

    def _restore_window_size(self) -> None:
        """前回保存したウインドウサイズを復元 (なければ既定 1400x860 のまま)。"""
        w_str = self.db.get_setting("window_width", "") or ""
        h_str = self.db.get_setting("window_height", "") or ""
        maxed = (self.db.get_setting("window_maximized", "0") or "0") == "1"
        try:
            if w_str and h_str:
                w, h = int(w_str), int(h_str)
                if 400 <= w <= 10000 and 300 <= h <= 10000:
                    self.resize(w, h)
        except ValueError:
            pass
        if maxed:
            self.showMaximized()

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
            # 3 カラム時も「Inbox 幅 ≒ 中央ファイル一覧幅」を維持。
            # offset = strip + _CASE_LEFT_OFFSET。center = inbox + offset。
            # preview は残り (結果 2*inbox の幅になり、概ね 1:1:2 に近い割り付け)。
            offset = strip + _CASE_LEFT_OFFSET
            inbox = max((usable - offset) // 4, 100)
            center_w = inbox + offset
            self.splitter.setSizes([inbox, center_w, usable - inbox - center_w])
        else:
            self.preview_pane.setVisible(False)
            usable = total - handle
            inbox = max((usable - strip - _CASE_LEFT_OFFSET) // 2, 100)
            self.splitter.setSizes([inbox, usable - inbox, 0])
        # プレビュー表示時は左右ペインが狭くなるので Name 列のみに絞る
        self.inbox_pane.set_compact(self._preview_visible)
        self.case_pane.set_compact(self._preview_visible)

    def _on_about(self) -> None:
        AboutDialog(self).exec()

    def _on_inbox_changed(self, count: int) -> None:
        self._inbox_count = count
        self._update_idle_status()

    def _update_path_status(self, *_args) -> None:
        """ステータスバー右側の「選択ファイルのフルパス」表示を更新する。

        signal の sender でどちらのペインで操作があったかを判定し、そのペインの
        選択を表示する。同ペインで複数行選択時は <複数選択>。未選択なら空。
        (Inbox / 中央のテーブルはどちらも SingleSelection だが、将来 multi 化
        した場合に対応できるよう selectedRows で件数を見る)
        """
        sender = self.sender()
        if sender is self.inbox_pane.table.selectionModel():
            rows = sender.selectedRows()
            if len(rows) > 1:
                text = "<複数選択>"
            elif rows:
                f = self.inbox_pane.selected_file()
                text = str(f.path) if f is not None else ""
            else:
                text = ""
            self.path_status_label.setText(text)
            return
        if sender is self.case_pane.table.selectionModel():
            rows = sender.selectedRows()
            if len(rows) > 1:
                text = "<複数選択>"
            elif rows:
                entry = self.case_pane.selected_entry()
                text = str(entry[0]) if entry is not None else ""
            else:
                text = ""
            self.path_status_label.setText(text)

    def _update_idle_status(self) -> None:
        n = self.db.undoable_count() if hasattr(self, "db") else 0
        self.statusBar().showMessage(
            f"準備完了 — Inbox {self._inbox_count} 件 / Undo {n} 段"
        )

    def _record_history(self, **kwargs) -> int:
        """db.record_history のラッパ。記録後に Undo 状態を refresh。"""
        eid = self.db.record_history(**kwargs)
        self._refresh_undo_state()
        return eid

    def _refresh_undo_state(self) -> None:
        """↶ ボタンと「元に戻す」メニュー、ステータスバー Undo 段数を再計算。"""
        n = self.db.undoable_count()
        self.command_strip.btn_undo.setEnabled(n > 0)
        self.act_undo.setEnabled(n > 0)
        self._update_idle_status()

    def _on_undo(self) -> None:
        """Ctrl+Z / ↶ / 編集→元に戻す: 最新の Undo 可能履歴を逆実行。"""
        row = self.db.last_undoable_entry()
        if row is None:
            self.statusBar().showMessage("Undo するアクションがありません", 3000)
            return
        ok, msg = undo_ops.undo_action(row)
        if not ok:
            self.statusBar().showMessage(f"Undo 失敗: {msg}", 6000)
            return
        self.db.mark_undone(int(row["id"]))
        # 影響を受けるペインを再走査
        self.inbox_pane.refresh()
        self.case_pane.refresh_current_view()
        self._refresh_undo_state()
        self.statusBar().showMessage(f"Undo: {msg}", 4000)

    def _on_case_tab_changed(self, idx: int, code: str, name: str) -> None:
        self.statusBar().showMessage(f"事件タブ切替 → {code}  {name}", 3000)

    def _on_subfolder_browsed(self, idx: int, folder_name: str) -> None:
        code, _ = self.case_pane.current_case()
        self.statusBar().showMessage(f"{code} / {folder_name} を表示", 2000)

    def _batch_inject(
        self,
        srcs: list[Path],
        target_dir: Path,
        category: str,
        suffix: str = "",
    ) -> None:
        """N ファイルを target_dir に順次 inject。各 ok 件で history 記録 +
        ステータスメッセージを集計して 1 行で報告 (UX 簡潔化)。"""
        if not srcs:
            return
        # inject = Copy → 検証 → 元削除。元削除フェーズで Win のファイルロック
        # (PDF プレビューが掴んでいる) があると unlink が失敗するため、開始前に
        # preview を強制クローズしてハンドルを解放する。
        self.preview_pane.clear()
        code, _ = self.case_pane.current_case()
        ok_n = 0
        collided_n = 0
        fails: list[str] = []
        last_name = ""
        for src in srcs:
            result = file_ops.inject(src, target_dir)
            if not result.ok:
                fails.append(f"{src.name}: {result.error}")
                continue
            ok_n += 1
            last_name = result.renamed_to or src.name
            if result.collided:
                collided_n += 1
            self._record_history(
                action="inject",
                src_path=str(result.src),
                dst_path=str(result.dst) if result.dst else None,
                case_code=code,
                category=category,
                renamed_to=result.renamed_to,
                original_name=result.original_name,
            )
        self.inbox_pane.refresh()
        self.case_pane.refresh_current_view()

        if ok_n == 1 and not fails:
            collide = "  衝突を回避" if collided_n else ""
            self.statusBar().showMessage(
                f"{last_name} → {code} / {category}{collide} に投入{suffix}",
                4000,
            )
        elif ok_n >= 1:
            msg = f"{ok_n} ファイルを {code} / {category} に投入{suffix}"
            if collided_n:
                msg += f" (衝突回避 {collided_n} 件)"
            if fails:
                msg += f" / 失敗 {len(fails)} 件"
            self.statusBar().showMessage(msg, 5000)
        else:
            self.statusBar().showMessage(
                f"投入失敗: {'; '.join(fails[:2])}", 6000
            )

    def _on_subfolder_inject_requested(
        self, view_id: int, folder_name: str
    ) -> None:
        """Alt+0〜9 / 右クリック / ストリップ数字ボタン: Inbox 選択ファイルを
        全件即投入 (multi-select 対応)。rename ダイアログは出さない (素早く
        実行が原則 — rename したい時は F2 で別途行う)。衝突時は自動連番。"""
        files = self.inbox_pane.selected_files()
        if not files:
            self.statusBar().showMessage(
                "投入する Inbox ファイルが未選択です", 3000
            )
            return
        target_dir = self.case_pane.view_target_dir(view_id)
        if target_dir is None:
            self.statusBar().showMessage(
                f"投入先が見つかりません: {folder_name}", 3000
            )
            return
        self._batch_inject([f.path for f in files], target_dir, folder_name)

    def _on_inbox_drop_inject(
        self, view_id: int, folder_name: str, src_paths: list[str]
    ) -> None:
        """Inbox ファイル群をサブフォルダボタンに D&D 投入 (rename なし即時)。"""
        target_dir = self.case_pane.view_target_dir(view_id)
        if target_dir is None:
            self.statusBar().showMessage(
                f"投入先が見つかりません: {folder_name}", 3000
            )
            return
        self._batch_inject(
            [Path(p) for p in src_paths], target_dir, folder_name,
            suffix=" (D&D)",
        )

    def _on_inbox_drop_to_folder(
        self, target_dir: str, src_paths: list[str]
    ) -> None:
        """Inbox ファイル群をファイル一覧内の任意フォルダ (孫含む) に D&D 投入。"""
        target = Path(target_dir)
        # category 表示用に「親サブフォルダ/孫フォルダ」のような相対パス
        case_root = self.case_pane.current_case_path()
        try:
            rel = (
                str(target.relative_to(case_root)) if case_root else target.name
            )
        except ValueError:
            rel = target.name
        self._batch_inject(
            [Path(p) for p in src_paths], target, rel, suffix=" (D&D)",
        )

    def _do_cross_case_op(
        self,
        op: str,                                       # "move" or "copy"
        target_case_root: Path,
        target_dir_resolver: Callable[[Path], Path],   # src → 投入先
        src_paths: list[str],
    ) -> None:
        """cross-case Move/Copy の共通ループ。`target_dir_resolver` は src ごと
        に投入先フォルダを返す。D&D 経路では「同名サブフォルダ自動マッピング」
        を渡し、右クリック明示経路では「固定 target_dir」を渡す。

        履歴 / ステータスバー / refresh は全てここで処理する。
        """
        src_case_root = self.case_pane.current_case_path()
        op_label = "コピー" if op == "copy" else "移動"
        if src_case_root is not None and target_case_root == src_case_root:
            self.statusBar().showMessage(
                f"同じ事件タブには{op_label}できません", 3000
            )
            return
        target_code, _ = _parse_case(target_case_root)
        op_fn = file_ops.copy if op == "copy" else file_ops.move
        ok_n = 0
        collided_n = 0
        fails: list[str] = []
        last_label = ""
        last_category = ""
        for src_str in src_paths:
            src = Path(src_str)
            if not src.exists():
                fails.append(f"{src.name}: 元ファイルが消えています")
                continue
            target_dir = target_dir_resolver(src)
            category = (
                target_dir.name if target_dir != target_case_root else "(直下)"
            )
            result = op_fn(src, target_dir)
            if not result.ok:
                fails.append(f"{src.name}: {result.error}")
                continue
            ok_n += 1
            last_label = result.renamed_to or src.name
            last_category = category
            if result.collided:
                collided_n += 1
            self._record_history(
                action=op,
                src_path=str(result.src),
                dst_path=str(result.dst) if result.dst else None,
                case_code=target_code,
                category=category,
                renamed_to=result.renamed_to,
                original_name=result.original_name,
            )
        # Move は src 側のタブ表示が変わるため refresh が必須。Copy も target タブ
        # が現在表示中の場合に再描画が必要なので一律呼ぶ。
        self.case_pane.refresh_current_view()

        if ok_n == 1 and not fails:
            collide = "  衝突を回避" if collided_n else ""
            sep = "→" if op == "move" else "を"
            self.statusBar().showMessage(
                f"{last_label} {sep} {target_code} / {last_category}{collide} に{op_label}",
                4000,
            )
        elif ok_n >= 1:
            msg = f"{ok_n} ファイルを {target_code} に{op_label}"
            if collided_n:
                msg += f" (衝突回避 {collided_n} 件)"
            if fails:
                msg += f" / 失敗 {len(fails)} 件"
            self.statusBar().showMessage(msg, 5000)
        else:
            self.statusBar().showMessage(
                f"{op_label}失敗: {'; '.join(fails[:2])}", 6000
            )

    def _automap_resolver(
        self, target_case_root: Path, src_case_root: Path | None
    ) -> Callable[[Path], Path]:
        """D&D 用の resolver: src の所属サブフォルダ名と同名のサブフォルダが
        target_case_root にあればそこへ、なければ target_case_root 直下へ。"""
        def resolve(src: Path) -> Path:
            if src_case_root is None:
                return target_case_root
            try:
                rel_parts = src.parent.relative_to(src_case_root).parts
            except ValueError:
                return target_case_root
            if rel_parts:
                candidate = target_case_root / rel_parts[0]
                if candidate.is_dir():
                    return candidate
            return target_case_root
        return resolve

    def _on_case_tab_drop_move(
        self, target_idx: int, src_paths: list[str]
    ) -> None:
        """事件タブへの D&D = クロス事件 Move (multi-select、同名サブフォルダ自動マッピング)。"""
        case_paths = self.case_pane._case_paths
        if not 0 <= target_idx < len(case_paths):
            return
        # Move は shutil.move なので Win 側でファイルロックがあると失敗する
        self.preview_pane.clear()
        target_case_root = case_paths[target_idx]
        resolver = self._automap_resolver(
            target_case_root, self.case_pane.current_case_path()
        )
        self._do_cross_case_op("move", target_case_root, resolver, src_paths)

    def _on_case_tab_drop_copy(
        self, target_idx: int, src_paths: list[str]
    ) -> None:
        """事件タブへの Ctrl+D&D = クロス事件 Copy (multi-select、自動マッピング)。
        元ファイルは src 事件側に残る。Undo は dst を OS ごみ箱へ。"""
        case_paths = self.case_pane._case_paths
        if not 0 <= target_idx < len(case_paths):
            return
        # Copy は src を読むだけだが PDF ロック解放のため Move と同じく事前に clear
        self.preview_pane.clear()
        target_case_root = case_paths[target_idx]
        resolver = self._automap_resolver(
            target_case_root, self.case_pane.current_case_path()
        )
        self._do_cross_case_op("copy", target_case_root, resolver, src_paths)

    def _on_case_explicit_op(
        self, op: str, target_dir_str: str, src_paths: list[str]
    ) -> None:
        """右クリック「他事件へコピー/移動 → サブフォルダ」(B 案、明示指定経路)。

        target_dir は呼び出し側が指定する固定パス。所属事件タブを逆引きして
        共通ループへ流す。auto-mapping は使わない (D&D 経路と動線を分離)。
        """
        target_dir = Path(target_dir_str)
        case_paths = self.case_pane._case_paths
        target_case_root: Path | None = None
        for cp in case_paths:
            if target_dir == cp:
                target_case_root = cp
                break
            try:
                target_dir.relative_to(cp)
                target_case_root = cp
                break
            except ValueError:
                continue
        if target_case_root is None:
            self.statusBar().showMessage(
                "投入先の事件タブが見つかりません", 3000
            )
            return
        self.preview_pane.clear()
        self._do_cross_case_op(
            op, target_case_root, lambda _src: target_dir, src_paths,
        )

    def _on_rename_in_case(self) -> None:
        """F2: 中央ペインで選択中のファイル/フォルダの名前変更。"""
        entry = self.case_pane.selected_entry()
        if entry is None:
            self.statusBar().showMessage(
                "F2: 名前変更する行が選択されていません", 3000
            )
            return
        path, _is_dir = entry

        dlg = RenameDialog(
            original_name=path.name,
            recent=self.db.recent_names(),
            mode="rename",
            parent=self,
        )
        # 自前 modal を示すカウンタを立てて preview を維持 (Issue 2 対策)
        self._internal_modal_count += 1
        try:
            accepted = dlg.exec() == RenameDialog.DialogCode.Accepted
        finally:
            self._internal_modal_count -= 1
        if not accepted:
            return
        new_name = dlg.chosen_name()

        # Win では QPdfDocument がファイルを掴んだままだと rename も失敗するため
        # ダイアログ確定後・rename 実行直前にプレビューを閉じてハンドル解放
        self.preview_pane.clear()
        result = file_ops.rename(path, new_name)
        if not result.ok:
            self.statusBar().showMessage(f"名前変更失敗: {result.error}", 6000)
            return
        if result.dst is None or result.dst == path:
            # 変更なし (同名で OK 押下) — 何もしない
            return

        code, _ = self.case_pane.current_case()
        self._record_history(
            action="rename",
            src_path=str(result.src),
            dst_path=str(result.dst),
            case_code=code,
            category="",          # rename はフォルダをまたがない
            renamed_to=result.renamed_to,
            original_name=result.original_name,
        )
        if new_name != result.original_name:
            self.db.add_recent_name(new_name)

        self.case_pane.refresh_current_view()
        # rename 後も同じファイルを選択中に保ちプレビューを継続
        if result.dst is not None:
            self.case_pane.select_path_in_table(result.dst)

        if result.collided:
            self.statusBar().showMessage(
                f"{result.original_name} → {result.renamed_to} "
                "(衝突を回避して連番を付与)", 5000,
            )
        else:
            self.statusBar().showMessage(
                f"{result.original_name} → {result.renamed_to} に変更", 4000,
            )

    def _on_case_delete(self, path_str: str) -> None:
        """中央ペインから Del / − ボタン経由の削除要求。"""
        path = Path(path_str)
        # Win 側で PDF プレビューがファイルを掴んだままだと send2trash が失敗する
        self.preview_pane.clear()
        result = file_ops.trash(path)
        if not result.ok:
            self.statusBar().showMessage(f"削除失敗: {result.error}", 6000)
            return
        code, _ = self.case_pane.current_case()
        # 削除前のパスから category を推測 (事件 root 直下なら "(直下)")
        case_root = self.case_pane.current_case_path()
        category = "(直下)"
        if case_root is not None:
            try:
                rel = path.relative_to(case_root)
                category = rel.parts[0] if rel.parts else "(直下)"
            except ValueError:
                category = "?"
        self._record_history(
            action="trash",
            src_path=str(path),
            dst_path=None,
            case_code=code,
            category=category,
            renamed_to=path.name,
            original_name=path.name,
        )
        self.case_pane.refresh_current_view()
        self.statusBar().showMessage(
            f"{path.name} を OS のごみ箱へ — 復元は編集メニュー→ごみ箱を開く", 5000
        )

    def _on_inbox_delete(self, path_str: str) -> None:
        """Inbox ペインから Del 経由の削除要求。"""
        path = Path(path_str)
        # 出所ラベル特定 (history 用の category)
        source_label = ""
        sf = self.inbox_pane.selected_file()
        if sf is not None and str(sf.path) == path_str:
            source_label = sf.source
        # PDF プレビューが掴んでいる状態だと Win で削除失敗するため明示クリア
        self.preview_pane.clear()
        result = file_ops.trash(path)
        if not result.ok:
            self.statusBar().showMessage(f"削除失敗: {result.error}", 6000)
            return
        self._record_history(
            action="trash",
            src_path=str(path),
            dst_path=None,
            case_code="",
            category=source_label,
            renamed_to=path.name,
            original_name=path.name,
        )
        self.inbox_pane.refresh()
        self.statusBar().showMessage(
            f"{path.name} を OS のごみ箱へ — 復元は編集メニュー→ごみ箱を開く", 5000
        )

    def _on_rename_in_inbox(self) -> None:
        """F2: Inbox で選択中ファイルの名前変更。

        Inbox のファイルは scan/Desktop/作業 等の元フォルダにある実ファイル。
        ここで rename すると元フォルダのファイル名そのものが変わる。
        """
        f = self.inbox_pane.selected_file()
        if f is None:
            self.statusBar().showMessage(
                "F2: 名前変更する Inbox ファイルが選択されていません", 3000
            )
            return

        dlg = RenameDialog(
            original_name=f.name,
            recent=self.db.recent_names(),
            mode="rename",
            parent=self,
        )
        # 自前 modal を示すカウンタを立てて preview を維持 (Issue 2 対策)
        self._internal_modal_count += 1
        try:
            accepted = dlg.exec() == RenameDialog.DialogCode.Accepted
        finally:
            self._internal_modal_count -= 1
        if not accepted:
            return
        new_name = dlg.chosen_name()

        # Inbox 側もダイアログ確定後・rename 実行直前にプレビューを閉じる
        self.preview_pane.clear()
        result = file_ops.rename(f.path, new_name)
        if not result.ok:
            self.statusBar().showMessage(f"名前変更失敗: {result.error}", 6000)
            return
        if result.dst is None or result.dst == f.path:
            return  # 同名 OK = 何もしない

        # 履歴 (case_code は無いので空。category は Inbox の出所ラベルを使う)
        self._record_history(
            action="rename",
            src_path=str(result.src),
            dst_path=str(result.dst),
            case_code="",
            category=f.source,
            renamed_to=result.renamed_to,
            original_name=result.original_name,
        )
        if new_name != result.original_name:
            self.db.add_recent_name(new_name)

        # Inbox を再走査 (Watcher も発火するが手動でも更新)
        self.inbox_pane.refresh()
        if result.dst is not None:
            self.inbox_pane.select_path(result.dst)

        if result.collided:
            self.statusBar().showMessage(
                f"{result.original_name} → {result.renamed_to} "
                "(衝突を回避して連番を付与)", 5000,
            )
        else:
            self.statusBar().showMessage(
                f"{result.original_name} → {result.renamed_to} に変更 "
                f"({f.source})", 4000,
            )
