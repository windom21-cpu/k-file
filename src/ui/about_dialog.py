"""ヘルプ →「k-file について」の Win95/98 風バージョン情報ウインドウ。

QMessageBox.about() のモダンな見た目を避け、アプリ本体と同じく
Frameless + 自作タイトルバー (× のみ) + 灰色 beveled body で再現する。

本文は **QVBoxLayout 直挿し** (内側 QWidget でラップしない) で組む。
ラッパ QWidget を入れると自身の背景でダイアログの raised 外縁を覆ってしまい、
border が見えなくなる (RenameDialog と同じ方針)。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.title_bar import TitleBar


class AboutDialog(QDialog):
    """Win95/98 風の「バージョン情報」ダイアログ。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aboutDialog")
        # WA_StyledBackground: QSS の raised 外縁を描かせる (frameless 時必須)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setModal(True)
        self.setFixedSize(360, 175)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Win95 風タイトルバー (× のみ) ──
        self.title_bar = TitleBar(self, minimal=True)
        self.title_bar.set_title("k-file のバージョン情報")
        outer.addWidget(self.title_bar)

        # ── 本文 (内側ラッパ QWidget を作らず QVBoxLayout 直挿し) ──
        body_l = QVBoxLayout()
        body_l.setContentsMargins(12, 11, 12, 10)
        body_l.setSpacing(7)

        # アイコン枠 + アプリ名/説明 (Win95 about の定番レイアウト)
        top = QHBoxLayout()
        top.setSpacing(11)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(40, 40)
        _app = QApplication.instance()
        if _app is not None:
            icon.setPixmap(_app.windowIcon().pixmap(36, 36))
        top.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        app_name = QLabel("k-file — 案件ドキュメント作業台")
        app_name.setObjectName("aboutAppName")
        text_col.addWidget(app_name)
        text_col.addWidget(QLabel("バージョン M5 (K-SystemZ 連携 + 設定 + 復元)"))
        text_col.addWidget(QLabel("法律実務向け 2/3 ペイン型ファイラー"))
        text_col.addStretch(1)
        top.addLayout(text_col, stretch=1)
        body_l.addLayout(top)

        # Win95 彫り込み線 (ペイン見出しと共用の #etchedLine)
        sep = QFrame()
        sep.setObjectName("etchedLine")
        sep.setFixedHeight(2)
        body_l.addWidget(sep)

        body_l.addWidget(
            QLabel("PySide6 / Python — ローカル完結・実ファイル主義")
        )
        body_l.addStretch(1)

        # OK ボタン (右寄せ、Enter で確定)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        ok = QPushButton("OK")
        ok.setObjectName("aboutOkBtn")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        body_l.addLayout(btn_row)

        outer.addLayout(body_l, stretch=1)

        # 親ウインドウの中央に配置 (Frameless なので自前で位置決め)
        if parent is not None:
            c = parent.geometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
