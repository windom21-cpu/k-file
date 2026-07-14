"""事件フォルダ名 → (case_code, タブ表示名) の解析 (_parse_case / _tab_label)。

macOS はファイル名を NFD (濁点分解) で返すことがあり、NFC のリテラル
"文書フォルダ" と一致せず解析が丸ごと失敗する → タブラベルが空文字になり
「どの事件を開いているのか分からない」状態になっていた (2026-07-15、Mac 実機)。
NFD 名でも Windows と同じ結果になること、および解析に失敗しても空タブには
ならないことを固定する。
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from src.ui.case_pane import _parse_case, _tab_label

# 実環境の現行命名規則。macOS の readdir はこれを NFD で返しうる
NFC_NAME = "R08020011文書フォルダ(田中太郎)売買"
NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)


def test_nfc_name_parses() -> None:
    code, name = _parse_case(Path("/docs") / NFC_NAME)
    assert code == "R08020011"
    assert name == "田中太郎 売買"


def test_nfd_name_parses_identically() -> None:
    """macOS 由来の分解済み名でも Windows と同一の結果になる。"""
    assert NFD_NAME != NFC_NAME          # 前提: 2 つは別の文字列
    code, name = _parse_case(Path("/docs") / NFD_NAME)
    assert code == "R08020011"
    assert name == "田中太郎 売買"


def test_nfd_name_gives_non_empty_tab_label() -> None:
    """回帰: Mac で空タブになっていた経路。"""
    assert _tab_label(*_parse_case(Path("/docs") / NFD_NAME)) == "田中太郎 売買"


def test_legacy_space_separated_name() -> None:
    code, name = _parse_case(Path("/docs/R060200042 山田太郎 損害賠償"))
    assert code == "R060200042"
    assert name == "山田太郎 損害賠償"


def test_unknown_naming_never_yields_empty_tab() -> None:
    """命名規則から外れたフォルダでも「文字のないタブ」にしない。"""
    code, name = _parse_case(Path("/docs/雑フォルダ"))
    assert name == ""                    # 表示名は取れない
    assert _tab_label(code, name) == "雑フォルダ"
