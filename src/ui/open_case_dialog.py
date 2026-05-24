"""「事件を開く」(Ctrl+O) ダイアログ — Win95 風 frameless モーダル。

ksystemz.db (RO) を `core/case_repo.CaseRepo` 経由で検索し、選択した事件を
返す。MainWindow が戻り値を使って case_pane にタブを追加する。

レイアウト:
  [TitleBar]
  [検索:____________] [☑ 現在進行中のみ]
  [Code / 依頼者 / 種別 / 状態 / 事件名 のテーブル]
  [説明テキスト]                           [開く] [キャンセル]

操作:
  - 検索ボックス変更で即時フィルタ (LIKE 部分一致)
  - 「現在進行中のみ」OFF で 顧問・終了・諸件・不受任 も表示
  - ダブルクリック / Enter / 「開く」ボタンで accept、Esc / キャンセルで reject
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.core.case_repo import CaseRecord, CaseRepo
from src.ui._font_strategy import apply_bitmap_font_strategy
from src.ui.title_bar import TitleBar


class OpenCaseDialog(QDialog):
    """ksystemz.db を検索して事件 1 件を選ばせるモーダル。"""

    def __init__(self, repo: CaseRepo, parent=None) -> None:
        super().__init__(parent)
        # Win95 raised 外縁 QSS を共有 (#renameDialog ルールを流用)
        self.setObjectName("renameDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.resize(640, 420)   # 9pt サイズ (事件名/依頼者名で見やすい幅)

        self._repo = repo
        self._selected: CaseRecord | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)   # raised 外縁 2px と重ならないため
        outer.setSpacing(0)

        title = TitleBar(self, minimal=True)
        title.set_title("事件を開く")
        outer.addWidget(title)

        body = QVBoxLayout()
        body.setContentsMargins(10, 8, 10, 8)
        body.setSpacing(6)

        # ── 上段: 検索ボックス + 「現在進行中のみ」チェック ──
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(QLabel("検索:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("事件番号 / 事件名 / 依頼者 / 法人名")
        self._search.textChanged.connect(self._reload)
        top.addWidget(self._search, stretch=1)
        self._active_only = QCheckBox("現在進行中のみ")
        self._active_only.setChecked(True)
        self._active_only.toggled.connect(self._reload)
        top.addWidget(self._active_only)
        body.addLayout(top)

        # ── 中段: 結果テーブル ──
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["事件番号", "依頼者", "種別", "状態", "事件名"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(1, 130)
        self._table.cellDoubleClicked.connect(lambda _r, _c: self._accept())
        body.addWidget(self._table, stretch=1)

        # ── 下段: 件数表示 + 開く / キャンセル ──
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #555;")
        bottom.addWidget(self._count_label)
        bottom.addStretch(1)
        self._open_btn = QPushButton("開く")
        self._open_btn.setDefault(True)
        self._open_btn.clicked.connect(self._accept)
        bottom.addWidget(self._open_btn)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        body.addLayout(bottom)

        outer.addLayout(body)

        # Esc で reject (RenameDialog の inject モードと違って通常キャンセル)
        esc = QShortcut(QKeySequence("Escape"), self)
        esc.activated.connect(self.reject)

        # 検索ボックスに初期フォーカス
        self._search.setFocus()
        self._reload()
        # 本体と同じ MS Gothic ビットマップ戦略を適用
        apply_bitmap_font_strategy(self, point_size=9)

    def _reload(self) -> None:
        """検索条件を再評価してテーブルを書き換える。"""
        try:
            results = self._repo.search(
                keyword=self._search.text().strip(),
                active_only=self._active_only.isChecked(),
            )
        except Exception as e:
            self._count_label.setText(f"検索失敗: {e}")
            self._table.setRowCount(0)
            return

        self._table.setRowCount(len(results))
        for r, rec in enumerate(results):
            self._table.setItem(r, 0, QTableWidgetItem(rec.case_code))
            self._table.setItem(r, 1, QTableWidgetItem(rec.client_display))
            self._table.setItem(r, 2, QTableWidgetItem(rec.case_type))
            self._table.setItem(r, 3, QTableWidgetItem(rec.status))
            self._table.setItem(r, 4, QTableWidgetItem(rec.case_name))
            # row → CaseRecord を引けるよう UserRole に格納 (0 列)
            self._table.item(r, 0).setData(Qt.ItemDataRole.UserRole, rec)
            self._table.setRowHeight(r, 16)
        self._count_label.setText(f"{len(results)} 件")

        if results:
            self._table.setCurrentCell(0, 0)

    def _accept(self) -> None:
        """選択行を _selected に格納して accept。"""
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        rec = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(rec, CaseRecord):
            self._selected = rec
            self.accept()

    def selected(self) -> CaseRecord | None:
        """確定した事件 (accept 後)。reject 時は None。"""
        return self._selected
