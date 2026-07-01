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
import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QToolTip

from src.core.ui_scale import (
    DEFAULT_SCALE,
    SETTING_KEY as UI_SCALE_KEY,
    parse_scale,
    scale_factor_str,
)
from src.infra.kfile_db import KFileDB, app_data_dir
from src.ipc import IpcServer, try_send_to_primary
from src.ui._font_strategy import apply_bitmap_font_strategy, tooltip_font
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


def _apply_ui_scale() -> None:
    """kfile.db の表示倍率を QT_SCALE_FACTOR に反映する (QApplication 生成前に呼ぶ)。

    ユーザーが「表示 → 表示倍率」で選んだ倍率で、ウインドウ・文字・全 widget を
    一律にスケールする。QT_SCALE_FACTOR は Qt が起動時に一度だけ読むため、倍率変更は
    再起動で反映する (MainWindow が自動再起動する)。100% のときは環境変数を触らない
    = OS 側スケール (ADR-45 PassThrough) に一切干渉しない。DB 読取失敗時も既定 100%。
    """
    try:
        db = KFileDB()
        percent = parse_scale(db.get_setting(UI_SCALE_KEY))
        db.close()
    except Exception:
        percent = DEFAULT_SCALE
    if percent != DEFAULT_SCALE:
        os.environ["QT_SCALE_FACTOR"] = scale_factor_str(percent)


def main() -> int:
    # 表示倍率 (ユーザー設定) を QApplication 生成前に環境変数へ反映する。
    _apply_ui_scale()
    # High-DPI: 拡大率 (125%/150% 等) を OS 設定そのままに追従させる (PassThrough)。
    # 100% 表示では scale factor=1.0 で一切影響しない (= 通常運用には無影響)。
    # ビットマップフォント + 固定 px 前提のため、拡大時の最終的な見え方 (にじみ /
    # レイアウト溢れ) は Win 実機で要確認 (β.12 課題)。崩れたら Round 等へ調整する。
    # ※ この静的設定は QApplication 生成より前に呼ぶ必要がある。
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("k-file")
    app.setOrganizationName("k-file")
    from src.__version__ import VERSION
    app.setApplicationVersion(VERSION)
    app.setStyle("Windows")  # Fusion / windowsvista を避けて Win95 寄りに固定
    app.setStyleSheet(_load_stylesheet())
    app.setWindowIcon(_app_icon())  # タスクバー / Alt+Tab / 自作タイトルバー用

    initial_paths = parse_initial_paths(sys.argv)

    # 単一インスタンス + IPC (M6b): 既存 primary プロセスがあればそこへ
    # パスを送って自分は終了する。K-SystemZ から「フォルダを開く」を連打
    # しても 1 つの k-file ウインドウにタブが集約される。
    if try_send_to_primary(initial_paths):
        return 0

    window = MainWindow(initial_paths=initial_paths)
    window.show()
    # MainWindow が kfile.db から文字描画モード (ガタガタ/中間/なめらか) を復元済。
    # 全 widget tree へ最終適用し、ツールチップも同モードに揃える。
    apply_bitmap_font_strategy(window)
    QToolTip.setFont(tooltip_font())

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
    # sys.exit は try の外に置く。try 内に置くと正常終了 (SystemExit:0) まで
    # except BaseException が拾い、毎回 error.log に SystemExit のトレースを
    # 書いてしまう (secondary→primary 転送の return 0 でも毎回記録され、
    # error.log が「正常なのにエラーだらけ」に見えるノイズになる)。ここでは
    # main() の実行中に実際に送出された致命例外だけを記録して再送出する。
    try:
        exit_code = main()
    except BaseException as e:
        _log_startup_error(e)
        raise
    sys.exit(exit_code)
