"""SemVer ライクなバージョン比較。

サポート形式:
  - `0.1.0`           (stable)
  - `0.1.0-beta.1`    (prerelease)
  - `v0.1.0-beta.1`   (先頭 `v` は許容、内部で除去)

優先順位:
  0.0.9 < 0.1.0-alpha.1 < 0.1.0-alpha.2 < 0.1.0-beta.1 < 0.1.0-rc.1 < 0.1.0 < 0.1.1

採用ルール:
  - 数値部 (major.minor.patch) が異なれば数値大きい方が新しい
  - 数値部が同じなら **prerelease なし > prerelease あり**
  - prerelease 同士は要素ごとに比較 (数値 vs 文字列が混在する場合は数値が下位)
"""

from __future__ import annotations


def _strip_v(s: str) -> str:
    return s[1:] if s.startswith("v") or s.startswith("V") else s


def parse_version(s: str) -> tuple[tuple[int, ...], list | None]:
    """`0.1.0-beta.1` → ((0, 1, 0), ['beta', 1])。stable は pre が None。

    数値変換できないトークンは文字列のまま保持 (例: 'beta', 'rc')。
    数字のみのトークンは int 化 (例: 1, 2)。
    """
    s = _strip_v(s.strip())
    if "-" in s:
        base, pre = s.split("-", 1)
        pre_parts: list = []
        for p in pre.split("."):
            pre_parts.append(int(p) if p.isdigit() else p)
    else:
        base = s
        pre_parts = None
    try:
        nums = tuple(int(x) for x in base.split("."))
    except ValueError:
        nums = (0,)
    return nums, pre_parts


def _pre_key(pre: list) -> list:
    """prerelease 要素を tuple sort 用のキーに変換。

    `(-1, 0, "")` = "dev" (リポジトリ内開発中マーカ、alpha より下)
    `(0, n, "")` = 数値 (数値同士で n を比較、文字列より下位)
    `(1, 0, s)` = 文字列 (文字列同士で s を比較、数値より上位)
    SemVer 仕様「Numeric identifiers have lower precedence than alphanumeric」に従う。
    "dev" だけは特例で alpha/beta/rc より下に置く (開発ビルド → リリース版で
    更新検知させるため)。
    """
    out = []
    for p in pre:
        if isinstance(p, int):
            out.append((0, p, ""))
        elif p == "dev":
            out.append((-1, 0, ""))
        else:
            out.append((1, 0, p))
    return out


def compare_versions(a: str, b: str) -> int:
    """-1 if a < b, 0 if equal, 1 if a > b."""
    a_nums, a_pre = parse_version(a)
    b_nums, b_pre = parse_version(b)
    if a_nums != b_nums:
        return 1 if a_nums > b_nums else -1
    # 数値部が同じ: stable (= pre なし) は prerelease より新しい
    if a_pre is None and b_pre is None:
        return 0
    if a_pre is None:
        return 1
    if b_pre is None:
        return -1
    a_key = _pre_key(a_pre)
    b_key = _pre_key(b_pre)
    if a_key == b_key:
        return 0
    return 1 if a_key > b_key else -1


def is_newer(remote: str, local: str) -> bool:
    """remote が local より新しければ True (= 更新あり)。"""
    return compare_versions(remote, local) > 0
