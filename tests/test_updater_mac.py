"""macOS 自動アップデート (.app 差し替え型 updater) の単体テスト。

Mac 実機がなくても壊れに気づけるよう、生成した sh スクリプトを **実際に走らせて**
検証する。macOS 専用コマンド (ditto / open / xattr) は PATH 先頭に置いた偽物に
差し替え、「展開 → 旧バンドル退避 → 新バンドル設置 → 起動 → 後始末」と、失敗時の
ロールバックが本当に起きるかを確かめる。

Windows では /bin/sh が無いので skip (CI の test ジョブは ubuntu なので必ず走る)。
"""
from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from src.core.updater import (
    ASSET_NAME_MACOS,
    ASSET_NAME_WINDOWS,
    fetch_latest_release,
    pick_sha256_asset,
    pick_zip_asset,
    platform_asset_name,
    write_mac_relaunch_script,
    write_mac_updater_script,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="/bin/sh が無い環境ではスクリプトを実行できない"
)


# ───────── OS ごとの asset 選択 ─────────


def test_platform_asset_name_per_os():
    assert platform_asset_name("win32") == ASSET_NAME_WINDOWS
    assert platform_asset_name("darwin") == ASSET_NAME_MACOS
    assert platform_asset_name("linux") is None


def test_pick_zip_asset_takes_the_asked_platform():
    """Release には Win/Mac 両方の zip が載る。取り違えたら別 OS のビルドが入る。"""
    assets = [
        {"name": ASSET_NAME_WINDOWS, "browser_download_url": "https://x/win"},
        {"name": ASSET_NAME_MACOS, "browser_download_url": "https://x/mac"},
    ]
    mac = pick_zip_asset(assets, asset_name=ASSET_NAME_MACOS)
    win = pick_zip_asset(assets, asset_name=ASSET_NAME_WINDOWS)
    assert mac is not None and mac["browser_download_url"] == "https://x/mac"
    assert win is not None and win["browser_download_url"] == "https://x/win"


def test_pick_zip_asset_never_falls_back_to_other_platform():
    """欲しい zip が無いとき、他 OS の zip を掴むくらいなら None を返す。"""
    assets = [{"name": ASSET_NAME_WINDOWS, "browser_download_url": "https://x/win"}]
    assert pick_zip_asset(assets, asset_name=ASSET_NAME_MACOS) is None


def test_pick_sha256_asset_ignores_other_platform_sidecar():
    """他 OS のハッシュを掴むと必ず不一致 → fail-closed で更新が止まってしまう。"""
    assets = [
        {"name": ASSET_NAME_MACOS, "browser_download_url": "https://x/mac"},
        {
            "name": ASSET_NAME_WINDOWS + ".sha256",
            "browser_download_url": "https://x/winsha",
        },
    ]
    assert pick_sha256_asset(assets, ASSET_NAME_MACOS) is None


def test_fetch_latest_release_picks_mac_assets(monkeypatch):
    release = {
        "tag_name": "v9.9.9",
        "prerelease": False,
        "published_at": "2026-07-15T00:00:00Z",
        "assets": [
            {
                "name": ASSET_NAME_WINDOWS,
                "browser_download_url": "https://x/win",
                "size": 1,
            },
            {
                "name": ASSET_NAME_WINDOWS + ".sha256",
                "browser_download_url": "https://x/winsha",
                "size": 1,
            },
            {
                "name": ASSET_NAME_MACOS,
                "browser_download_url": "https://x/mac",
                "size": 2,
            },
            {
                "name": ASSET_NAME_MACOS + ".sha256",
                "browser_download_url": "https://x/macsha",
                "size": 1,
            },
        ],
    }
    monkeypatch.setattr(
        "src.core.updater.urllib.request.urlopen",
        lambda *a, **k: _FakeResp([release]),
    )
    rel = fetch_latest_release(asset_name=ASSET_NAME_MACOS)
    assert rel is not None
    assert rel.asset_name == ASSET_NAME_MACOS
    assert rel.download_url == "https://x/mac"
    assert rel.sha256_url == "https://x/macsha"      # Win 版のハッシュを掴まない


class _FakeResp:
    """urlopen の context manager をまねる最小のダミー。"""

    def __init__(self, payload) -> None:
        import json

        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


# ───────── sh スクリプトを実際に走らせる ─────────


def _fake_mac_commands(bin_dir: Path, *, ditto_fails: bool = False) -> None:
    """macOS 専用コマンドの偽物を bin_dir に置く。

    ditto  … zip 展開 (Linux の unzip で代用 / ditto_fails=True なら失敗を返す)
    open   … 起動した .app のパスを opened.log に追記するだけ
    xattr  … 何もしない (検疫属性の削除は Linux で再現しようがない)
    """
    ditto_body = (
        "#!/bin/sh\nexit 3\n" if ditto_fails
        # 実物は `ditto -x -k <zip> <dst>`。$3=zip $4=dst
        else '#!/bin/sh\nmkdir -p "$4" && cd "$4" && unzip -q -o "$3"\n'
    )
    (bin_dir / "ditto").write_text(ditto_body)
    (bin_dir / "open").write_text(
        '#!/bin/sh\n[ "$1" = "-n" ] && shift\n'
        f'echo "$1" >> {bin_dir / "opened.log"}\n'
    )
    (bin_dir / "xattr").write_text("#!/bin/sh\nexit 0\n")
    for name in ("ditto", "open", "xattr"):
        (bin_dir / name).chmod(0o755)


def _make_bundle(path: Path, marker: str) -> None:
    """`k-file.app` の最小の似姿 (中身の marker で新旧を見分ける)。"""
    (path / "Contents" / "MacOS").mkdir(parents=True)
    (path / "Contents" / "MacOS" / "k-file").write_text(marker)


def _run_script(script: Path, bin_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    return subprocess.run(
        ["/bin/sh", str(script)], env=env, capture_output=True, timeout=60
    )


@pytest.fixture
def mac_env(tmp_path: Path):
    """`~/Applications/k-file.app` 相当 + DL 済み zip + 偽コマンド一式。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    apps = tmp_path / "Applications"
    apps.mkdir()
    bundle = apps / "k-file.app"
    _make_bundle(bundle, "OLD VERSION")

    # CI が作る k-file-macos.zip 相当 (中身は新版バンドル)
    updates = tmp_path / "updates"
    updates.mkdir()
    new_src = tmp_path / "src_new" / "k-file.app"
    _make_bundle(new_src, "NEW VERSION")
    zip_path = updates / ASSET_NAME_MACOS
    with zipfile.ZipFile(zip_path, "w") as zf:
        for p in sorted(new_src.rglob("*")):
            if p.is_file():
                zf.write(p, str(Path("k-file.app") / p.relative_to(new_src)))
    return {
        "bin": bin_dir,
        "bundle": bundle,
        "zip": zip_path,
        "opened_log": bin_dir / "opened.log",
    }


def test_mac_updater_replaces_bundle_and_relaunches(mac_env):
    """正常系: 新版に差し替わり、新版が起動され、後始末される。"""
    _fake_mac_commands(mac_env["bin"])
    bundle: Path = mac_env["bundle"]
    # 終了済みプロセスの PID を渡す (= k-file がもう閉じた状態から始める)
    dead = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
    dead.wait()
    script = write_mac_updater_script(bundle, mac_env["zip"], pid=dead.pid)

    res = _run_script(script, mac_env["bin"])
    assert res.returncode == 0, res.stderr

    exe = bundle / "Contents" / "MacOS" / "k-file"
    assert exe.read_text() == "NEW VERSION"          # 差し替わった
    assert not bundle.with_name("k-file.app.old").exists()   # 旧版は掃除された
    assert mac_env["opened_log"].read_text().strip() == str(bundle)  # 起動された
    log = (script.parent / "updater.log").read_text()
    assert "update applied OK" in log


def test_mac_updater_rolls_back_and_reopens_old_when_extract_fails(mac_env):
    """異常系: 展開に失敗しても旧版を残して起動し直す (ユーザーを取り残さない)。"""
    _fake_mac_commands(mac_env["bin"], ditto_fails=True)
    bundle: Path = mac_env["bundle"]
    dead = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
    dead.wait()
    script = write_mac_updater_script(bundle, mac_env["zip"], pid=dead.pid)

    res = _run_script(script, mac_env["bin"])
    assert res.returncode == 1

    exe = bundle / "Contents" / "MacOS" / "k-file"
    assert exe.read_text() == "OLD VERSION"          # 旧版が無傷で残る
    assert mac_env["opened_log"].read_text().strip() == str(bundle)  # 起動し直した
    assert "ERROR ditto failed" in (script.parent / "updater.log").read_text()


def test_mac_updater_waits_for_the_app_to_quit(mac_env, tmp_path: Path):
    """起動中の k-file が終わるまで差し替えを始めない (使用中のバンドルを壊さない)。"""
    _fake_mac_commands(mac_env["bin"])
    bundle: Path = mac_env["bundle"]
    victim = subprocess.Popen(["/bin/sh", "-c", "sleep 1.5"])
    script = write_mac_updater_script(bundle, mac_env["zip"], pid=victim.pid)

    proc = subprocess.Popen(
        ["/bin/sh", str(script)],
        env=dict(os.environ, PATH=f"{mac_env['bin']}:{os.environ['PATH']}"),
    )
    # k-file (victim) がまだ生きている間は旧版のまま
    exe = bundle / "Contents" / "MacOS" / "k-file"
    assert exe.read_text() == "OLD VERSION"

    victim.wait()
    proc.wait(timeout=30)
    assert exe.read_text() == "NEW VERSION"          # 終了後に差し替わる


def test_mac_updater_script_quotes_paths_with_apostrophe(tmp_path: Path):
    """アポストロフィ入りのパス (`Sam's Mac`) でもスクリプトが壊れない。"""
    apps = tmp_path / "Sam's Apps"
    apps.mkdir()
    bundle = apps / "k-file.app"
    _make_bundle(bundle, "OLD")
    zip_path = tmp_path / ASSET_NAME_MACOS
    zip_path.write_bytes(b"dummy")
    script = write_mac_updater_script(bundle, zip_path, pid=os.getpid())
    # sh -n = 構文チェックのみ (実行しない)
    res = subprocess.run(["/bin/sh", "-n", str(script)], capture_output=True)
    assert res.returncode == 0, res.stderr


def test_mac_relaunch_script_reopens_the_bundle(mac_env):
    """表示倍率変更後の自動再起動 (Mac 版) も同じ待ち方で動く。"""
    _fake_mac_commands(mac_env["bin"])
    bundle: Path = mac_env["bundle"]
    dead = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
    dead.wait()
    script = write_mac_relaunch_script(
        bundle, pid=dead.pid, script_path=mac_env["bin"].parent / "relaunch.sh"
    )
    res = _run_script(script, mac_env["bin"])
    assert res.returncode == 0, res.stderr
    assert mac_env["opened_log"].read_text().strip() == str(bundle)
    # 再起動は差し替えを伴わない
    assert (bundle / "Contents" / "MacOS" / "k-file").read_text() == "OLD VERSION"
