"""自動アップデート UI (案②)。

役割分担:
  - `UpdateBanner` — ステータスバーに常駐する小型ウィジェット (「v0.X.Y 公開
    [更新...] [×]」)。更新が無ければ非表示。
  - `UpdateManager` — MainWindow から制御する更新フロー全体:
      1. 起動時に裏で GitHub Releases をチェック (QThread + urllib)
      2. 新版あればバナー表示
      3. ユーザーが「更新...」 → QNetworkAccessManager で zip DL (進捗ダイアログ)
      4. DL 完了 → 確認ダイアログ「再起動して適用しますか？」
      5. はい → updater バッチ生成 → detached 起動 → k-file 終了

dev 実行 (PyInstaller --onedir でない、`python -m src.main`) では install_dir
が取れないため、適用は「未対応」メッセージを出して終わる (通知 + DL までは動く)。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QWidget,
)

from src.core.updater import (
    ReleaseInfo,
    default_updates_dir,
    find_newer_release,
    install_dir_from_exe,
    write_updater_script,
)


# ───────── UpdateBanner (status bar に常駐) ─────────


class UpdateBanner(QWidget):
    """「v0.X.Y 公開 [更新...] [×]」をステータスバー左に常駐させる小型 widget。

    通常は非表示。`show_for(release)` で表示、`hide_banner()` で隠す。
    クリック動作は外から `updateClicked` / `dismissClicked` シグナルで受ける。
    """

    updateClicked = Signal()
    dismissClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateBanner")
        # バナー高 16px 固定。見切れ根治の本質は「バー高 > バナー高 + QStatusBar の
        # 上寄せ offset(≈3px)」を満たすこと (win95.qss の QStatusBar=20px 参照)。
        # バナーとバーを同じ 20px に揃えると offset 分だけ下端がはみ出し、β.4〜β.10
        # の見切れが再発する。バナーは 16px のままにし、余白はバー側(20px)が持つ。
        # 内部ボタンは #updateBannerBtn で内寸 14px(+枠2px=16px) にして 9pt の字を収める。
        self.setFixedHeight(16)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(3)
        self._label = QLabel("")
        self._label.setObjectName("updateBannerLabel")
        layout.addWidget(self._label)
        self._btn_update = QPushButton("更新...")
        self._btn_update.setObjectName("updateBannerBtn")
        self._btn_update.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_update.clicked.connect(self.updateClicked.emit)
        layout.addWidget(self._btn_update)
        self._btn_dismiss = QPushButton("×")
        self._btn_dismiss.setObjectName("updateBannerBtn")
        self._btn_dismiss.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_dismiss.setToolTip("今回起動中は非表示にする")
        self._btn_dismiss.setMaximumWidth(20)
        self._btn_dismiss.clicked.connect(self.dismissClicked.emit)
        layout.addWidget(self._btn_dismiss)
        # フォントを 9pt に「明示的に」固定する (16px のステータスバーに収めるため)。
        # QSS の font-size:9pt (#updateBannerLabel/#updateBannerBtn) だけでは効かない:
        # 起動時 apply_bitmap_font_strategy が全 widget を walk して w.font() を
        # setFont し直す際、QSS の font-size は w.font() に反映されない (描画段だけ)
        # ため、各 widget は継承した 12pt を「明示フォント」として焼き直され、QSS の
        # 9pt を上書きしてしまう (= バナーが 12pt で縦に見切れる, ADR-37 の積み残し)。
        # ここで各 widget の font を 9pt に明示設定しておけば walk が 9pt を保つ
        # (point_size=None の walk は既存サイズを維持し strategy だけ付与するため)。
        for _w in (self._label, self._btn_update, self._btn_dismiss):
            _f = _w.font()
            _f.setPointSize(9)
            _w.setFont(_f)
        self.setVisible(False)

    def show_for(self, release: ReleaseInfo) -> None:
        prefix = "🔔  "
        tag = release.tag
        self._label.setText(f"{prefix}{tag} が公開されました")
        self.setVisible(True)

    def hide_banner(self) -> None:
        self.setVisible(False)


# ───────── 起動時チェックを裏で走らせる QThread ─────────


class _CheckWorker(QObject):
    """`find_newer_release` を別スレッドで実行。完了時に結果を signal で返す。"""

    done = Signal(object)   # ReleaseInfo | None

    def __init__(self, local_version: str) -> None:
        super().__init__()
        self._local_version = local_version

    def run(self) -> None:
        try:
            rel = find_newer_release(self._local_version)
        except Exception:        # noqa: BLE001 - 起動チェックは何があっても黙る
            rel = None
        self.done.emit(rel)


# ───────── UpdateManager (MainWindow から呼び出される全体制御) ─────────


class UpdateManager(QObject):
    """起動時チェック → 通知 → DL → 適用 (= k-file 終了 + 新版起動) の全体。

    MainWindow から `mgr = UpdateManager(window, banner, local_version)` で
    インスタンス化、`mgr.check_async()` で起動チェック開始。
    """

    def __init__(
        self,
        main_window,                 # 親 (QMessageBox の parent 用)
        banner: UpdateBanner,
        local_version: str,
    ) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._banner = banner
        self._local_version = local_version
        self._release: ReleaseInfo | None = None
        self._thread: QThread | None = None
        self._worker: _CheckWorker | None = None
        self._dl_manager: QNetworkAccessManager | None = None
        self._dl_reply: QNetworkReply | None = None
        self._progress: QProgressDialog | None = None
        self._dl_path: Path | None = None

        banner.updateClicked.connect(self._on_update_clicked)
        banner.dismissClicked.connect(banner.hide_banner)

    # ───── 起動時チェック ─────

    def check_async(self) -> None:
        """別スレッドで `find_newer_release` を走らせる。完了時にバナー更新。"""
        if self._thread is not None:
            return   # すでに走っている
        self._thread = QThread(self)
        self._worker = _CheckWorker(self._local_version)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_check_done)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None

    def _on_check_done(self, release: object) -> None:
        if not isinstance(release, ReleaseInfo):
            return
        self._release = release
        self._banner.show_for(release)

    # ───── DL フロー ─────

    def _on_update_clicked(self) -> None:
        if self._release is None:
            return
        # 1 行確認ダイアログ (情報のみ、押すと DL 開始)
        ans = QMessageBox.question(
            self._main_window,
            "アップデート",
            (
                f"{self._release.tag} が公開されています。\n"
                f"ダウンロードして適用しますか？\n\n"
                f"(ダウンロード後、再起動して新版に切り替わります)"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._start_download(self._release)

    def _start_download(self, release: ReleaseInfo) -> None:
        updates_dir = default_updates_dir()
        updates_dir.mkdir(parents=True, exist_ok=True)
        dest = updates_dir / release.asset_name

        # 進捗ダイアログ (キャンセル可)
        total_mb = release.asset_size / (1024 * 1024) if release.asset_size else 0
        label = (
            f"{release.tag} をダウンロード中...\n"
            f"(約 {total_mb:.1f} MB)"
        ) if total_mb else f"{release.tag} をダウンロード中..."
        self._progress = QProgressDialog(
            label, "キャンセル", 0, 100, self._main_window,
        )
        self._progress.setObjectName("updateProgress")
        self._progress.setWindowTitle("アップデート DL")
        self._progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._progress.setMinimumDuration(0)
        self._progress.canceled.connect(self._cancel_download)
        self._progress.setValue(0)

        self._dl_path = dest
        if self._dl_manager is None:
            self._dl_manager = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(release.download_url))
        req.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader,
            f"k-file-updater/{self._local_version}",
        )
        # GitHub Release asset は redirect で S3 系に飛ぶので follow を有効に
        req.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        self._dl_reply = self._dl_manager.get(req)
        self._dl_reply.downloadProgress.connect(self._on_dl_progress)
        self._dl_reply.finished.connect(self._on_dl_finished)
        self._dl_reply.errorOccurred.connect(self._on_dl_error)

    def _on_dl_progress(self, received: int, total: int) -> None:
        if self._progress is None:
            return
        if total > 0:
            self._progress.setMaximum(int(total))
            self._progress.setValue(int(received))

    def _on_dl_error(self, _err) -> None:
        # finished も後で呼ばれるが、確実にメッセージを出す
        pass    # _on_dl_finished で reply.error() を見て統一処理

    def _on_dl_finished(self) -> None:
        reply = self._dl_reply
        progress = self._progress
        self._dl_reply = None
        self._progress = None
        if reply is None:
            return
        try:
            if progress is not None:
                progress.close()
            err = reply.error()
            if err != QNetworkReply.NetworkError.NoError:
                # キャンセル時は OperationCanceledError → 黙って終わる
                if err == QNetworkReply.NetworkError.OperationCanceledError:
                    return
                QMessageBox.warning(
                    self._main_window,
                    "ダウンロード失敗",
                    f"アップデートのダウンロードに失敗しました:\n{reply.errorString()}",
                )
                return
            # 成功: ファイルに保存
            data = bytes(reply.readAll())
            assert self._dl_path is not None
            self._dl_path.write_bytes(data)
            self._on_download_complete(self._dl_path)
        finally:
            reply.deleteLater()

    def _cancel_download(self) -> None:
        if self._dl_reply is not None:
            self._dl_reply.abort()

    # ───── 適用フロー (= 旧フォルダ退避 + 新版展開 + 再起動) ─────

    def _on_download_complete(self, zip_path: Path) -> None:
        assert self._release is not None
        install_dir = install_dir_from_exe()
        if install_dir is None:
            # dev 実行 (`python -m src.main`) では適用不可。DL 場所だけ通知。
            QMessageBox.information(
                self._main_window,
                "DL 完了 (dev mode)",
                (
                    f"{self._release.tag} の zip を以下に保存しました:\n\n"
                    f"{zip_path}\n\n"
                    "dev 環境 (python -m src.main 起動) では自動適用は無効です。"
                    "PyInstaller 配布版 (.exe) でのみ自動的に再起動して新版に切替えます。"
                ),
            )
            return
        ans = QMessageBox.question(
            self._main_window,
            "新版を適用",
            (
                f"{self._release.tag} の DL が完了しました。\n"
                f"今すぐ再起動して適用しますか？\n\n"
                f"(k-file を一度終了し、updater が旧フォルダを退避してから\n"
                f" 新版を展開して起動します。所要 5-10 秒)"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            QMessageBox.information(
                self._main_window,
                "アップデート保留",
                "次回起動時に再度通知します。",
            )
            return
        # updater (PowerShell スクリプト) を書き出して起動 → k-file 終了。
        script_path = write_updater_script(install_dir, zip_path)
        try:
            # PowerShell を CREATE_NO_WINDOW (隠しコンソール付き) で起動する。
            # DETACHED_PROCESS (コンソールなし) だと cmd の tasklist|findstr パイプが
            # デッドロックしハングした (ADR-36)。CREATE_NO_WINDOW なら Get-Process /
            # Expand-Archive / Start-Process が確実に動き、窓も出ない (実機検証済)。
            # cwd は install_dir の外 (= %TEMP%) に固定 (install_dir を CWD にすると
            # rename できないため)。k-file が終了しても本プロセスは生き続ける。
            no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [
                    "powershell.exe", "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-File", str(script_path),
                ],
                cwd=tempfile.gettempdir(),
                creationflags=(no_window if sys.platform == "win32" else 0),
                close_fds=True,
            )
        except OSError as e:
            QMessageBox.warning(
                self._main_window,
                "updater 起動失敗",
                f"updater の起動に失敗しました:\n{e}\n\n"
                f"手動適用してください:\n{script_path}",
            )
            return
        # k-file 自身を終了 (updater は k-file.exe が消えるのを待ってから動く)
        self._main_window.close()
