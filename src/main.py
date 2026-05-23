"""k-file エントリポイント

PySide6 を起動し、Win95 QSS を適用してメインウインドウを表示する。
PyInstaller --onefile で配布されたときは sys._MEIPASS から resources を読む。

コマンドライン引数 (M6a):
    k-file.exe "C:\\path\\to\\folder" ["別フォルダ"...]
        → 渡されたフォルダを順に事件タブとして開く。
        セッション復元 (前回 open_tabs) の後に追加され、最後の引数が active に。
        K-SystemZ の「フォルダを開く」連携 (subprocess.Popen) の窓口。
        非事件フォルダも受け付ける (汎用ファイラー化、ADR-15 と整合)。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
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


def _app_icon() -> QIcon:
    """アプリアイコン (タスクバー / Alt+Tab / 各ウインドウ)。

    複数サイズの PNG を addFile して、用途に応じた解像度を Qt に選ばせる。
    """
    icon = QIcon()
    icons_dir = _base_path() / "resources" / "icons"
    for png in sorted(icons_dir.glob("favicon-*.png")):
        icon.addFile(str(png))
    return icon


def parse_initial_paths(argv: list[str]) -> list[Path]:
    """sys.argv から事件タブとして開くフォルダパスを抽出 (M6a)。

    argv[0] (実行ファイル) はスキップ、以降のうちディレクトリとして実在するものだけ。
    ファイルや実在しないパスは無視 (黙って捨てる)。
    """
    out: list[Path] = []
    for arg in argv[1:]:
        if not arg:
            continue
        try:
            p = Path(arg)
        except (TypeError, ValueError):
            continue
        if p.is_dir():
            out.append(p)
    return out


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("k-file")
    app.setOrganizationName("k-file")
    app.setStyle("Windows")  # Fusion / windowsvista を避けて Win95 寄りに固定
    app.setStyleSheet(_load_stylesheet())
    app.setWindowIcon(_app_icon())  # タスクバー / Alt+Tab / 自作タイトルバー用

    initial_paths = parse_initial_paths(sys.argv)
    window = MainWindow(initial_paths=initial_paths)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
