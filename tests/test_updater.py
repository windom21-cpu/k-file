"""updater.py の HTTP 切り離し可能な部分の単体テスト。

GitHub API への実通信は行わず、urllib.request.urlopen を monkey-patch。
バッチ書き出しは実ファイル生成して中身を文字列でアサート。
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.updater import (
    ASSET_NAME,
    ReleaseInfo,
    fetch_latest_release,
    find_newer_release,
    parse_sha256_text,
    pick_sha256_asset,
    pick_zip_asset,
    sha256_of_file,
    write_updater_script,
)


# ───────── pick_zip_asset ─────────


def test_pick_zip_asset_exact_name():
    assets = [
        {"name": "k-file-windows.zip", "browser_download_url": "https://x/zip"},
        {"name": "source.tar.gz", "browser_download_url": "https://x/tgz"},
    ]
    a = pick_zip_asset(assets)
    assert a is not None
    assert a["name"] == ASSET_NAME


def test_pick_zip_asset_fallback_any_zip():
    assets = [
        {"name": "k-file-vNEXT.zip", "browser_download_url": "https://x/zip"},
        {"name": "README.md", "browser_download_url": "https://x/md"},
    ]
    a = pick_zip_asset(assets)
    assert a is not None
    assert a["name"].endswith(".zip")


def test_pick_zip_asset_none():
    assert pick_zip_asset([]) is None
    assert pick_zip_asset([{"name": "x.tar"}]) is None
    assert pick_zip_asset(None) is None  # type: ignore[arg-type]


# ───────── fetch_latest_release ─────────


def _fake_release(tag, prerelease=False, asset_name=ASSET_NAME):
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": False,
        "published_at": "2026-05-27T00:00:00Z",
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": f"https://example.com/{asset_name}",
                "size": 12345,
            }
        ],
    }


def _mock_urlopen(payload: object):
    """`urllib.request.urlopen` の戻りを差し替える context manager."""
    raw = json.dumps(payload).encode("utf-8")

    class _Fake:
        def __enter__(self):
            return io.BytesIO(raw)

        def __exit__(self, *_args):
            return False

    return _Fake()


def test_fetch_latest_release_picks_first_with_zip():
    payload = [
        _fake_release("v0.2.0-beta.1", prerelease=True),
        _fake_release("v0.1.0", prerelease=False),
    ]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        rel = fetch_latest_release()
    assert rel is not None
    assert rel.tag == "v0.2.0-beta.1"
    assert rel.version == "0.2.0-beta.1"
    assert rel.prerelease is True
    assert rel.asset_name == ASSET_NAME
    assert rel.asset_size == 12345


def test_fetch_latest_release_skips_release_without_zip():
    payload = [
        {
            "tag_name": "v0.3.0",
            "prerelease": False,
            "draft": False,
            "published_at": "2026-05-28T00:00:00Z",
            "assets": [{"name": "README.md"}],
        },
        _fake_release("v0.1.0"),
    ]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        rel = fetch_latest_release()
    assert rel is not None
    assert rel.tag == "v0.1.0"


def test_fetch_latest_release_returns_none_on_empty():
    with patch("urllib.request.urlopen", return_value=_mock_urlopen([])):
        assert fetch_latest_release() is None


def test_fetch_latest_release_returns_none_on_network_error():
    def _raise(*_a, **_kw):
        raise OSError("no network")

    with patch("urllib.request.urlopen", side_effect=_raise):
        assert fetch_latest_release() is None


def test_find_newer_release_when_remote_is_newer():
    payload = [_fake_release("v0.1.0-beta.2")]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        rel = find_newer_release(local_version="0.1.0-beta.1")
    assert rel is not None
    assert rel.version == "0.1.0-beta.2"


def test_find_newer_release_when_remote_is_same():
    payload = [_fake_release("v0.1.0-beta.1")]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        rel = find_newer_release(local_version="0.1.0-beta.1")
    assert rel is None


def test_find_newer_release_when_remote_is_older():
    payload = [_fake_release("v0.0.9")]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        rel = find_newer_release(local_version="0.1.0-beta.1")
    assert rel is None


# ───────── write_updater_script ─────────


def test_write_updater_script_creates_file(tmp_path: Path):
    install_dir = tmp_path / "k-file"
    install_dir.mkdir()
    zip_path = tmp_path / "k-file-windows.zip"
    zip_path.write_bytes(b"PK\x03\x04")

    script = write_updater_script(install_dir, zip_path)
    assert script.exists()
    assert script.name == "apply_update.ps1"
    content = script.read_text(encoding="utf-8-sig")
    # 主要要素 (PowerShell コマンド + パス) が含まれていること
    assert "Expand-Archive" in content
    assert "Start-Process" in content
    assert str(install_dir) in content
    assert str(zip_path) in content
    # CRLF + UTF-8 BOM (Windows PowerShell 5.1 が非 ASCII パスを読むため)
    raw = script.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw

    # ── ハング/無反応バグ修正の回帰ガード (ADR-36) ──
    # ① cmd の tasklist|findstr パイプ・ping・timeout を使わない
    #    (DETACHED コンソールなしで不安定/ハングするため)
    assert "tasklist" not in content
    assert "ping " not in content
    assert "timeout " not in content
    # ② プロセス終了待ちは Get-Process でポーリング
    assert "Get-Process" in content
    # ③ rename 失敗 / 展開失敗ロールバック / 診断ログ
    assert "rename failed" in content
    assert "rolling back" in content
    assert "updater.log" in content


def test_write_updater_script_custom_path(tmp_path: Path):
    install_dir = tmp_path / "k-file"
    install_dir.mkdir()
    zip_path = tmp_path / "k-file-windows.zip"
    zip_path.write_bytes(b"x")
    custom = tmp_path / "custom_dir" / "apply.ps1"

    script = write_updater_script(install_dir, zip_path, script_path=custom)
    assert script == custom
    assert script.exists()


def test_write_updater_script_quotes_paths_with_apostrophe(tmp_path: Path):
    # パスに ' が含まれても PowerShell リテラルが壊れないこと ('' エスケープ)
    install_dir = tmp_path / "o'brien-k-file"
    install_dir.mkdir()
    zip_path = tmp_path / "k-file-windows.zip"
    zip_path.write_bytes(b"x")

    script = write_updater_script(install_dir, zip_path)
    content = script.read_text(encoding="utf-8-sig")
    assert "o''brien-k-file" in content


# ───────── SHA256 整合性検証 (通信破損への保険) ─────────


def test_pick_sha256_asset_exact_name():
    assets = [
        {"name": ASSET_NAME, "browser_download_url": "https://x/zip"},
        {
            "name": ASSET_NAME + ".sha256",
            "browser_download_url": "https://x/sha",
        },
    ]
    a = pick_sha256_asset(assets, ASSET_NAME)
    assert a is not None
    assert a["name"] == ASSET_NAME + ".sha256"


def test_pick_sha256_asset_fallback_any_sha256():
    assets = [
        {"name": "other.zip.sha256", "browser_download_url": "https://x/sha"},
    ]
    a = pick_sha256_asset(assets, ASSET_NAME)
    assert a is not None
    assert a["name"].endswith(".sha256")


def test_pick_sha256_asset_none_when_absent():
    assets = [{"name": ASSET_NAME, "browser_download_url": "https://x/zip"}]
    assert pick_sha256_asset(assets, ASSET_NAME) is None
    assert pick_sha256_asset([], ASSET_NAME) is None
    assert pick_sha256_asset(None, ASSET_NAME) is None  # type: ignore[arg-type]


def test_sha256_of_file_known_value(tmp_path: Path):
    f = tmp_path / "blob.bin"
    f.write_bytes(b"abc")
    # 既知の SHA256("abc")
    assert sha256_of_file(f) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_parse_sha256_text_plain():
    h = "a" * 64
    assert parse_sha256_text(h) == h


def test_parse_sha256_text_sha256sum_format():
    h = "b" * 64
    assert parse_sha256_text(f"{h}  k-file-windows.zip\n") == h


def test_parse_sha256_text_uppercase_and_prefix():
    h = "C" * 64
    assert parse_sha256_text(f"SHA256(k-file-windows.zip)= {h}") == h.lower()


def test_parse_sha256_text_none_when_missing():
    assert parse_sha256_text("") is None
    assert parse_sha256_text("no hash here") is None
    assert parse_sha256_text("deadbeef") is None  # 64 桁未満


def _fake_release_with_sha(tag, asset_name=ASSET_NAME):
    rel = _fake_release(tag)
    rel["assets"].append(
        {
            "name": asset_name + ".sha256",
            "browser_download_url": f"https://example.com/{asset_name}.sha256",
            "size": 70,
        }
    )
    return rel


def test_fetch_latest_release_populates_sha256_url():
    payload = [_fake_release_with_sha("v0.1.0-beta.12")]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        rel = fetch_latest_release()
    assert rel is not None
    assert rel.sha256_url == f"https://example.com/{ASSET_NAME}.sha256"


def test_fetch_latest_release_sha256_url_none_when_absent():
    # サイドカーが無い旧 Release では None (= 照合スキップで後方互換)
    payload = [_fake_release("v0.1.0-beta.1")]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
        rel = fetch_latest_release()
    assert rel is not None
    assert rel.sha256_url is None
