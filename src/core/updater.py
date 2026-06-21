"""自動アップデート機構 (案②) のコアロジック。

`案②`: 起動時 GitHub Releases API で最新版チェック → 新版あれば通知 →
ユーザー承認後に zip を自動 DL → updater バッチ生成 → k-file 終了 → updater が
旧フォルダ退避 + 新版展開 + 新版起動 + 旧フォルダ削除。

このモジュールは「ロジック」だけ (UI はここに置かない):
  - `fetch_latest_release()`     — GitHub Releases API call (blocking)
  - `pick_zip_asset()`           — JSON から zip アセットを 1 件選ぶ
  - `write_updater_script()`     — 更新適用用の PowerShell スクリプトを書き出す
  - `default_updates_dir()`      — `%APPDATA%/k-file/updates/` を返す

UI 側 (status bar / 進捗 / 確認) と DL 進捗ストリーミングは `ui/update_banner.py`
で QNetworkAccessManager を使う。Linux dev では HTTP / バッチは動かさず、unit
テストのみで動作確認する。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
# zip の SHA256 を載せたサイドカー asset の拡張子 (= "<zip 名>.sha256")
SHA256_ASSET_SUFFIX = ".sha256"


@dataclass
class ReleaseInfo:
    """Releases API の必要なフィールドだけまとめた struct。"""

    tag: str                 # 例: "v0.1.0-beta.1"
    version: str             # tag から "v" を取り除いた値
    prerelease: bool
    download_url: str        # zip の direct URL
    asset_name: str
    asset_size: int          # bytes
    sha256_url: str | None = None   # ".sha256" サイドカー asset の URL (無ければ None)


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
        assets = release.get("assets") or []
        asset = pick_zip_asset(assets)
        if asset is None:
            continue
        sha = pick_sha256_asset(assets, asset["name"])
        return ReleaseInfo(
            tag=tag,
            version=version,
            prerelease=bool(release.get("prerelease", False)),
            download_url=asset["browser_download_url"],
            asset_name=asset["name"],
            asset_size=int(asset.get("size", 0)),
            sha256_url=(sha["browser_download_url"] if sha else None),
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


def pick_sha256_asset(assets: list[dict], zip_name: str) -> dict | None:
    """Release の assets 配列から zip の SHA256 サイドカーを 1 件選ぶ。

    優先順位:
      1. `<zip_name>.sha256` と完全一致 (CI が upload する名前)
      2. `.sha256` 拡張子の最初の asset (fallback)
    サイドカーが無い (= 旧 Release) 場合は None。照合は「あれば行う」保険扱い。
    """
    if not isinstance(assets, list):
        return None
    want = zip_name + SHA256_ASSET_SUFFIX
    for a in assets:
        if a.get("name") == want and a.get("browser_download_url"):
            return a
    for a in assets:
        if (
            isinstance(a.get("name"), str)
            and a["name"].lower().endswith(SHA256_ASSET_SUFFIX)
            and a.get("browser_download_url")
        ):
            return a
    return None


def sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """ファイルの SHA256 を小文字 hex で返す (1MB ずつ読むのでメモリ安全)。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


def parse_sha256_text(text: str) -> str | None:
    """`.sha256` ファイルの中身から 64 桁 hex を 1 つ取り出して小文字で返す。

    許容する書式 (どれでも先頭の 64-hex を拾う):
      - `<hex>`
      - `<hex>  k-file-windows.zip`   (sha256sum 形式)
      - `SHA256(k-file-windows.zip)= <hex>`
      - `sha256:<hex>`
    見つからなければ None。
    """
    if not text:
        return None
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    return m.group(1).lower() if m else None


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


def _ps_quote(value: str) -> str:
    """PowerShell の単一引用符リテラルに安全に埋める ('' で ' をエスケープ)。"""
    return "'" + value.replace("'", "''") + "'"


def write_updater_script(
    install_dir: Path,
    zip_path: Path,
    new_exe_name: str = "k-file.exe",
    script_path: Path | None = None,
) -> Path:
    """更新適用用の **PowerShell スクリプト** を書き出し、その絶対パスを返す。

    install_dir: 現 k-file がインストールされているフォルダ
                 (例: `C:\\Users\\xxx\\k-file-windows`、PyInstaller --onedir のフォルダ)
    zip_path:    DL 済みの zip ファイルパス
    new_exe_name: 起動する .exe 名 (zip 展開後の install_dir/<new_exe_name>)
    script_path: 書き出し先。未指定なら zip 隣りに `apply_update.ps1`

    動作:
      1. k-file プロセス消滅まで wait (最大 30 秒、Get-Process でポーリング)
      2. install_dir を install_dir + ".old" にリネーム (バックアップ)
         失敗 = フォルダがまだ使用中 → 旧版を起動し直してユーザーを取り残さない
      3. Expand-Archive で zip を install_dir に展開
         新 exe が出てこなければロールバック (.old を元名に戻す)
      4. 新 install_dir/<new_exe_name> を起動
      5. .old フォルダ削除 (失敗しても黙る)

    各ステップは スクリプトと同じフォルダの `updater.log` に追記する。

    **なぜ cmd バッチでなく PowerShell か** (2026-06-04 ADR-36): cmd バッチを
    DETACHED_PROCESS (コンソールなし) で起動すると `tasklist | findstr` パイプが
    デッドロックしてハングし、`timeout`/`ping` 等のコンソール依存コマンドも不安定
    だった (実機で再起動後ハング)。PowerShell の Get-Process / Expand-Archive /
    Start-Process はコンソール非依存で、`CREATE_NO_WINDOW` (隠しコンソール) 起動で
    確実に完走する (実機検証済)。呼び出し側は update_banner が CREATE_NO_WINDOW で起動。
    """
    if script_path is None:
        script_path = zip_path.with_name("apply_update.ps1")
    install_dir = install_dir.resolve()
    zip_path = zip_path.resolve()
    old_dir = install_dir.with_name(install_dir.name + ".old")
    new_exe = install_dir / new_exe_name
    # Get-Process は .exe を除いた名前を取る (k-file.exe → "k-file")
    proc_base = new_exe_name[:-4] if new_exe_name.lower().endswith(".exe") else new_exe_name

    q_install = _ps_quote(str(install_dir))
    q_old = _ps_quote(str(old_dir))
    q_zip = _ps_quote(str(zip_path))
    q_exe = _ps_quote(str(new_exe))
    q_install_leaf = _ps_quote(install_dir.name)
    q_old_leaf = _ps_quote(old_dir.name)
    q_proc = _ps_quote(proc_base)

    lines = [
        "$ErrorActionPreference = 'Continue'",
        "$log = Join-Path $PSScriptRoot 'updater.log'",
        "function Log($m) {",
        '  "$(Get-Date -Format o) $m" | Out-File -FilePath $log -Append -Encoding utf8',
        "}",
        f"$install = {q_install}",
        f"$old = {q_old}",
        f"$zip = {q_zip}",
        f"$exe = {q_exe}",
        "Log 'updater start'",
        # k-file が終了するまで最大 30 秒待つ (Get-Process でポーリング)
        "$deadline = (Get-Date).AddSeconds(30)",
        f"while ((Get-Process -Name {q_proc} -ErrorAction SilentlyContinue) "
        "-and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 400 }",
        "Log 'wait done'",
        # 前回の .old が残っていれば掃除 → 現フォルダを .old にリネーム
        "try {",
        "  if (Test-Path -LiteralPath $old) { "
        "Remove-Item -LiteralPath $old -Recurse -Force }",
        f"  Rename-Item -LiteralPath $install -NewName {q_old_leaf} -ErrorAction Stop",
        "} catch {",
        '  Log "ERROR rename failed: $_"',
        # フォルダ無傷 → 旧版を起動し直してユーザーを取り残さない
        "  Start-Process -FilePath $exe",
        "  exit",
        "}",
        # zip を install_dir に展開 (CI は dist/k-file/* を直に zip 化)
        "try {",
        "  Expand-Archive -LiteralPath $zip -DestinationPath $install -Force "
        "-ErrorAction Stop",
        "} catch {",
        '  Log "ERROR expand: $_"',
        "}",
        # 新 exe が無ければ展開失敗 → .old を元名に戻してロールバック
        "if (-not (Test-Path -LiteralPath $exe)) {",
        "  Log 'expand failed, rolling back'",
        "  if (Test-Path -LiteralPath $install) { "
        "Remove-Item -LiteralPath $install -Recurse -Force }",
        f"  Rename-Item -LiteralPath $old -NewName {q_install_leaf}",
        "  Start-Process -FilePath $exe",
        "  exit",
        "}",
        "Log 'update applied OK'",
        "Start-Process -FilePath $exe",
        "Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue",
        "Log 'updater end'",
    ]
    script_path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 BOM 付きで書く (Windows PowerShell 5.1 が非 ASCII パスを正しく読むため)
    script_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig")
    return script_path


def install_dir_from_exe() -> Path | None:
    """PyInstaller --onedir で立ち上がった時の install_dir (= k-file.exe の親)。

    開発実行 (`python -m src.main`) では `sys.frozen` が無いので None。
    自動アップデート機構は --onedir 配布時のみ作動。
    """
    if not getattr(sys, "frozen", False):
        return None
    # sys.executable は dist/k-file/k-file.exe のフルパス
    return Path(sys.executable).parent
