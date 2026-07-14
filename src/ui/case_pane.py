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

import unicodedata
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QSize, Qt, Signal
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QDrag, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core import file_ops
from src.ui import clipboard_ops
from src.infra.folder_shortcut import create_folder_shortcut, resolve_shortcut

from src.core.folder_scanner import (
    CaseScan,
    FileEntry,
    list_files,
    list_folder,
    scan_case_folder,
)
from src.ui._font_strategy import apply_bitmap_font_strategy
from src.ui.dnd import (
    SRC_CASE,
    SRC_INBOX,
    kfile_local_paths,
    kfile_source_of,
    make_drag_pixmap,
    make_kfile_mime_data,
)
from src.ui.pane_header import PaneHeader

# M2 dev: 事件フォルダの親 (doc_root)。M5 で ksystemz.db +「事件を開く」
# ダイアログ経由に置き換える。
_DEV_DOC_ROOT = Path.home() / "k-file-test-data" / "事件"

# 「事件フォルダ直下」ビューの ID (サブフォルダ index 0..N-1 と衝突しない値)
ROOT_VIEW_ID = 999


def format_size(n: int, unit: str = "KB") -> str:
    """バイト数を 3 桁カンマ区切りで返す (単位文字は付けない、InboxPane と同方式)。

    ヘッダー右クリックメニューで KB/MB 切替。KB は整数、MB は小数 1 桁。
    """
    if unit == "MB":
        return f"{n / (1024 * 1024):,.1f}"
    return f"{n // 1024:,}"


def _parse_case(path: Path) -> tuple[str, str]:
    """事件フォルダ名 → (case_code, タブ表示用ラベル)。

    対応する命名規則 (本番運用 2026-05 時点):
      1) `R08020011文書フォルダ(田中太郎)売買` (実環境の現行ルール)
         → ('R08020011', '田中太郎 売買')
      2) `R060200042 山田太郎 損害賠償` (旧/モック形式・スペース区切り)
         → ('R060200042', '山田太郎 損害賠償')
      3) 上記以外 → 名前全体を code、表示名は空

    タブ表示は「依頼者名 + 事件名」優先。case_code は K-SystemZ 連携キーなので
    タブ表示には出さない (タブのツールチップで案内、case_pane.add_case_tab 側)。
    括弧は半角 / 全角の両方を許容する (`(...)` / `（...）`)。

    ⚠ macOS はファイル名を NFD (濁点分解: 「ダ」= 「タ」+ U+3099) で返すことが
    あり、NFC のリテラル "文書フォルダ" と一致しない。照合前に必ず NFC 化する。
    Windows/Linux は既に NFC なので正規化しても無影響。
    """
    name = unicodedata.normalize("NFC", path.name)
    if "文書フォルダ" in name:
        idx = name.index("文書フォルダ")
        code = name[:idx]
        rest = name[idx + len("文書フォルダ"):]
        client = ""
        case_name = ""
        if rest[:1] in ("(", "（"):
            close_ch = ")" if rest[0] == "(" else "）"
            close_idx = rest.find(close_ch)
            if close_idx > 0:
                client = rest[1:close_idx].strip()
                case_name = rest[close_idx + 1:].strip()
            else:
                case_name = rest.strip()
        else:
            case_name = rest.strip()
        if client and case_name:
            display = f"{client} {case_name}"
        else:
            display = client or case_name
        return code, display
    # 旧形式 (モック / Linux dev): スペース区切り
    parts = name.split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return name, ""


def _tab_label(code: str, name: str) -> str:
    """タブに出す文字列。表示名が取れない命名のフォルダでも空タブにしない。

    _parse_case が命名規則に当てはまらないと判断した場合、表示名は空になるが
    (code = フォルダ名全体)、それをそのままタブに入れるとどの事件を開いている
    のか分からない「文字のないタブ」になる。その場合は code を出す。
    """
    return name or code


class _NameItem(QTableWidgetItem):
    """Name 列セル: フォルダを先頭にまとめ、各々名前順でソートする。

    表示文字列は拡張子を除いた stem (拡張子は別列に分離)。
    行がフォルダかどうか・実パスを保持し、ダブルクリック時の判定に使う。
    `..` 行 (is_parent=True) はフォルダの中でも別格で常に最先頭。
    """

    def __init__(
        self,
        name: str,                  # 表示文字列 (file=stem / folder=フォルダ名)
        is_dir: bool,
        path: Path,
        is_parent: bool = False,
        is_link: bool = False,
        ext: str = "",              # ソート時の補助キー (大文字、ドットなし)
    ) -> None:
        super().__init__(name)
        self.is_dir = is_dir
        self.path = path
        self.is_parent = is_parent
        self.is_link = is_link    # ショートカット (symlink/.lnk) なら True
        self.ext = ext

    def __lt__(self, other: QTableWidgetItem) -> bool:
        # PySide6 では super().__lt__() が再帰しクラッシュするため Python 側で比較
        if isinstance(other, _NameItem):
            if self.is_parent != other.is_parent:
                return self.is_parent   # ".." 行は常に最先頭
            if self.is_dir != other.is_dir:
                return self.is_dir       # フォルダを先頭へ
            # 同じ stem なら拡張子で安定化 (例: 報告書.pdf < 報告書.xlsx)
            s, o = self.text().casefold(), other.text().casefold()
            if s == o:
                return self.ext < other.ext
            return s < o
        return self.text().casefold() < other.text().casefold()


class _ExtItem(QTableWidgetItem):
    """拡張子列セル: 表示は大文字 (PDF/JPG/PNG)、行カテゴリ別の安定ソート用。

    フォルダ・".."・ショートカット行は ext='' で先頭にまとまる。
    """

    def __init__(self, ext: str, is_dir: bool, is_parent: bool = False) -> None:
        super().__init__(ext)
        self.is_dir = is_dir
        self.is_parent = is_parent
        self.ext = ext
        self.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _ExtItem):
            if self.is_parent != other.is_parent:
                return self.is_parent
            if self.is_dir != other.is_dir:
                return self.is_dir
            return self.ext < other.ext
        return self.text() < other.text()


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


class _DropButton(QPushButton):
    """Drop を受け入れるサブフォルダボタン。

    Inbox 起点の D&D を受け取った時のみアクセプトし、parent CasePane の
    `_on_inbox_drop(view_id, src_path)` を呼び出す。

    幅が狭く全文表示できない時は末尾省略 (…) を描画し、ツールチップで
    フル名を確認できるようにする。リサイズ時にも追従。
    """

    def __init__(self, view_id: int, label: str, pane: "CasePane") -> None:
        super().__init__(label, pane)
        self._view_id = view_id
        self._pane = pane
        self._full_label = label
        self.setToolTip(label)
        self.setAcceptDrops(True)

    def _set_drop_hover(self, on: bool) -> None:
        """drag が入ってきた時の強調色 (黄色) / 抜けたら戻す。
        QSS の :checked と競合しないよう setStyleSheet で動的に上書き。"""
        if on:
            self.setStyleSheet(
                "QPushButton#folderBtn { background-color: #FFFFC8; "
                "border: 2px solid #000080; padding: 0 2px; }"
            )
        else:
            self.setStyleSheet("")

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._apply_elide()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._apply_elide()

    def _apply_elide(self) -> None:
        avail = self.width() - 12   # 左右 padding + アイコン余裕
        if avail <= 0:
            return
        elided = self.fontMetrics().elidedText(
            self._full_label, Qt.TextElideMode.ElideRight, avail,
        )
        if elided != self.text():
            super().setText(elided)

    def dragEnterEvent(self, e) -> None:
        if kfile_source_of(e.mimeData()) == SRC_INBOX:
            self._set_drop_hover(True)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:
        if kfile_source_of(e.mimeData()) == SRC_INBOX:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e) -> None:
        self._set_drop_hover(False)
        super().dragLeaveEvent(e)

    def dropEvent(self, e) -> None:
        self._set_drop_hover(False)
        paths = kfile_local_paths(e.mimeData())
        if paths and kfile_source_of(e.mimeData()) == SRC_INBOX:
            self._pane._on_inbox_drop(self._view_id, paths)
            e.acceptProposedAction()
        else:
            e.ignore()


class _DropTabBar(QTabBar):
    """事件タブバー: 事件起点の D&D を受け取り、クロス事件 Move のトリガとする。"""

    def __init__(self, pane: "CasePane") -> None:
        super().__init__(pane)
        self._pane = pane
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e) -> None:
        if kfile_source_of(e.mimeData()) == SRC_CASE:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:
        if kfile_source_of(e.mimeData()) == SRC_CASE:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e) -> None:
        if kfile_source_of(e.mimeData()) != SRC_CASE:
            e.ignore()
            return
        target_idx = self.tabAt(e.position().toPoint())
        if target_idx < 0:
            e.ignore()
            return
        paths = kfile_local_paths(e.mimeData())
        if not paths:
            e.ignore()
            return
        # Ctrl 押下中の D&D = Copy (Win Explorer 標準)。Qt は startDrag 側で
        # Move|Copy を許可しているため、proposedAction で意図が読み取れる。
        is_copy = e.proposedAction() == Qt.DropAction.CopyAction
        if is_copy:
            self._pane._on_case_tab_drop_copy(target_idx, paths)
        else:
            self._pane._on_case_tab_drop(target_idx, paths)
        e.acceptProposedAction()


class _DragCaseTable(QTableWidget):
    """事件ファイル一覧: drag 起点 + folder 行への Inbox D&D drop 受け入れ。

    - 自テーブル → 別事件タブへの drag: クロス事件 Move (パスを MIME に載せる)
    - Inbox → 自テーブル内の folder 行への drop: そのフォルダへ inject 投入
      (孫フォルダ等、サブフォルダボタンに割当がない深い階層への投入手段)
    """

    tabPressed = Signal()   # Tab / Shift+Tab で Inbox テーブルにフォーカス移動

    def __init__(self, pane: "CasePane") -> None:
        super().__init__(0, 4, pane)
        self._pane = pane
        self.setDragEnabled(True)
        # DragDrop = drag 起点としても drop 受け入れ先としても機能する
        self.setDragDropMode(QTableWidget.DragDropMode.DragDrop)
        self.setAcceptDrops(True)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.tabPressed.emit()
            e.accept()
            return
        super().keyPressEvent(e)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if hasattr(self._pane, "_apply_responsive_columns"):
            self._pane._apply_responsive_columns()

    def startDrag(self, _actions) -> None:
        entries = self._pane.selected_entries()
        if not entries:
            return
        paths = [p for p, _is_dir in entries]
        drag = QDrag(self)
        drag.setMimeData(make_kfile_mime_data(SRC_CASE, paths))
        from PySide6.QtCore import QPoint
        drag.setPixmap(make_drag_pixmap([p.name for p in paths]))
        drag.setHotSpot(QPoint(-12, -12))
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction,
                  Qt.DropAction.MoveAction)

    # ── Inbox → テーブルへの drop = 現在表示中フォルダに投入 ─────
    # 「テーブルに投げたら、いま見えているフォルダに入る」の方が
    # フォルダ行への精密 drop より直感的。ネストの孫/曾孫もここに含まれる。
    def _set_drop_hover(self, on: bool) -> None:
        if on:
            self.setStyleSheet(
                "QTableWidget { background-color: #FFFFC8; "
                "border: 2px solid #000080; }"
            )
        else:
            self.setStyleSheet("")

    def dragEnterEvent(self, e) -> None:
        if kfile_source_of(e.mimeData()) == SRC_INBOX:
            self._set_drop_hover(True)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:
        if kfile_source_of(e.mimeData()) == SRC_INBOX:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e) -> None:
        self._set_drop_hover(False)
        super().dragLeaveEvent(e)

    def dropEvent(self, e) -> None:
        self._set_drop_hover(False)
        if kfile_source_of(e.mimeData()) != SRC_INBOX:
            e.ignore()
            return
        paths = kfile_local_paths(e.mimeData())
        if not paths:
            e.ignore()
            return
        target_dir = self._pane._cur_dir
        if target_dir is None:
            e.ignore()
            return
        self._pane.inboxDropToFolderRequested.emit(
            str(target_dir), [str(p) for p in paths]
        )
        e.acceptProposedAction()


class CasePane(QWidget):
    # 左クリック = 閲覧 (ファイルは動かさない)
    subfolderBrowsed = Signal(int, str)          # (view_id, view_name)
    # Alt+0〜9 / 右クリックメニュー = 投入要求 (実投入は M3)
    subfolderInjectRequested = Signal(int, str)  # (view_id, view_name)
    # Inbox からの D&D 投入要求 (Alt とは別シグナル — rename ダイアログは出さず即投入)
    inboxDropInjectRequested = Signal(int, str, list)  # (view_id, view_name, src_paths)
    # ファイル一覧内の任意フォルダ行への Inbox D&D 投入 (孫フォルダ等)
    inboxDropToFolderRequested = Signal(str, list)     # (target_dir, src_paths)
    # 事件タブへの D&D = クロス事件 Move 要求
    caseTabDropMoveRequested = Signal(int, list)       # (target_tab_idx, src_paths)
    # Ctrl+D&D = クロス事件 Copy 要求 (元ファイルは src 事件に残る)
    caseTabDropCopyRequested = Signal(int, list)       # (target_tab_idx, src_paths)
    # 右クリック「他事件へコピー / 移動 → サブフォルダ明示」(B 案)
    # (op: "copy"|"move", target_dir: str, src_paths: list[str])
    caseExplicitCrossCaseRequested = Signal(str, str, list)
    caseTabChanged = Signal(int, str, str)       # (idx, code, name)
    # サブフォルダ構成 (≒ Alt 割当) が変わった → 中央ストリップが再構築
    subfoldersChanged = Signal()
    # 削除要求 (Del キー / − ボタン)。MainWindow が file_ops.trash + 履歴記録を担当
    deleteRequested = Signal(str)                # 削除対象パス
    # 事件タブの追加/閉鎖で _case_paths が変わった → MainWindow が open_tabs を保存
    casePathsChanged = Signal()
    # 事件ショートカット (B フォルダの A symlink/.lnk) のダブルクリック →
    # MainWindow に target パスを渡して、当該事件タブに切替 (なければ新タブ追加)
    caseShortcutActivated = Signal(str)
    # ステータスバー通知 (サブフォルダ追加/ショートカット作成等)
    actionStatus = Signal(str)
    fileSelected = Signal(str)                   # 選択ファイルのパス (プレビュー用)
    # Ctrl+V / 右クリック「貼り付け」: 貼り付け先フォルダのパスを送る
    # (空文字 = 貼り付け先が特定できない)。実コピー/移動は MainWindow が担当。
    pasteRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("casePane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 右クリック投入メニューが Inbox の選択ファイルを問い合わせる getter
        self._inbox_file_getter = None
        # 「事件ショートカット?」判定用に ksystemz の doc_root を引く callback。
        # MainWindow が CaseRepo.doc_root を遅延評価する関数を注入する。
        self._doc_root_getter = None
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
        outer.addWidget(PaneHeader("参照ﾌｫﾙﾀﾞ"))

        # ── 事件タブ ── (cross-case D&D Move の drop ターゲットも兼ねる)
        self.case_tabs = _DropTabBar(self)
        self.case_tabs.setObjectName("caseTabBar")
        self.case_tabs.setDrawBase(False)
        self.case_tabs.setTabsClosable(True)
        self.case_tabs.setMovable(True)
        # ペイン全幅を占有 (デフォルトの Preferred だと sizeHint 止まり)
        self.case_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        # Qt 標準のタブ動作: タブは内容サイズ固定、溢れたら左右スクロールボタンで
        # アクセス。「タブを潰す」より「スクロールで切り替える」方が直感的。
        self.case_tabs.setExpanding(False)
        self.case_tabs.setUsesScrollButtons(True)
        # 単一タブ内で名前が長い場合のみ末尾省略 (今は case_code 表示なので影響少)
        self.case_tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.case_tabs.currentChanged.connect(self._on_case_tab_changed)
        self.case_tabs.tabCloseRequested.connect(self._on_case_tab_close)
        # 右クリックメニュー: 閉じる / 他を閉じる / 全部閉じる / Explorer で開く
        self.case_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.case_tabs.customContextMenuRequested.connect(self._show_case_tab_menu)
        outer.addWidget(self.case_tabs)

        # ── 事件フォルダパス兼パンくず + デスクトップショートカットボタン ──
        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(4)
        self.path_label = QLabel("(事件未選択)")
        self.path_label.setObjectName("casePath")
        self.path_label.setTextFormat(Qt.TextFormat.RichText)
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.path_label.linkActivated.connect(self._on_crumb_click)
        path_row.addWidget(self.path_label, stretch=1)
        # 「他事件へ」: アイコンのみ表示 (説明はホバーのツールチップに集約)。
        # ↗ は同事件フォルダ内に置かれた他事件ショートカットの表示マーカと共通。
        self.btn_to_case = QPushButton("↗")
        self.btn_to_case.setObjectName("caseToolBtn")
        self.btn_to_case.setToolTip(
            "他事件へショートカット作成\n"
            "現在の事件フォルダへのショートカットを\n"
            "別事件フォルダの root に置く\n"
            "(例: 夫婦事件で B 事件フォルダに A 事件のショートカットを置き、\n"
            " 文書は A に集約する運用)"
        )
        self.btn_to_case.clicked.connect(self._show_other_cases_menu)

        # ── ファイル名 絞込検索 (Win95 風: 虫眼鏡アイコン + 折り畳み式 LineEdit) ──
        # 通常は虫眼鏡だけ表示、Ctrl+F or 虫眼鏡クリックで input 欄が現れる。
        # AND 検索 (空白区切り) で「うけと 田中」のような複数語マッチに対応。
        self._filter_query = ""
        self.filter_edit = QLineEdit()
        self.filter_edit.setObjectName("caseFilterEdit")
        self.filter_edit.setPlaceholderText("絞込検索")
        self.filter_edit.setMaximumWidth(180)
        self.filter_edit.setVisible(False)
        self.filter_edit.textChanged.connect(self._on_filter_text_changed)
        sc_filter_esc = QShortcut(
            QKeySequence(Qt.Key.Key_Escape), self.filter_edit
        )
        sc_filter_esc.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc_filter_esc.activated.connect(self._on_filter_escape)
        self.filter_count_label = QLabel("")
        self.filter_count_label.setObjectName("caseFilterCount")
        self.filter_count_label.setVisible(False)
        self.btn_filter = QPushButton("🔍")
        self.btn_filter.setObjectName("caseToolBtn")
        self.btn_filter.setCheckable(True)
        self.btn_filter.setToolTip(
            "ファイル名で絞込検索 (Ctrl+F)\n"
            "空白区切りで AND 検索 (例: 受領 田中)\n"
            "Esc で解除"
        )
        self.btn_filter.clicked.connect(self._on_filter_btn_clicked)
        path_row.addWidget(self.filter_edit)
        path_row.addWidget(self.filter_count_label)
        path_row.addWidget(self.btn_filter)
        path_row.addWidget(self.btn_to_case)
        outer.addLayout(path_row)

        # Ctrl+F: 検索入力欄をひらいてフォーカス
        sc_ctrl_f = QShortcut(QKeySequence("Ctrl+F"), self)
        sc_ctrl_f.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_ctrl_f.activated.connect(self._open_filter)

        # ── 下段: 左=サブフォルダボタン / 右=ファイル一覧 ──
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(2)

        # サブフォルダボタン列 (上: 動的な閲覧ボタン群 / 下: +/- 管理ボタン)
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.button_group.idClicked.connect(self._on_folder_browse)
        btn_container = QWidget()
        container_lay = QVBoxLayout(btn_container)
        container_lay.setContentsMargins(0, 0, 0, 0)
        container_lay.setSpacing(0)
        # 上: 動的サブフォルダ閲覧ボタン (_rebuild_subfolder_buttons で構築)
        self.btn_col = QVBoxLayout()
        # 上端 (1 ボタンとパスバーの間) もボタン間と同じ 2px
        self.btn_col.setContentsMargins(0, 2, 0, 0)
        # ボタン間に 2px のすき間 (中央ストリップの >1 >2 と同じ間隔)
        self.btn_col.setSpacing(2)
        container_lay.addLayout(self.btn_col, stretch=1)
        # 下: 区切り + 管理ボタン (+追加 / -削除)。固定で永続。
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedHeight(4)
        container_lay.addWidget(sep)
        self.btn_add_subf = QPushButton("+ 追加")
        self.btn_add_subf.setObjectName("caseToolBtn")
        self.btn_add_subf.setToolTip("新規サブフォルダを作成 (例: 7_メモ)")
        self.btn_add_subf.clicked.connect(self._on_add_subfolder)
        container_lay.addWidget(self.btn_add_subf)
        self.btn_del_subf = QPushButton("− 削除")
        self.btn_del_subf.setObjectName("caseToolBtn")
        self.btn_del_subf.setToolTip(
            "現在表示中のサブフォルダを削除 (OS のごみ箱へ。事件フォルダ直下は削除不可)"
        )
        self.btn_del_subf.clicked.connect(self._on_delete_subfolder)
        container_lay.addWidget(self.btn_del_subf)
        # 固定幅 140 にして「Inbox 幅 ≒ 中央ファイル一覧幅」の動的計算が
        # 実際のオーバーヘッド (_CASE_LEFT_OFFSET=148) と一致するようにする。
        # max-width だと内容次第で実幅が変動し、Name 列幅が両ペインで不揃いになる。
        btn_container.setFixedWidth(140)
        mid.addWidget(btn_container)

        # 右カラム: ファイル一覧テーブル (子フォルダも行として表示)
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)
        # _DragCaseTable: 行を別事件タブへ D&D できる (cross-case Move 起点)
        self.table = _DragCaseTable(self)
        # サイズ列ヘッダーは KB/MB 切替に追従 (`ｻｲｽﾞ (KB)` ↔ `ｻｲｽﾞ (MB)`)。
        self.table.setHorizontalHeaderLabels(
            ["Name", "拡張子", "更新", "ｻｲｽﾞ (KB)"]
        )
        self.table.setIconSize(QSize(13, 13))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(18)
        self.table.verticalHeader().setMinimumSectionSize(18)
        self.table.horizontalHeader().setFixedHeight(17)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 複数選択可能 (Shift で範囲 / Ctrl で個別 toggle)。削除 / D&D は
        # 全選択行に対して順次実行される (rename = F2 のみ単一行限定)。
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        # 縦スクロールバーを常時表示 (InboxPane と viewport 幅を揃え、Name 列幅を
        # 両ペインで一致させるため。AsNeeded だと片方だけ 12px 狭くなる)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(1, 60)    # 拡張子 (.PDF / .JPEG)
        # 更新 (YY-MM-DD HH:MM、14 文字)。初期表示で省略されない幅 (Inbox と同寸)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 90)    # サイズ
        self.table.cellDoubleClicked.connect(self._on_table_double_click)
        # Enter / Return: 選択行をダブルクリック相当で活性化
        # (ファイル → 既定アプリ / フォルダ → descend / .. → 上へ)
        sc_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self.table)
        sc_enter.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_enter.activated.connect(self._activate_current_row)
        sc_enter_kp = QShortcut(QKeySequence(Qt.Key.Key_Enter), self.table)
        sc_enter_kp.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_enter_kp.activated.connect(self._activate_current_row)
        # Ctrl+C / Ctrl+X / Ctrl+V: Explorer 流のファイル コピー / 切り取り / 貼り付け
        sc_copy = QShortcut(QKeySequence.StandardKey.Copy, self.table)
        sc_copy.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_copy.activated.connect(lambda: self.copy_selected(cut=False))
        sc_cut = QShortcut(QKeySequence.StandardKey.Cut, self.table)
        sc_cut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_cut.activated.connect(lambda: self.copy_selected(cut=True))
        sc_paste = QShortcut(QKeySequence.StandardKey.Paste, self.table)
        sc_paste.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc_paste.activated.connect(self._request_paste)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        # ヘッダー右クリック (サイズ列のみ) → KB/MB 切替メニュー
        # 左クリックはソートに専念させる (役割が違うので分離 — ユーザー要望)
        hdr = self.table.horizontalHeader()
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._show_header_menu)
        # 行右クリック → 「既定アプリで開く」「Explorer で開く」「フルパスをコピー」
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_row_menu)
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
        """起動時はタブを空で開始する (M5: 自動 load 撤去 — ADR-15)。

        事件タブは外部 (MainWindow) から `add_case_tab()` で構築される:
          - セッション復元 (前回 open_tabs の事件を順次 add)
          - Ctrl+O「事件を開く」ダイアログから選択
          - フォルダ D&D でメインウインドウに drop
        初期状態は空 (path_label = 「事件未選択」のまま) で、ユーザーが意識的に
        開く方が業務フロー (どの事件を扱うかを最初に決める) と整合する。
        """
        # 何もしない (パス表示は __init__ で「事件未選択」のまま)
        return

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
            # タブ切替時に絞込検索を解除 (別事件で前の検索語が残ると混乱)
            self._reset_filter()
            self._load_case(idx)
            self.caseTabChanged.emit(idx, self._case_code, self._case_name)

    def _show_case_tab_menu(self, pos) -> None:
        """事件タブの右クリックメニュー。"""
        idx = self.case_tabs.tabAt(pos)
        if idx < 0:
            return
        if not 0 <= idx < len(self._case_paths):
            return
        path = self._case_paths[idx]
        menu = QMenu(self)
        act_close = menu.addAction("このタブを閉じる")
        act_close.triggered.connect(lambda: self._on_case_tab_close(idx))
        if len(self._case_paths) > 1:
            act_other = menu.addAction("他のタブを閉じる")
            act_other.triggered.connect(lambda: self._close_other_tabs(idx))
            act_all = menu.addAction("すべてのタブを閉じる")
            act_all.triggered.connect(self._close_all_tabs)
        menu.addSeparator()
        act_reveal = menu.addAction("Explorer で開く")
        act_reveal.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        )
        act_copy = menu.addAction("フルパスをコピー")
        act_copy.triggered.connect(
            lambda: self._copy_to_clipboard(str(path))
        )
        menu.exec(self.case_tabs.mapToGlobal(pos))

    def _close_other_tabs(self, keep_idx: int) -> None:
        """keep_idx 以外のタブを全て閉じる (末尾から削除して index ズレ回避)。"""
        keep_path = self._case_paths[keep_idx]
        for i in reversed(range(len(self._case_paths))):
            if self._case_paths[i] != keep_path:
                self._on_case_tab_close(i)

    def _close_all_tabs(self) -> None:
        for i in reversed(range(len(self._case_paths))):
            self._on_case_tab_close(i)

    def _on_case_tab_close(self, idx: int) -> None:
        if 0 <= idx < len(self._case_paths):
            self._case_paths.pop(idx)
        self.case_tabs.removeTab(idx)
        # 全タブを閉じた場合の表示クリア (中身が前事件のまま残るのを防ぐ)
        if not self._case_paths:
            self._scan = None
            self._case_code = ""
            self._case_name = ""
            self.path_label.setText("(事件未選択)")
            # サブフォルダボタン群 + ファイル一覧を空に
            while self.btn_col.count():
                item = self.btn_col.takeAt(0)
                w = item.widget()
                if w is not None:
                    self.button_group.removeButton(w)
                    w.deleteLater()
            self._view_btns = {}
            self.table.setRowCount(0)
            self.subfoldersChanged.emit()
        self.casePathsChanged.emit()

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

        # 新規ボタンに MS Gothic ビットマップ戦略を再適用 (QSS の font-family
        # が新 widget で strategy をリセットするため、ADR-17 と同方式で
        # widget tree を walk して strategy 再付与)
        apply_bitmap_font_strategy(self)

        # 中央ストリップに最新のサブフォルダ構成を反映してもらう
        self.subfoldersChanged.emit()

    def _make_view_button(self, view_id: int, label: str) -> QPushButton:
        # _DropButton: Inbox からの D&D を受けて投入要求を発火する
        btn = _DropButton(view_id, label, self)
        btn.setObjectName("folderBtn")
        btn.setCheckable(True)
        # 右クリック = 投入メニュー (左クリックは閲覧のみ)
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, vid=view_id, b=btn: self._show_folder_menu(vid, b, pos)
        )
        self.button_group.addButton(btn, view_id)
        return btn

    # ───────── D&D 受信ハンドラ (_DropButton / _DropTabBar から呼ばれる) ─────────

    def _on_inbox_drop(self, view_id: int, src_paths: list[Path]) -> None:
        """サブフォルダボタンに Inbox ファイル群が drop された。"""
        self.inboxDropInjectRequested.emit(
            view_id, self._view_name(view_id),
            [str(p) for p in src_paths],
        )
        # 投入先の中身を表示 (Alt 投入と同じ挙動)
        self._browse(view_id)

    def _on_case_tab_drop(
        self, target_idx: int, src_paths: list[Path]
    ) -> None:
        """事件タブに 事件ファイル群が drop された (= クロス事件 Move)。"""
        self.caseTabDropMoveRequested.emit(
            target_idx, [str(p) for p in src_paths]
        )

    def _on_case_tab_drop_copy(
        self, target_idx: int, src_paths: list[Path]
    ) -> None:
        """事件タブに Ctrl+D&D された (= クロス事件 Copy)。Move とは別動線。"""
        self.caseTabDropCopyRequested.emit(
            target_idx, [str(p) for p in src_paths]
        )

    # ───────── ビュー / ネストナビゲーション ─────────

    def _browse(self, view_id: int) -> None:
        """左ボタン: 上位ビュー (サブフォルダ / 直下) へ移動。閲覧のみ。"""
        if self._scan is None:
            return
        btn = self._view_btns.get(view_id)
        if btn is None:
            return
        # サブフォルダ切替時に絞込検索を解除 (別フォルダで前の検索語が残ると混乱)
        if self._cur_view_id != view_id:
            self._reset_filter()
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
        # 「事件フォルダ直下」ビューは サブフォルダ (1_文書 等) を出さない
        # (左ボタン列で管理)。ただし **事件ショートカット (symlink/.lnk)** は
        # 別事件への入口として直下に置かれているので、is_link なら表示する。
        if self._cur_view_id == ROOT_VIEW_ID:
            entries = [
                e for e in list_folder(self._cur_dir)
                if not e.is_dir or e.is_link
            ]
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

    def _activate_current_row(self) -> None:
        """Enter キー: 現在行をダブルクリック相当で活性化。"""
        row = self.table.currentRow()
        if row >= 0:
            self._on_table_double_click(row, 0)

    def _on_table_double_click(self, row: int, _col: int) -> None:
        """ファイル一覧の行をダブルクリック:
          - `..` 行: 一階層上へ
          - ショートカット: 事件タブ切替 (or 通常 descend)
          - フォルダ: descend
          - ファイル: OS 既定アプリで開く"""
        item = self.table.item(row, 0)
        if not isinstance(item, _NameItem):
            return
        if item.is_parent:
            self._go_up()
            return
        if item.is_link:
            if self._try_activate_case_shortcut(item.path):
                return
        if item.is_dir:
            self._cur_dir = item.path
            self._crumb.append((item.text(), item.path))
            self._show_current()
        else:
            # ファイル → OS 既定アプリ起動 (Windows = Explorer の関連付け、
            # Linux = xdg-open、Mac = LaunchServices)。プレビューと併用。
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.path)))

    def _try_activate_case_shortcut(self, path: Path) -> bool:
        """symlink/.lnk のターゲットが ksystemz doc_root 直下の事件フォルダなら
        caseShortcutActivated を発火して True。それ以外は False (descend に戻す)。
        """
        target = resolve_shortcut(path)
        if target is None:
            return False
        if self._doc_root_getter is None:
            return False
        try:
            doc_root = self._doc_root_getter()
        except OSError:
            return False
        if doc_root is None:
            return False
        try:
            target_resolved = target.resolve()
            root_resolved = Path(doc_root).resolve()
        except OSError:
            return False
        if target_resolved.parent != root_resolved:
            return False    # doc_root 直下の事件フォルダではない
        if not target_resolved.is_dir():
            return False
        self.caseShortcutActivated.emit(str(target_resolved))
        return True

    def _on_table_selection(self) -> None:
        """行選択が変わったら、ファイルならパスを通知 (フォルダ・未選択は "")。
        clearSelection 後は currentRow が古い値のまま残るので、選択が空の
        場合は currentRow を見ずに必ず空文字を emit する (Inbox→事件移動後
        eventFilter で inbox 側の選択を消した直後にプレビューが古い path に
        戻る事故を防ぐ、2026-05-26)。"""
        sel_model = self.table.selectionModel()
        if sel_model is None or not sel_model.selectedRows():
            self.fileSelected.emit("")
            return
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
        """パスバーを「R060... 鈴木花子 離婚 › サブ › サブサブ」のパンくず表示に。"""
        text = f"{self._case_code}  {self._case_name}"
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
        # rebuild 前に選択中の path を保存しておき、rebuild 完了後に同 path
        # 行を再選択する (rename/refresh 後に選択が別ファイルにずれる現象を
        # 防ぐ、2026-05-26)。
        prev_paths = self._collect_selected_paths()
        # 選択していたファイルが消えた (削除・移動) ケースで「同じ行 index の
        # 隣接ファイル」へフォールバックするため、rebuild 直前の currentRow も
        # 控える。
        prev_current_row = self.table.currentRow()
        self.table.setSortingEnabled(False)
        has_parent = parent_path is not None
        self.table.setRowCount(len(entries) + (1 if has_parent else 0))

        row = 0
        if has_parent:
            parent_item = _NameItem("..", True, parent_path, is_parent=True)
            self.table.setItem(row, 0, parent_item)
            self.table.setItem(row, 1, _ExtItem("", True, is_parent=True))
            empty_date = QTableWidgetItem("")
            empty_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, empty_date)
            size_cell = QTableWidgetItem("<DIR>")
            size_cell.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 3, size_cell)
            self.table.setRowHeight(row, 18)
            row += 1

        for e in entries:
            # 拡張子は別列に分離。フォルダ・ショートカット行は空。
            # ファイルは stem を Name に、拡張子を大文字で EXT 列に出す。
            # 拡張子はドット付き大文字 (例: .PDF .JPG)。フォルダ・ショートカット
            # 行は空文字。Path.suffix は既に "." を含むため upper() のみで OK。
            ext_upper = ""
            if not e.is_dir and not e.is_link:
                ext_upper = e.path.suffix.upper()
            if e.is_dir or e.is_link:
                stem_display = e.name
            else:
                stem_display = e.path.stem
            # ショートカット行は ↗ プレフィックス + .lnk 拡張子を表示から省く
            if e.is_link and stem_display.lower().endswith(".lnk"):
                stem_display = stem_display[:-4]
            if e.is_link:
                stem_display = "↗ " + stem_display
            name_item = _NameItem(
                stem_display, e.is_dir, e.path,
                is_link=e.is_link, ext=ext_upper,
            )
            # 長いファイル名はセル幅で省略表示されるので、ホバーでフル名を表示
            # (本番テスト要望 2026-05-25)。フォルダ/ショートカット行はフォルダ名のみ。
            if e.is_dir or e.is_link:
                name_item.setToolTip(e.name)
            else:
                name_item.setToolTip(e.path.name)
            # アイコンは表示しない (DOS ファイラー風、サイズ列の <DIR> でフォルダ判別)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(
                row, 1, _ExtItem(ext_upper, e.is_dir)
            )

            # Inbox と表示書式を揃える: `26-05-25 15:30` (西暦下 2 桁 + 時分)
            # 2026-05-25 ユーザー要望 (両ペインで時刻まで見えると業務上便利)。
            date = datetime.fromtimestamp(e.mtime).strftime("%y-%m-%d %H:%M")
            item_date = QTableWidgetItem(date)
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_date)

            if e.is_dir:
                item_size = QTableWidgetItem("<DIR>")
                item_size.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row, 3, item_size)
            else:
                self.table.setItem(row, 3, _SizeItem(e.size, self._size_unit))
            self.table.setRowHeight(row, 18)
            row += 1

        # 現在の sortIndicator を尊重して再ソート (KB/MB 切替等で勝手に
        # 既定列に戻さない)。初回 populate 時のみ既定 (Name 昇順) を採用。
        self.table.setSortingEnabled(True)
        if not getattr(self, "_sort_initialized", False):
            self.table.sortItems(0, Qt.SortOrder.AscendingOrder)
            self._sort_initialized = True
        # ソート後の最終行配置で、保存した path 群を再選択。restore に失敗した
        # (= 選択中のファイルが全部消えた) 場合は同じ row index の隣接行を選び、
        # プレビューが「直前まで見ていた近傍」を表示し続けるようにする
        # (Inbox→事件移動などペイン跨ぎの focus 制御は呼び出し側で別途行う)。
        if prev_paths:
            restored = self._restore_selection_by_paths(prev_paths)
            if not restored:
                self._select_adjacent_row(prev_current_row)
        # 絞込検索 (Ctrl+F) が有効ならフィルタを再適用 (refresh 後にヒット行が
        # 変わる可能性のため)。空クエリなら全行表示の no-op。
        self._apply_filter()

    def _collect_selected_paths(self) -> set[str]:
        """現在の選択行の Path を文字列集合で取得。`..` 行は除外。
        _NameItem.path が事実上のキー。"""
        out: set[str] = set()
        sel_model = self.table.selectionModel()
        if sel_model is None:
            return out
        for ix in sel_model.selectedRows():
            it = self.table.item(ix.row(), 0)
            if isinstance(it, _NameItem) and not it.is_parent:
                out.add(str(it.path))
        return out

    def _restore_selection_by_paths(self, paths: set[str]) -> bool:
        """rebuild 後のテーブルから path が一致する行を再選択する。
        multi-select 対応。currentIndex を先に動かしてから select を発火する
        ことで、itemSelectionChanged 経由のプレビュー連動が新しい currentRow
        を見るように順序を保証する (選択 vs プレビュー食い違い対策、2026-05-26)。

        Returns: 1 行以上選択できたか。呼び出し側が「全部消えた」検出に使う。"""
        if not paths:
            return False
        rows: list[int] = []
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if isinstance(it, _NameItem) and not it.is_parent:
                if str(it.path) in paths:
                    rows.append(row)
        sel_model = self.table.selectionModel()
        model = self.table.model()
        if sel_model is None or model is None:
            return False
        if not rows:
            # 旧選択の row index に「selected」フラグが残っているとそこが
            # 別ファイルなのに濃紺で出てしまう。一旦クリアして呼び出し側に
            # フォールバック判断を委ねる。
            sel_model.clearSelection()
            return False
        # 先に currentIndex を更新 (selectionChanged は発火させない)
        sel_model.setCurrentIndex(
            model.index(rows[0], 0),
            QItemSelectionModel.SelectionFlag.NoUpdate,
        )
        # 次に selection を一括適用 → itemSelectionChanged は最終 currentRow で発火
        selection = QItemSelection()
        last_col = self.table.columnCount() - 1
        for row in rows:
            tl = model.index(row, 0)
            br = model.index(row, last_col)
            selection.select(tl, br)
        sel_model.select(
            selection,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        return True

    def _select_adjacent_row(self, hint_row: int) -> None:
        """選択ファイルが全部消えた時のフォールバック: hint_row と同じ index
        (テーブル末尾を超えたら末尾) の行を選択する。`..` 行は飛ばす。
        Inbox→事件移動など「移動先を別ペインで focus する」場合はここを通る前に
        呼び出し側で focus 制御するため、ここはあくまで「同ペイン内の隣接行」用。"""
        n = self.table.rowCount()
        if n == 0:
            return
        target = min(max(hint_row, 0), n - 1)
        it = self.table.item(target, 0)
        if isinstance(it, _NameItem) and it.is_parent:
            # `..` 行を飛ばして次の行へ
            if target + 1 < n:
                target += 1
                it = self.table.item(target, 0)
            else:
                return
        if isinstance(it, _NameItem):
            self._restore_selection_by_paths({str(it.path)})

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
            self.table.setHorizontalHeaderLabels(
                ["Name", "拡張子", "更新", f"ｻｲｽﾞ ({new_unit})"]
            )
            self._show_current()

    def _show_row_menu(self, pos) -> None:
        """ファイル一覧 行の右クリックメニュー。
        対象が `..` 行や未選択なら出さない。フォルダ行は「Explorer で開く」のみ。
        末尾に「他事件へコピー/移動」サブメニュー (B 案)。"""
        row = self.table.indexAt(pos).row()
        item = self.table.item(row, 0) if row >= 0 else None
        if not isinstance(item, _NameItem) or item.is_parent:
            # `..` 行 / 余白の右クリック: 貼り付けのみ (表示中フォルダへ)
            menu = QMenu(self)
            self._add_paste_action(menu)
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return
        menu = QMenu(self)
        if item.is_dir:
            act_open = menu.addAction("フォルダを開く (Explorer)")
            act_open.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.path)))
            )
        else:
            act_open = menu.addAction("既定アプリで開く")
            act_open.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.path)))
            )
            act_reveal = menu.addAction("フォルダを開く (Explorer)")
            act_reveal.triggered.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(item.path.parent))
                )
            )
        menu.addSeparator()
        act_fcopy = menu.addAction("コピー")
        act_fcopy.triggered.connect(lambda: self.copy_selected(cut=False))
        act_fcut = menu.addAction("切り取り")
        act_fcut.triggered.connect(lambda: self.copy_selected(cut=True))
        self._add_paste_action(menu)
        act_pathcopy = menu.addAction("フルパスをコピー")
        act_pathcopy.triggered.connect(
            lambda: self._copy_to_clipboard(str(item.path))
        )

        # 「他事件へコピー / 移動」(B 案): multi-select 対応で全選択行を target に
        sel_paths = [p for p, _ in self.selected_entries()]
        if not sel_paths:
            sel_paths = [item.path]
        self._add_cross_case_submenus(menu, sel_paths)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _add_paste_action(self, menu: QMenu) -> None:
        """「貼り付け」項目を menu に足す。クリップボードにファイルが無ければ
        無効表示にして発見性だけ残す。"""
        act_paste = menu.addAction("貼り付け")
        act_paste.setEnabled(
            clipboard_ops.clipboard_has_files() and self._cur_dir is not None
        )
        act_paste.triggered.connect(self._request_paste)

    def _add_cross_case_submenus(
        self, parent_menu: QMenu, src_paths: list[Path]
    ) -> None:
        """「他事件へコピー / 移動」の 2 つのサブメニューを末尾に追加する。

        各サブメニューは: 他の開いている事件タブ一覧 → そのサブフォルダ一覧
        (+「事件フォルダ直下」)。発火時は `caseExplicitCrossCaseRequested`
        シグナルで (op, target_dir, src_paths) を送る。
        他事件タブが 0 件なら両サブメニューを disable 表示で残す (発見性のため)。
        """
        parent_menu.addSeparator()
        current = self.current_case_path()
        other_cases = [p for p in self._case_paths if p != current]

        copy_menu = parent_menu.addMenu("他事件へコピー…")
        move_menu = parent_menu.addMenu("他事件へ移動…")
        if not other_cases:
            copy_menu.setEnabled(False)
            move_menu.setEnabled(False)
            return

        for case_root in other_cases:
            code, name = _parse_case(case_root)
            tab_label = f"{code}  {name}" if name else code
            self._build_case_submenu(copy_menu, "copy", case_root, tab_label, src_paths)
            self._build_case_submenu(move_menu, "move", case_root, tab_label, src_paths)

    def _build_case_submenu(
        self,
        parent_menu: QMenu,
        op: str,
        case_root: Path,
        tab_label: str,
        src_paths: list[Path],
    ) -> None:
        """1 事件タブ分のサブメニュー: 事件直下 + サブフォルダ一覧。"""
        case_submenu = parent_menu.addMenu(tab_label)
        # 事件フォルダ直下
        act_root = case_submenu.addAction("0  事件フォルダ直下")
        act_root.triggered.connect(
            lambda checked=False, td=case_root: self._emit_explicit(op, td, src_paths)
        )
        # サブフォルダ (現在の動的構成)
        try:
            scan = scan_case_folder(case_root)
        except OSError:
            return
        for sf in scan.subfolders:
            label = sf.name
            if sf.alt_key:
                label = f"{sf.alt_key}  {sf.name}"
            act = case_submenu.addAction(label)
            act.triggered.connect(
                lambda checked=False, td=sf.path: self._emit_explicit(op, td, src_paths)
            )

    def _emit_explicit(
        self, op: str, target_dir: Path, src_paths: list[Path]
    ) -> None:
        """メニュー項目クリック時のシグナル発火。"""
        self.caseExplicitCrossCaseRequested.emit(
            op, str(target_dir), [str(p) for p in src_paths]
        )

    def _copy_to_clipboard(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(text)

    def current_dir(self) -> Path | None:
        """いま中央テーブルに表示中のフォルダ (貼り付け先)。事件未選択なら None。"""
        return self._cur_dir

    def copy_selected(self, cut: bool) -> None:
        """Ctrl+C / Ctrl+X / 右クリック: 選択行をクリップボードに載せる
        (Explorer 互換)。cut=True で切り取り (貼り付けで移動)。`..` 行は除外。"""
        paths = [p for p, _ in self.selected_entries()]
        if not paths:
            self.actionStatus.emit("コピーするファイルが選択されていません")
            return
        clipboard_ops.set_file_clipboard(paths, cut=cut)
        verb = "切り取り" if cut else "コピー"
        if len(paths) == 1:
            self.actionStatus.emit(f"{paths[0].name} を{verb}")
        else:
            self.actionStatus.emit(f"{len(paths)} ファイルを{verb}")

    def _request_paste(self) -> None:
        """Ctrl+V / 右クリック「貼り付け」: 表示中フォルダを宛先に MainWindow へ。"""
        target = self.current_dir()
        self.pasteRequested.emit(str(target) if target is not None else "")

    # ───────── サブフォルダ管理 / 事件フォルダ管理 (+ / − / デスクトップ) ─────────

    def _on_add_subfolder(self) -> None:
        """+ ボタン: 新規サブフォルダ作成。"""
        if self._scan is None:
            self.actionStatus.emit("事件が未選択です")
            return
        name, ok = QInputDialog.getText(
            self,
            "サブフォルダを追加",
            "新しいサブフォルダ名を入力してください\n"
            "(例: 7_メモ、案件メモ、判例集 など)",
            QLineEdit.EchoMode.Normal,
        )
        if not ok:
            return
        name = name.strip()
        err = file_ops.validate_name(name) if name else "ファイル名が空です"
        if err is not None:
            QMessageBox.warning(self, "サブフォルダを追加", err)
            return
        new_dir = self._scan.root_path / name
        if new_dir.exists():
            QMessageBox.warning(
                self, "サブフォルダを追加",
                f"同名のフォルダが既に存在します:\n{name}",
            )
            return
        try:
            new_dir.mkdir()
        except OSError as e:
            QMessageBox.critical(
                self, "サブフォルダを追加", f"作成に失敗しました:\n{e}"
            )
            return
        self.refresh_current_view()
        self.actionStatus.emit(f"サブフォルダを作成: {name}")

    def _on_delete_subfolder(self) -> None:
        """− ボタン: 現在表示中のサブフォルダを OS ごみ箱へ送る要求。

        「事件フォルダ直下」ビューでは削除しない (事件本体が消えるのを防ぐ)。
        実削除と履歴記録は MainWindow (deleteRequested) に委譲。
        """
        if self._scan is None or self._cur_view_id == ROOT_VIEW_ID:
            self.actionStatus.emit(
                "削除できるサブフォルダが選択されていません (直下は削除不可)"
            )
            return
        if not (0 <= self._cur_view_id < len(self._scan.subfolders)):
            return
        sf = self._scan.subfolders[self._cur_view_id]
        # 削除済ビューに留まらないよう先に root へ
        self._cur_view_id = ROOT_VIEW_ID
        self.deleteRequested.emit(str(sf.path))

    def delete_selected_row(self) -> None:
        """Del キー: 中央テーブルの選択行を削除要求 (multi-select 対応)。

        ファイル / ネストフォルダ どちらでも可。`..` 行と未選択は無視。
        """
        entries = self.selected_entries()
        if not entries:
            self.actionStatus.emit("削除する行が選択されていません")
            return
        for path, _is_dir in entries:
            self.deleteRequested.emit(str(path))

    def _show_other_cases_menu(self) -> None:
        """「他事件へ」ボタン: 開いている他の事件タブをメニュー表示。"""
        if self._scan is None:
            self.actionStatus.emit("事件が未選択です")
            return
        current_idx = self.case_tabs.currentIndex()
        others = [
            (i, self._case_paths[i])
            for i in range(len(self._case_paths))
            if i != current_idx
        ]
        menu = QMenu(self)
        if not others:
            act = menu.addAction("他に開いている事件タブがありません")
            act.setEnabled(False)
        else:
            for _i, path in others:
                code, name = _parse_case(path)
                label = f"→ {code}  {name}"
                act = menu.addAction(label)
                act.triggered.connect(
                    lambda _=False, p=path: self._place_shortcut_in_case(p)
                )
        menu.exec(self.btn_to_case.mapToGlobal(
            self.btn_to_case.rect().bottomLeft()
        ))

    def _place_shortcut_in_case(self, target_case_root: Path) -> None:
        """現在の事件フォルダのショートカットを target_case_root に置く。"""
        if self._scan is None:
            return
        src_root = self._scan.root_path
        try:
            link = create_folder_shortcut(src_root, target_case_root)
        except OSError as e:
            QMessageBox.critical(
                self, "他事件にショートカット作成",
                f"作成に失敗しました:\n{e}",
            )
            return
        target_code, _ = _parse_case(target_case_root)
        self.actionStatus.emit(
            f"{target_code} の root にショートカット作成: {link.name}"
        )

    def trigger_subfolder_action(self, view_id: int, *, has_inbox: bool) -> None:
        """中央ストリップ数字ボタン共用エントリ。

        - has_inbox=True (Inbox に選択あり): 投入要求 + 投入先を開く
        - has_inbox=False: 閲覧のみ (左クリックと同じ)
        """
        if view_id not in self._view_btns:
            return
        if has_inbox:
            self._on_subfolder_inject(view_id)
        else:
            self._on_folder_browse(view_id)

    def subfolder_button_targets(self) -> list[tuple[str, int]]:
        """中央ストリップに並べる数字ボタン構成 (label, view_id) を返す。

        ラベルは ">1" 等 — `>` で「Inbox から右のサブフォルダへ移動」を視覚化。
        実フォルダの動的スキャンに連動 (例: 1_文書〜6_訟務 + 直下=0 → 7 個)。
        Alt 割当のないサブフォルダ (10 個目以降) は数字ボタンも作らない。
        """
        out: list[tuple[str, int]] = []
        if self._scan is None:
            return out
        for i, sf in enumerate(self._scan.subfolders):
            if sf.alt_key is not None:
                out.append((f">{sf.alt_key}", i))
        out.append((">0", ROOT_VIEW_ID))
        return out

    def view_target_dir(self, view_id: int) -> Path | None:
        """view_id (サブフォルダ index または ROOT_VIEW_ID) → 投入先ディレクトリ。"""
        if self._scan is None:
            return None
        if view_id == ROOT_VIEW_ID:
            return self._scan.root_path
        if 0 <= view_id < len(self._scan.subfolders):
            return self._scan.subfolders[view_id].path
        return None

    def current_view_id(self) -> int:
        """現在閲覧中のビュー ID。投入先 (実際にユーザーが見ているフォルダ)。"""
        return self._cur_view_id

    def current_case_path(self) -> Path | None:
        """現在開いている事件フォルダのルート (cross-case D&D 等の判定用)。"""
        return self._scan.root_path if self._scan is not None else None

    def add_case_tab(self, path: Path) -> int:
        """事件フォルダを新規タブとして開く (既に開いていればそれに切替)。

        Ctrl+O「事件を開く」やフォルダ D&D 経由で呼ばれる。重複時は新タブを
        作らずに既存タブをアクティブにする。casePathsChanged を発火。
        """
        path = Path(path)
        for i, existing in enumerate(self._case_paths):
            if existing == path:
                if self.case_tabs.currentIndex() != i:
                    self.case_tabs.setCurrentIndex(i)
                return i
        # 新規追加。タブラベルは依頼者名+案件名 (case_code は短いがコード番号
        # だけだと事件が識別しにくい)。長くて溢れる場合はスクロールボタンで
        # アクセスする。フル名はツールチップで確認可。
        self._case_paths.append(path)
        code, name = _parse_case(path)
        new_idx = self.case_tabs.addTab(_tab_label(code, name))
        self.case_tabs.setTabToolTip(new_idx, f"{code}  {name}")
        # 初回の addTab は currentChanged を発火するので _load_case 自動呼出し。
        # 2 件目以降は自動選択されないので明示的に setCurrentIndex で発火させる。
        if self.case_tabs.currentIndex() != new_idx:
            self.case_tabs.setCurrentIndex(new_idx)
        self.casePathsChanged.emit()
        return new_idx

    def case_paths(self) -> list[Path]:
        """開いている事件タブのパス一覧 (左端から順)。セッション保存用。"""
        return list(self._case_paths)

    def selected_entry(self) -> tuple[Path, bool] | None:
        """中央テーブルで選択中の (ファイル|フォルダ) の (path, is_dir)。

        `..` 行や未選択時は None。F2 等の単一行ハンドラから使う。
        """
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not isinstance(item, _NameItem) or item.is_parent:
            return None
        return item.path, item.is_dir

    def selected_entries(self) -> list[tuple[Path, bool]]:
        """multi-select 全行の (path, is_dir) リスト。`..` 行は除外。
        cross-case D&D / Del / 等の複数行操作で使う。"""
        rows = [
            ix.row() for ix in self.table.selectionModel().selectedRows()
        ]
        out: list[tuple[Path, bool]] = []
        for r in sorted(set(rows)):
            item = self.table.item(r, 0)
            if isinstance(item, _NameItem) and not item.is_parent:
                out.append((item.path, item.is_dir))
        return out

    # ───────── ファイル名 絞込検索 (Ctrl+F) ─────────

    def _open_filter(self) -> None:
        """Ctrl+F or 虫眼鏡クリック: 検索入力欄を表示してフォーカス。"""
        self.btn_filter.setChecked(True)
        self.filter_edit.setVisible(True)
        self.filter_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.filter_edit.selectAll()

    def _on_filter_btn_clicked(self) -> None:
        """虫眼鏡ボタン: クリックで入力欄の表示切替 (checkable で状態が反転済)。"""
        if self.btn_filter.isChecked():
            self._open_filter()
        else:
            self._reset_filter()

    def _on_filter_escape(self) -> None:
        """Esc in filter_edit: 絞込を解除して閉じ、フォーカスをテーブルに戻す。"""
        self._reset_filter()

    def _reset_filter(self) -> None:
        """絞込検索を解除して入力欄を閉じる。サブフォルダ/タブ切替時にも呼ぶ。"""
        # textChanged が走るので _filter_query は "" に。_apply_filter も走って
        # 全行表示 + count_label 非表示になる。
        self.filter_edit.blockSignals(True)
        self.filter_edit.clear()
        self.filter_edit.blockSignals(False)
        self._filter_query = ""
        self.filter_edit.setVisible(False)
        self.btn_filter.setChecked(False)
        self.filter_count_label.setVisible(False)
        self.filter_count_label.setText("")
        self._apply_filter()
        # テーブル側に focus を戻す (空でない場合のみ。空の事件タブは無干渉)
        if self.table.rowCount() > 0:
            self.table.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_filter_text_changed(self, text: str) -> None:
        self._filter_query = text
        self._apply_filter()

    def _apply_filter(self) -> None:
        """現在のテーブル行に対して `_filter_query` でフィルタを適用。
        空白区切り AND 検索 (大小無視・部分一致)。`..` 行は常に表示。
        フィルタ中は `X / Y 件` をラベルに出す。"""
        query = self._filter_query.strip()
        tokens = [t.lower() for t in query.split()] if query else []
        visible_n = 0
        total_n = 0
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if not isinstance(it, _NameItem):
                continue
            if it.is_parent:
                self.table.setRowHidden(row, False)
                continue
            total_n += 1
            if not tokens:
                self.table.setRowHidden(row, False)
                visible_n += 1
                continue
            name = it.path.name.lower()
            ok = all(tok in name for tok in tokens)
            self.table.setRowHidden(row, not ok)
            if ok:
                visible_n += 1
        if tokens:
            self.filter_count_label.setText(f"{visible_n} / {total_n} 件")
            self.filter_count_label.setVisible(True)
        else:
            self.filter_count_label.setVisible(False)

    def select_path_in_table(self, path: Path) -> None:
        """指定パスの行を選択状態にする (rename 直後にフォーカスを保つため)。
        `setCurrentCell` 単独だと currentIndex だけ動いて selection が
        更新されない (= 点線囲いのみ、濃紺にならず itemSelectionChanged
        も発火しない) ケースがあるため、ADR-24 と同じ
        setCurrentIndex(NoUpdate) → select(ClearAndSelect|Rows) パターンで
        確実にプレビュー連動も発火させる。"""
        self._restore_selection_by_paths({str(path)})

    def refresh_current_view(self) -> None:
        """投入・rename・削除後に外部から呼ぶ: 現フォルダ再走査 + サブ件数更新。

        ネストしていた場合はパンくずをできる限り保持する (途中フォルダが消えて
        いれば残っている所まで戻る)。
        """
        if self._scan is None:
            return
        prev_view = self._cur_view_id
        prev_crumb = list(self._crumb)
        # サブフォルダの件数バッジが変わるので scan を取り直し、左ボタン再構築
        self._scan = scan_case_folder(self._scan.root_path)
        self._rebuild_subfolder_buttons()

        target_view = prev_view if prev_view in self._view_btns else (
            0 if self._scan.subfolders else ROOT_VIEW_ID
        )
        self._browse(target_view)
        # ネストを 1 段ずつ復元 (途中で実体が消えていたらそこで停止)
        if target_view == prev_view:
            for name, path in prev_crumb[1:]:
                if path.is_dir():
                    self._crumb.append((name, path))
                    self._cur_dir = path
                else:
                    break
            self._show_current()

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

        # 内部状態 + タブ表示 + 走査結果を更新 (タブラベルは依頼者名+案件名)
        self._case_paths[idx] = new_path
        code, name = _parse_case(new_path)
        self.case_tabs.blockSignals(True)
        self.case_tabs.setTabText(idx, _tab_label(code, name))
        self.case_tabs.setTabToolTip(idx, f"{code}  {name}")
        self.case_tabs.blockSignals(False)
        self._load_case(idx)

    # ───────── 外部 API ─────────

    def current_case(self) -> tuple[str, str]:
        idx = self.case_tabs.currentIndex()
        if 0 <= idx < len(self._case_paths):
            return _parse_case(self._case_paths[idx])
        return ("?", "?")

    def set_compact(self, compact: bool) -> None:
        """プレビュー展開時 (3 カラムモード) は Name 列のみに絞り、
        ペインが狭くてもファイル名が読めるようにする (InboxPane と同方針)。
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
        # 基準幅は MainWindow が両ペイン共通値 (_shared_name_width) を渡していれば
        # それを使う (InboxPane と同方針)。自前 viewport だと INBOX と参照フォルダで
        # 数 px ずれ、その差が 30px 閾値をまたぐと片方だけ更新列が消えて Name 幅が
        # 半々にならない (F4 半幅時 / Win で参照フォルダにファイルが多い時に頻発)。
        shared = getattr(self, "_shared_name_width", None)
        viewport_w = shared if shared else self.table.viewport().width()
        date_avail = viewport_w - (60 + 90 + 120)
        if date_avail < 30:
            self.table.setColumnHidden(2, True)
        else:
            self.table.setColumnHidden(2, False)
            self.table.setColumnWidth(2, min(date_avail, 130))

    def set_shared_name_width(self, width: int | None) -> None:
        """MainWindow から INBOX / 参照フォルダ共通の基準幅を受け取る。

        両ペインで更新列の出し入れ判定を完全に一致させるためのフック。None を
        渡すと自前 viewport にフォールバックする (単体利用 / テスト時)。
        """
        self._shared_name_width = width
        self._apply_responsive_columns()

    def set_inbox_file_getter(self, getter) -> None:
        """右クリック投入メニューが Inbox の選択ファイル名を問い合わせる getter。

        getter() は選択中ファイル名 (str)、未選択なら None を返すこと。
        """
        self._inbox_file_getter = getter

    def set_doc_root_getter(self, getter) -> None:
        """事件ショートカット判定に使う ksystemz doc_root の getter。

        getter() は ksystemz の doc_root_path (Path) または None を返す。
        None なら全 symlink/.lnk は通常フォルダとして扱う (タブ切替しない)。
        """
        self._doc_root_getter = getter
