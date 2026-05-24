"""Inbox と参照フォルダの間に置く縦長コマンドストリップ。

Norton Commander 風の中央コマンド列。マウス派の代替操作の主役。

レイアウト (上→下):
  [1] [2] [3] ... [N] [0]   ← 現在の事件のサブフォルダに対応した可変ボタン群
  ───                          (区切り)
  [✕] [↶]                    ← ユーティリティ (無視 / Undo)

数字ボタンは Alt+1〜9 / Alt+0 と同じ動作 (Inbox 選択 → 投入 + 投入先を開く)。
Inbox 未選択時は「閲覧のみ」として、そのサブフォルダの中身を表示する。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout, QWidget


class CommandStrip(QWidget):
    """Inbox と参照フォルダの間に挟む細い縦バー。"""

    STRIP_WIDTH = 52  # ペイン外から見える視覚幅 (動的レイアウト計算で参照)

    # 数字ボタン (1..9, 0) クリック → view_id を載せて通知
    subfolderClicked = Signal(int)
    # << ボタン: 中央ペイン選択ファイルを実デスクトップへ戻す (一時保留)
    returnToDesktopClicked = Signal()
    ignoreClicked = Signal()
    deleteClicked = Signal()
    undoClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandStrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(self.STRIP_WIDTH)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(2, 4, 2, 4)
        self._lay.setSpacing(2)
        self._lay.addStretch(1)

        # 動的サブフォルダボタン (set_subfolder_targets で再構築)
        self._target_btns: list[QPushButton] = []

        # 区切り (薄い水平凹線 = Win95 風 sunken)
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        self._sep.setFrameShadow(QFrame.Shadow.Sunken)
        self._sep.setFixedHeight(4)
        self._lay.addWidget(self._sep)

        # << : 中央ペイン選択ファイルを実デスクトップへ戻す
        # (Inbox に再循環させる前段。デスクトップは OS 管理で消えないため安全)
        self.btn_return = self._make_btn(
            "<<",
            "中央ペインの選択ファイルを\n実デスクトップへ戻す (一時保留)",
        )
        self.btn_return.clicked.connect(self.returnToDesktopClicked.emit)
        self._lay.addWidget(self.btn_return)

        self._sep2 = QFrame()
        self._sep2.setFrameShape(QFrame.Shape.HLine)
        self._sep2.setFrameShadow(QFrame.Shadow.Sunken)
        self._sep2.setFixedHeight(4)
        self._lay.addWidget(self._sep2)

        # ユーティリティ: 無視 / 削除 / Undo (常設)
        # "無視" は表示除外のみ (実ファイルは触らない)、"削除" は OS ごみ箱送り。
        # 当初は "✕" 1 個だったが削除と誤認しやすいため文字ラベルに統一 + 分離。
        self.btn_ignore = self._make_btn(
            "無視",
            "Inbox 選択ファイルを表示から除外 / 解除 (実ファイルは触らない)",
        )
        self.btn_ignore.clicked.connect(self.ignoreClicked.emit)
        self._lay.addWidget(self.btn_ignore)

        self.btn_delete = self._make_btn(
            "削除",
            "選択ファイルを OS ごみ箱へ送る (Del キー相当。Inbox / 中央のどちらか)",
        )
        self.btn_delete.clicked.connect(self.deleteClicked.emit)
        self._lay.addWidget(self.btn_delete)

        self.btn_undo = self._make_btn("↶", "Undo (M4 で実装予定)")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undoClicked.emit)
        self._lay.addWidget(self.btn_undo)

        self._lay.addStretch(1)

    def set_subfolder_targets(self, targets: list[tuple[str, int]]) -> None:
        """事件のサブフォルダ構成に合わせて数字ボタン群を作り直す。

        `targets` = [(ラベル文字, view_id), ...]。表示順 (通常 "1".."9", "0")。
        既存ボタンを破棄して並び直す。
        """
        # 既存ボタンを除去
        for btn in self._target_btns:
            self._lay.removeWidget(btn)
            btn.deleteLater()
        self._target_btns.clear()

        # _sep の前 (= 上方) に挿入していく。
        # _lay の最初は addStretch(1) なので index=1 から順番に。
        insert_at = 1
        for label, view_id in targets:
            btn = self._make_btn(
                label,
                f"Inbox 選択 → {label} へ投入 (未選択時は閲覧のみ)",
            )
            btn.clicked.connect(
                lambda _=False, vid=view_id: self.subfolderClicked.emit(vid)
            )
            self._lay.insertWidget(insert_at, btn)
            self._target_btns.append(btn)
            insert_at += 1

    def _make_btn(self, label: str, tooltip: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("stripBtn")
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setToolTip(tooltip)
        return btn
