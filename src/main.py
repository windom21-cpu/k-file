"""k-file エントリポイント

PySide6 を起動し、Win95 QSS を適用してメインウインドウを表示する。
PyInstaller --onefile で配布されたときは sys._MEIPASS から resources を読む。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def _base_path() -> Path:
    """開発時 / PyInstaller バンドル時の両方で resources を解決するための基準パス。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # PyInstaller の展開先
    return Path(__file__).resolve().parent.parent  # 開発時: リポ root


def _load_stylesheet() -> str:
    qss_path = _base_path() / "resources" / "style" / "win95.qss"
    return qss_path.read_text(encoding="utf-8")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("k-file")
    app.setOrganizationName("k-file")
    app.setStyle("Windows")  # Fusion / windowsvista を避けて Win95 寄りに固定
    app.setStyleSheet(_load_stylesheet())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
