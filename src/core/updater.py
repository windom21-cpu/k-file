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
ASSET_NAME = "k-file-windows.zip"          # 後方互換のため名前は据え置き
ASSET_NAME_WINDOWS = ASSET_NAME
ASSET_NAME_MACOS = "k-file-macos.zip"
# 「別プラットフォーム向けの asset」集合。fallback で誤って掴まないための除外リスト
# (Mac に Windows 版 zip を入れてしまう事故を構造的に防ぐ)
_PLATFORM_ASSETS = {ASSET_NAME_WINDOWS, ASSET_NAME_MACOS}
# zip の SHA256 を載せたサイドカー asset の拡張子 (= "<zip 名>.sha256")
SHA256_ASSET_SUFFIX = ".sha256"


def platform_asset_name(platform: str | None = None) -> str | None:
    """この OS が DL すべき Release asset 名。対応外 OS (Linux dev) は None。"""
    plat = platform if platform is not None else sys.platform
    if plat == "win32":
        return ASSET_NAME_WINDOWS
    if plat == "darwin":
        return ASSET_NAME_MACOS
    return None


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
    asset_name: str | None = None,
) -> ReleaseInfo | None:
    """GitHub Releases API を叩いて「最新の zip asset を持つ release」を返す。

    最新判定は `published_at` 降順の先頭。prerelease (β タグ等) も含む — 後段の
    is_newer 比較で local 版より新しいかを最終判定する。

    通信失敗 (タイムアウト / オフライン / 403 rate limit 等) は **None を返す**
    (= 「黙って何もしない」)。起動時に毎回呼ぶので例外で落とさない。

    asset_name: 掴む zip の名前。既定は実行中 OS 用 (Win → k-file-windows.zip /
    Mac → k-file-macos.zip)。Release には両方が載るので、ここを間違えると別 OS の
    ビルドを掴む。
    """
    if asset_name is None:
        asset_name = platform_asset_name() or ASSET_NAME
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
        asset = pick_zip_asset(assets, asset_name=asset_name)
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


def pick_zip_asset(assets: list[dict], asset_name: str = ASSET_NAME) -> dict | None:
    """Release の assets 配列から「この OS 用」の zip を 1 件選ぶ。

    優先順位:
      1. `asset_name` と完全一致 (現 CI が upload する名前)
      2. `.zip` 拡張子の最初の asset (将来名前が変わっても拾えるよう fallback)
         ただし **他 OS 向けの asset は除外** する。Release には Win/Mac 両方の zip が
         載るため、素朴に「最初の .zip」を拾うと Mac に Windows 版を入れてしまう。
    """
    if not isinstance(assets, list):
        return None
    for a in assets:
        if a.get("name") == asset_name and a.get("browser_download_url"):
            return a
    for a in assets:
        name = a.get("name")
        if (
            isinstance(name, str)
            and name.lower().endswith(".zip")
            and name not in _PLATFORM_ASSETS   # 他 OS のビルドは掴まない
            and a.get("browser_download_url")
        ):
            return a
    return None


def pick_sha256_asset(assets: list[dict], zip_name: str) -> dict | None:
    """Release の assets 配列から zip の SHA256 サイドカーを 1 件選ぶ。

    優先順位:
      1. `<zip_name>.sha256` と完全一致 (CI が upload する名前)
      2. `.sha256` 拡張子の最初の asset (fallback)。ただし **他 OS の zip に紐づく
         サイドカーは除外** する (掴むと必ず不一致 → fail-closed で更新が止まる)
    サイドカーが無い (= 旧 Release) 場合は None。照合は「あれば行う」保険扱い。
    """
    if not isinstance(assets, list):
        return None
    want = zip_name + SHA256_ASSET_SUFFIX
    others = {
        p + SHA256_ASSET_SUFFIX for p in _PLATFORM_ASSETS if p != zip_name
    }
    for a in assets:
        if a.get("name") == want and a.get("browser_download_url"):
            return a
    for a in assets:
        name = a.get("name")
        if (
            isinstance(name, str)
            and name.lower().endswith(SHA256_ASSET_SUFFIX)
            and name not in others          # 他 OS の zip のハッシュは使わない
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
    asset_name: str | None = None,
) -> ReleaseInfo | None:
    """fetch + バージョン比較を 1 関数にまとめた便利関数。
    新版が無ければ None。"""
    rel = fetch_latest_release(
        timeout=timeout, api_url=api_url, asset_name=asset_name
    )
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


def write_relaunch_script(
    install_dir: Path,
    new_exe_name: str = "k-file.exe",
    script_path: Path | None = None,
) -> Path:
    """k-file を「終了を待って起動し直す」だけの PowerShell スクリプトを書き出す。

    表示倍率 (QT_SCALE_FACTOR) のように QApplication 生成前でしか反映できない設定を
    変えた後の自動再起動用。zip 展開を伴わない点だけが write_updater_script と違う。

    単一インスタンス IPC (QLocalServer, ADR-20) と競合しないよう、**旧プロセスの消滅を
    待ってから** 起動する。待たずに起動すると新プロセスが生き残っている旧 primary に
    パスを送って自分は終了し、旧 primary も直後に閉じてウインドウが 1 つも残らない。
    write_updater_script と同じ Get-Process ポーリングで回避する。

    起動側は update_banner と同様 CREATE_NO_WINDOW (隠しコンソール) で呼ぶこと。
    """
    install_dir = install_dir.resolve()
    new_exe = install_dir / new_exe_name
    if script_path is None:
        script_path = default_updates_dir() / "relaunch.ps1"
    # Get-Process は .exe を除いた名前を取る (k-file.exe → "k-file")
    proc_base = new_exe_name[:-4] if new_exe_name.lower().endswith(".exe") else new_exe_name
    q_exe = _ps_quote(str(new_exe))
    q_proc = _ps_quote(proc_base)
    lines = [
        "$ErrorActionPreference = 'Continue'",
        f"$exe = {q_exe}",
        # 旧 k-file が終了するまで最大 30 秒待つ (IPC ロック解放待ち)
        "$deadline = (Get-Date).AddSeconds(30)",
        f"while ((Get-Process -Name {q_proc} -ErrorAction SilentlyContinue) "
        "-and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 300 }",
        "Start-Process -FilePath $exe",
    ]
    script_path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 BOM 付き (Windows PowerShell 5.1 が非 ASCII パスを正しく読むため)
    script_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig")
    return script_path


# ───────── macOS: .app バンドル差し替え型の updater ─────────
#
# Windows との違い (なぜ別実装が要るか):
#   - 配布物が「フォルダ」ではなく `k-file.app` という 1 個のバンドル
#   - 展開に `ditto` を使う (CI も `ditto -c -k` で固めている)。Python の zipfile や
#     `unzip` では実行権限・拡張属性が落ちて .app が起動しなくなる
#   - 検疫 (com.apple.quarantine) は「ブラウザ等が DL したファイル」に付く印。
#     アプリ内 DL (QNetworkAccessManager) では付かないため、手動更新で必要だった
#     `xattr -cr` が不要になる (念のためスクリプト側でも外す)
#   - プロセス終了待ちは PID を直接見る (Get-Process 相当は不要、`kill -0` で足りる)


def _sh_quote(value: str) -> str:
    """sh の単一引用符リテラルに安全に埋める。"""
    return "'" + value.replace("'", "'\\''") + "'"


def mac_bundle_from_exe() -> Path | None:
    """実行中の `k-file.app` バンドルのパス (Mac の配布版でのみ返る)。

    sys.executable は `~/Applications/k-file.app/Contents/MacOS/k-file` なので、
    `.app` で終わる祖先を探して返す。dev 実行 (`python -m src.main`) や Win/Linux
    では None。
    """
    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return None
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def write_mac_updater_script(
    bundle_path: Path,
    zip_path: Path,
    pid: int,
    script_path: Path | None = None,
) -> Path:
    """`k-file.app` を新版に差し替えて起動し直す **sh スクリプト** を書き出す。

    bundle_path: 現在の k-file.app (例: `~/Applications/k-file.app`)
    zip_path:    DL 済みの k-file-macos.zip
    pid:         今動いている k-file のプロセス ID (これが消えるまで待つ)

    動作:
      1. pid が消えるまで wait (最大 30 秒)
      2. zip を作業ディレクトリへ `ditto -x -k` で展開 (権限・署名を保つ)
      3. 旧バンドルを `.old` へ退避 → 新バンドルを本来の場所へ move
      4. 失敗したらロールバックして **旧版を起動し直す** (ユーザーを取り残さない)
      5. 検疫属性を外して `open` で新版を起動 → `.old` と作業ディレクトリを削除
    各ステップはスクリプトと同じフォルダの `updater.log` に追記する。
    """
    bundle_path = bundle_path.resolve()
    zip_path = zip_path.resolve()
    if script_path is None:
        script_path = zip_path.with_name("apply_update.sh")
    stage = zip_path.with_name("stage")
    old = bundle_path.with_name(bundle_path.name + ".old")
    new_bundle = stage / bundle_path.name

    q_bundle = _sh_quote(str(bundle_path))
    q_zip = _sh_quote(str(zip_path))
    q_stage = _sh_quote(str(stage))
    q_old = _sh_quote(str(old))
    q_new = _sh_quote(str(new_bundle))

    lines = [
        "#!/bin/sh",
        'LOG="$(dirname "$0")/updater.log"',
        'log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $1" >> "$LOG"; }',
        f"BUNDLE={q_bundle}",
        f"ZIP={q_zip}",
        f"STAGE={q_stage}",
        f"OLD={q_old}",
        f"NEW={q_new}",
        f"PID={int(pid)}",
        "log 'updater start'",
        # 1. k-file の終了待ち (最大 30 秒 = 0.3s × 100)
        "i=0",
        'while kill -0 "$PID" 2>/dev/null && [ "$i" -lt 100 ]; do',
        "  sleep 0.3",
        "  i=$((i+1))",
        "done",
        'log "wait done (i=$i)"',
        # 2. 展開 (ditto: 実行権限・拡張属性・署名を保ったまま復元)
        'rm -rf "$STAGE" "$OLD"',
        'mkdir -p "$STAGE"',
        'if ! ditto -x -k "$ZIP" "$STAGE" >>"$LOG" 2>&1; then',
        "  log 'ERROR ditto failed'",
        '  open "$BUNDLE"',       # 旧版のまま起動し直す
        "  exit 1",
        "fi",
        'if [ ! -d "$NEW" ]; then',
        "  log 'ERROR new bundle not found in zip'",
        '  open "$BUNDLE"',
        "  exit 1",
        "fi",
        # 3. 旧バンドル退避 → 新バンドル設置
        'if ! mv "$BUNDLE" "$OLD"; then',
        "  log 'ERROR cannot move old bundle (permission?)'",
        '  open "$BUNDLE"',
        "  exit 1",
        "fi",
        'if ! mv "$NEW" "$BUNDLE"; then',
        "  log 'ERROR install failed, rolling back'",
        '  mv "$OLD" "$BUNDLE"',
        '  open "$BUNDLE"',
        "  exit 1",
        "fi",
        # 4. 検疫属性を外す (アプリ内 DL では付かないはずだが念のため)
        'xattr -dr com.apple.quarantine "$BUNDLE" 2>/dev/null',
        "log 'update applied OK'",
        # 5. 新版を起動 → 後始末
        'open "$BUNDLE"',
        'rm -rf "$OLD" "$STAGE"',
        "log 'updater end'",
    ]
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def write_mac_relaunch_script(
    bundle_path: Path,
    pid: int,
    script_path: Path | None = None,
) -> Path:
    """k-file.app を「終了を待って起動し直す」だけの sh スクリプト (Mac 版)。

    表示倍率 (QT_SCALE_FACTOR) 変更後の自動再起動用 = write_relaunch_script の Mac 版。
    単一インスタンス IPC (ADR-20) と競合しないよう、旧プロセス消滅を待ってから開く。
    """
    bundle_path = bundle_path.resolve()
    if script_path is None:
        script_path = default_updates_dir() / "relaunch.sh"
    q_bundle = _sh_quote(str(bundle_path))
    lines = [
        "#!/bin/sh",
        f"BUNDLE={q_bundle}",
        f"PID={int(pid)}",
        "i=0",
        'while kill -0 "$PID" 2>/dev/null && [ "$i" -lt 100 ]; do',
        "  sleep 0.3",
        "  i=$((i+1))",
        "done",
        # -n = 新しいインスタンスを起こす (LaunchServices が「まだ起動中」と
        # 誤認して無視するのを防ぐ)
        'open -n "$BUNDLE"',
    ]
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script_path.chmod(0o755)
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
