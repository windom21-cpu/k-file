"""ファイル名変更ダイアログ (Win95 風 frameless + 自前タイトルバー)。

二つのモードを兼ねる:
- mode="inject": Inbox → サブフォルダ投入時の rename。**Esc = 元名のまま投入**
  (HANDOVER §2)。「投入」ボタンで現在の名前で投入、Cancel で取り消し。
- mode="rename": F2 によるファイル単体の名前変更。Esc = 通常通りキャンセル。

「最近使った名前」を combobox で候補表示。OS のリネーム UI に合わせ、初期選択は
拡張子を除いた stem 部分だけ (拡張子を誤って壊さないように)。
"""
from __future__ import annotations

from pathlib import PurePath

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from src.core.file_ops import validate_name
from src.ui.title_bar import TitleBar


class RenameDialog(QDialog):
    """名前を尋ねるだけの小さいダイアログ。

    結果は `exec()` の戻り値で判定し、入力名は `chosen_name()` で取得する:
        - `QDialog.Accepted` (1): ユーザーが OK / Enter / (inject時) Esc で確定
        - `QDialog.Rejected` (0): Cancel ボタンや × で取り消し
    """

    def __init__(
        self,
        original_name: str,
        recent: list[str],
        *,
        mode: str = "inject",
        target_label: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("renameDialog")
        # WA_StyledBackground: QSS の border が描画されるよう (frameless 時必須)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.setMinimumWidth(380)

        self._original = original_name
        self._mode = mode
        self._chosen: str = original_name
        self._error_label: QLabel  # 入力検証時のエラー表示
        self._combo: QComboBox

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        title = "ファイルを投入" if mode == "inject" else "名前の変更"
        title_bar = TitleBar(self, minimal=True)
        title_bar.set_title(title)
        outer.addWidget(title_bar)

        body = QVBoxLayout()
        body.setContentsMargins(10, 8, 10, 10)
        body.setSpacing(6)

        if mode == "inject" and target_label:
            body.addWidget(QLabel(f"投入先:  {target_label}"))
        body.addWidget(QLabel(f"元の名前:  {original_name}"))

        body.addWidget(QLabel("新しい名前:"))
        self._combo = QComboBox()
        self._combo.setEditable(True)
        # 候補: original を先頭、その後重複除去で最近使った順
        items = [original_name]
        for n in recent:
            if n not in items:
                items.append(n)
        self._combo.addItems(items)
        self._combo.setCurrentText(original_name)
        # 拡張子を除いた stem 部分だけ選択 (誤って拡張子を壊さない、Windows 流儀)
        line = self._combo.lineEdit()
        if line is not None:
            stem_len = len(PurePath(original_name).stem)
            line.setSelection(0, stem_len)
        body.addWidget(self._combo)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #800000;")
        self._error_label.setVisible(False)
        body.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addStretch(1)
        self._ok_btn = QPushButton("投入" if mode == "inject" else "OK")
        self._ok_btn.setDefault(True)        # Enter で OK
        self._ok_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._ok_btn)
        self._cancel_btn = QPushButton("キャンセル")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)
        body.addLayout(btn_row)

        outer.addLayout(body)

        # Esc: mode により挙動分岐
        # - inject: 「元名のまま投入」確定 (HANDOVER §2)
        # - rename: 通常通りキャンセル
        esc = QShortcut(QKeySequence("Escape"), self)
        if mode == "inject":
            esc.activated.connect(self._accept_as_original)
        else:
            esc.activated.connect(self.reject)

    def _on_accept(self) -> None:
        """OK / Enter: 現在の入力テキストを検証して確定。"""
        name = self._combo.currentText().strip()
        err = validate_name(name)
        if err is not None:
            self._error_label.setText(err)
            self._error_label.setVisible(True)
            return
        self._chosen = name
        self.accept()

    def _accept_as_original(self) -> None:
        """Esc (inject 時のみ): 元名のまま投入を確定。"""
        self._chosen = self._original
        self.accept()

    def chosen_name(self) -> str:
        """確定された名前 (検証済み)。Rejected 時は意味を持たない。"""
        return self._chosen
