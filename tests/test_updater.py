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
    pick_zip_asset,
    write_updater_batch,
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


# ───────── write_updater_batch ─────────


def test_write_updater_batch_creates_file(tmp_path: Path):
    install_dir = tmp_path / "k-file"
    install_dir.mkdir()
    zip_path = tmp_path / "k-file-windows.zip"
    zip_path.write_bytes(b"PK\x03\x04")

    batch = write_updater_batch(install_dir, zip_path)
    assert batch.exists()
    content = batch.read_text(encoding="cp932")
    # 主要要素が含まれていること
    assert "tasklist" in content
    assert "k-file.exe" in content
    assert "Expand-Archive" in content
    assert str(install_dir) in content
    assert str(zip_path) in content
    # CRLF 改行 (Windows バッチ用)
    assert "\r\n" in batch.read_bytes().decode("cp932")


def test_write_updater_batch_custom_path(tmp_path: Path):
    install_dir = tmp_path / "k-file"
    install_dir.mkdir()
    zip_path = tmp_path / "k-file-windows.zip"
    zip_path.write_bytes(b"x")
    custom = tmp_path / "custom_dir" / "apply.bat"

    batch = write_updater_batch(install_dir, zip_path, batch_path=custom)
    assert batch == custom
    assert batch.exists()
