"""自動アップデート機構 (案②) のコアロジック。

`案②`: 起動時 GitHub Releases API で最新版チェック → 新版あれば通知 →
ユーザー承認後に zip を自動 DL → updater バッチ生成 → k-file 終了 → updater が
旧フォルダ退避 + 新版展開 + 新版起動 + 旧フォルダ削除。

このモジュールは「ロジック」だけ (UI はここに置かない):
  - `fetch_latest_release()`     — GitHub Releases API call (blocking)
  - `pick_zip_asset()`           — JSON から zip アセットを 1 件選ぶ
  - `write_updater_batch()`      — Windows バッチを書き出す
  - `default_updates_dir()`      — `%APPDATA%/k-file/updates/` を返す

UI 側 (status bar / 進捗 / 確認) と DL 進捗ストリーミングは `ui/update_banner.py`
で QNetworkAccessManager を使う。Linux dev では HTTP / バッチは動かさず、unit
テストのみで動作確認する。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from src.core.version import is_newer

# 連絡先 (環境固定で OK、テストでも使う)
GITHUB_OWNER = "windom21-cpu"
GITHUB_REPO = "k-file"
RELEASES_API_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
)

# CI が upload する asset 名 (.github/workflows/build.yml と整合)
ASSET_NAME = "k-file-windows.zip"


@dataclass
class ReleaseInfo:
    """Releases API の必要なフィールドだけまとめた struct。"""

    tag: str                 # 例: "v0.1.0-beta.1"
    version: str             # tag から "v" を取り除いた値
    prerelease: bool
    download_url: str        # zip の direct URL
    asset_name: str
    asset_size: int          # bytes


def fetch_latest_release(
    timeout: float = 5.0,
    api_url: str = RELEASES_API_URL,
) -> ReleaseInfo | None:
    """GitHub Releases API を叩いて「最新の zip asset を持つ release」を返す。

    最新判定は `published_at` 降順の先頭。prerelease (β タグ等) も含む — 後段の
    is_newer 比較で local 版より新しいかを最終判定する。

    通信失敗 (タイムアウト / オフライン / 403 rate limit 等) は **None を返す**
    (= 「黙って何もしない」)。起動時に毎回呼ぶので例外で落とさない。
    """
    try:
        req = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"k-file-updater/{GITHUB_OWNER}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if not isinstance(data, list) or not data:
        return None

    # published_at 降順 (API はそうなっているはずだが念のため sort)
    try:
        data.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    except (TypeError, KeyError):
        pass

    for release in data:
        if release.get("draft"):
            continue
        tag = release.get("tag_name") or ""
        if not tag:
            continue
        version = tag.lstrip("v").lstrip("V")
        asset = pick_zip_asset(release.get("assets") or [])
        if asset is None:
            continue
        return ReleaseInfo(
            tag=tag,
            version=version,
            prerelease=bool(release.get("prerelease", False)),
            download_url=asset["browser_download_url"],
            asset_name=asset["name"],
            asset_size=int(asset.get("size", 0)),
        )
    return None


def pick_zip_asset(assets: list[dict]) -> dict | None:
    """Release の assets 配列から k-file 用 zip を 1 件選ぶ。

    優先順位:
      1. `ASSET_NAME` と完全一致 (現 CI が upload する名前)
      2. `.zip` 拡張子の最初の asset (将来名前が変わっても fallback)
    """
    if not isinstance(assets, list):
        return None
    for a in assets:
        if a.get("name") == ASSET_NAME and a.get("browser_download_url"):
            return a
    for a in assets:
        if (
            isinstance(a.get("name"), str)
            and a["name"].lower().endswith(".zip")
            and a.get("browser_download_url")
        ):
            return a
    return None


def find_newer_release(
    local_version: str,
    timeout: float = 5.0,
    api_url: str = RELEASES_API_URL,
) -> ReleaseInfo | None:
    """fetch + バージョン比較を 1 関数にまとめた便利関数。
    新版が無ければ None。"""
    rel = fetch_latest_release(timeout=timeout, api_url=api_url)
    if rel is None:
        return None
    if is_newer(rel.version, local_version):
        return rel
    return None


def default_updates_dir() -> Path:
    """zip と updater バッチを置く作業ディレクトリ。

    Win: `%APPDATA%/k-file/updates/`
    Linux/Mac: `~/.config/k-file/updates/` (テストや dev で問題が出ないように)
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "k-file" / "updates"
    return Path.home() / ".config" / "k-file" / "updates"


def write_updater_batch(
    install_dir: Path,
    zip_path: Path,
    new_exe_name: str = "k-file.exe",
    batch_path: Path | None = None,
) -> Path:
    """Windows バッチを書き出して、その絶対パスを返す。

    install_dir: 現 k-file がインストールされているフォルダ
                 (例: `C:\\Users\\xxx\\k-file`、PyInstaller --onedir の dist フォルダ)
    zip_path:    DL 済みの zip ファイルパス
    new_exe_name: 起動する .exe 名 (zip 展開後の install_dir/<new_exe_name>)
    batch_path:  書き出し先。未指定なら zip 隣りに `apply_update.bat`

    バッチの動作:
      0. 作業フォルダを %TEMP% に移す (install_dir を CWD にしたままだと
         install_dir 自身を ren できないため。Explorer/K-SystemZ から起動された
         k-file.exe の CWD は install_dir のことが多い)
      1. k-file.exe プロセス消滅まで wait (タスクリスト確認、最大 30 秒)
         待機は `ping` で行う。`timeout` は console=False の windowed app から
         DETACHED で起動したバッチでは「コンソールなし」で即エラーになり待てない
      2. install_dir を install_dir + ".old" にリネーム (バックアップ)
         失敗 = フォルダがまだ使用中 → 旧版を起動し直してユーザーを取り残さない
      3. PowerShell Expand-Archive で zip を install_dir に展開
         新 exe が出てこなければロールバック (.old を元名に戻す)
      4. 新 install_dir/k-file.exe を起動
      5. .old フォルダ削除 (失敗しても黙る、AV スキャン中など)

    各ステップは `%~dp0updater.log` に追記する (失敗が「無反応」に見えないように。
    error.log と同じ "困ったらログを見る" 運用)。
    """
    if batch_path is None:
        batch_path = zip_path.with_name("apply_update.bat")
    install_dir = install_dir.resolve()
    zip_path = zip_path.resolve()
    old_dir = install_dir.with_name(install_dir.name + ".old")
    new_exe = install_dir / new_exe_name

    # cmd.exe バッチは ANSI / SJIS で UTF-8 BOM 無しが安全。エスケープは
    # 二重引用符でくくり、変数展開は `%~dp0` 等を活用。
    # 分岐は () ブロックを避け goto ラベルで書く (パス中の特殊文字で壊れにくい)。
    lines = [
        "@echo off",
        "setlocal enableextensions",
        'set "LOG=%~dp0updater.log"',
        'echo [%date% %time%] updater start >> "%LOG%"',
        # install_dir を CWD にしたままだと ren できないので外へ退避
        'cd /d "%TEMP%" 2>nul',
        # k-file.exe が落ちるまで wait (最大 30 秒、約 1 秒間隔)。
        # timeout はコンソールなしで効かないので ping で待つ。
        "set /a TRIES=30",
        ":wait_loop",
        f'tasklist /FI "IMAGENAME eq {new_exe_name}" '
        f'| findstr /I "{new_exe_name}" >nul',
        "if errorlevel 1 goto proceed",
        "set /a TRIES=TRIES-1",
        "if %TRIES% LEQ 0 goto proceed",
        "ping -n 2 127.0.0.1 >nul",
        "goto wait_loop",
        ":proceed",
        'echo [%date% %time%] wait done TRIES=%TRIES% >> "%LOG%"',
        # 旧 .old が残っていれば先に削除 (前回失敗の痕跡)
        f'if exist "{old_dir}" rmdir /S /Q "{old_dir}" >> "%LOG%" 2>&1',
        # 現フォルダを .old にリネーム (バックアップ)
        f'ren "{install_dir}" "{install_dir.name}.old"',
        "if errorlevel 1 goto ren_failed",
        # zip を install_dir に展開 (CI は dist/k-file/* を直に zip 化 = 中身が
        # install_dir 直下に出る)
        f'powershell -NoProfile -ExecutionPolicy Bypass -Command '
        f'"Expand-Archive -LiteralPath \'{zip_path}\' '
        f'-DestinationPath \'{install_dir}\' -Force" >> "%LOG%" 2>&1',
        # 展開後に新 exe が無ければ展開失敗 → ロールバック
        f'if not exist "{new_exe}" goto expand_failed',
        'echo [%date% %time%] update applied OK >> "%LOG%"',
        # 新版起動 (待たない)
        f'start "" "{new_exe}"',
        # 旧フォルダクリーンアップ (失敗しても OK)
        f'rmdir /S /Q "{old_dir}" >> "%LOG%" 2>&1',
        "goto end",
        # ── ren に失敗 = フォルダがまだ使用中。無傷なので旧版を起動し直す ──
        ":ren_failed",
        'echo [%date% %time%] ERROR ren failed (folder in use) >> "%LOG%"',
        f'start "" "{new_exe}"',
        "goto end",
        # ── 展開に失敗 = 新 exe が無い。.old を元名に戻して旧版を起動 ──
        ":expand_failed",
        'echo [%date% %time%] ERROR expand failed, rolling back >> "%LOG%"',
        f'if exist "{install_dir}" rmdir /S /Q "{install_dir}" >> "%LOG%" 2>&1',
        f'ren "{old_dir}" "{install_dir.name}"',
        f'start "" "{new_exe}"',
        "goto end",
        ":end",
        'echo [%date% %time%] updater end >> "%LOG%"',
        "endlocal",
        "exit /b 0",
    ]
    batch_path.parent.mkdir(parents=True, exist_ok=True)
    batch_path.write_text("\r\n".join(lines) + "\r\n", encoding="cp932")
    return batch_path


def install_dir_from_exe() -> Path | None:
    """PyInstaller --onedir で立ち上がった時の install_dir (= k-file.exe の親)。

    開発実行 (`python -m src.main`) では `sys.frozen` が無いので None。
    自動アップデート機構は --onedir 配布時のみ作動。
    """
    if not getattr(sys, "frozen", False):
        return None
    # sys.executable は dist/k-file/k-file.exe のフルパス
    return Path(sys.executable).parent
