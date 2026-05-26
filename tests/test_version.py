"""SemVer ライクなバージョン比較のテスト。"""

from __future__ import annotations

import pytest

from src.core.version import compare_versions, is_newer, parse_version


@pytest.mark.parametrize(
    "s,expected_nums,expected_pre",
    [
        ("0.1.0", (0, 1, 0), None),
        ("v0.1.0", (0, 1, 0), None),
        ("V0.1.0", (0, 1, 0), None),
        ("0.1.0-beta.1", (0, 1, 0), ["beta", 1]),
        ("v0.1.0-beta.1", (0, 1, 0), ["beta", 1]),
        ("1.0.0-alpha.10", (1, 0, 0), ["alpha", 10]),
        ("0.1.0-rc.1", (0, 1, 0), ["rc", 1]),
    ],
)
def test_parse_version(s, expected_nums, expected_pre):
    nums, pre = parse_version(s)
    assert nums == expected_nums
    assert pre == expected_pre


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("0.1.0", "0.0.9", 1),
        ("0.0.9", "0.1.0", -1),
        ("0.1.0", "0.1.0", 0),
        # stable vs prerelease (同じ数値)
        ("0.1.0", "0.1.0-beta.1", 1),
        ("0.1.0-beta.1", "0.1.0", -1),
        # prerelease 同士: 数字
        ("0.1.0-beta.2", "0.1.0-beta.1", 1),
        ("0.1.0-beta.10", "0.1.0-beta.2", 1),
        # prerelease 同士: 文字列 (alpha < beta < rc は alphabetical で動く)
        ("0.1.0-beta.1", "0.1.0-alpha.5", 1),
        ("0.1.0-rc.1", "0.1.0-beta.10", 1),
        # 数値部優先 (prerelease あり vs stable)
        ("0.2.0-beta.1", "0.1.0", 1),
        ("0.1.1", "0.1.0-beta.1", 1),
        # v 接頭辞許容
        ("v0.1.0", "v0.0.9", 1),
        ("v0.1.0-beta.1", "0.0.9", 1),
    ],
)
def test_compare_versions(a, b, expected):
    assert compare_versions(a, b) == expected


def test_is_newer_basic():
    assert is_newer("0.1.0", "0.0.9") is True
    assert is_newer("0.0.9", "0.1.0") is False
    assert is_newer("0.1.0", "0.1.0") is False


def test_is_newer_prerelease():
    # 同じ数値で remote が stable, local が beta → 更新あり
    assert is_newer("0.1.0", "0.1.0-beta.1") is True
    # 同じ数値で remote が beta, local が stable → 更新なし (downgrade)
    assert is_newer("0.1.0-beta.1", "0.1.0") is False


def test_is_newer_dev_to_beta():
    # 開発中 "0.1.0-dev" は実質 alpha 扱い → beta タグの方が新しい
    assert is_newer("0.1.0-beta.1", "0.1.0-dev") is True
