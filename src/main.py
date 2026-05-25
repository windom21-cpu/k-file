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

import datetime
import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QToolTip

from src.infra.kfile_db import app_data_dir
from src.ipc import IpcServer, try_send_to_primary
from src.ui._font_strategy import apply_bitmap_font_strategy
from src.ui.main_window import MainWindow


def _log_startup_error(exc: BaseException) -> None:
    """起動中に致命的な例外が出た時、APPDATA\\k-file\\error.log に追記する。

    K-SystemZ 側からは「.exe を起動したが何も出ない」状態が見えないため、
    ユーザー (法律実務家) が自分でログを開いて状況を確認できるようにする
    (連携設計の依頼事項 2026-05-25)。書き込みすら失敗しても黙って諦める。
    """
    try:
        log_dir = app_data_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "error.log"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n=== {datetime.datetime.now().isoformat()} ===\n")
            traceback.print_exception(
                type(exc), exc, exc.__traceback__, file=fh
            )
    except Exception:
        pass


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
    # ツールチップは top-level の別 widget で `*` 継承外。同じ MS Gothic
    # ビットマップ戦略で揃える (色/枠は QSS の QToolTip ルールで設定)。
    tooltip_font = QFont("MS Gothic", 12)
    tooltip_font.setStyleStrategy(
        QFont.StyleStrategy.PreferBitmap
        | QFont.StyleStrategy.NoAntialias
    )
    QToolTip.setFont(tooltip_font)
    app.setWindowIcon(_app_icon())  # タスクバー / Alt+Tab / 自作タイトルバー用

    initial_paths = parse_initial_paths(sys.argv)

    # 単一インスタンス + IPC (M6b): 既存 primary プロセスがあればそこへ
    # パスを送って自分は終了する。K-SystemZ から「フォルダを開く」を連打
    # しても 1 つの k-file ウインドウにタブが集約される。
    if try_send_to_primary(initial_paths):
        return 0

    window = MainWindow(initial_paths=initial_paths)
    window.show()
    apply_bitmap_font_strategy(window)

    # primary 側として LocalServer を立ち上げ、後発プロセスからのパス送信を待つ
    def _open_paths_from_ipc(paths: list[Path]) -> None:
        opened = 0
        for p in paths:
            try:
                if p.is_dir():
                    window.case_pane.add_case_tab(p)
                    opened += 1
            except OSError:
                continue
        # 後発プロセスが届いた合図として常にウインドウを前面に出す
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()
        if opened:
            window.statusBar().showMessage(
                f"K-SystemZ 等から {opened} 件のフォルダを受信", 4000
            )

    window._ipc_server = IpcServer(_open_paths_from_ipc, parent=window)
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException as e:
        # 起動経路 (main() 内 / Qt import 等) で発生した致命例外を error.log へ
        _log_startup_error(e)
        raise
