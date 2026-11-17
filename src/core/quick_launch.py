"""クイック起動フォルダ (ファンクションキー 1 発で開く常用フォルダ) の定義と永続化。

登録は「表示名 + フォルダ」の並び順つきリスト。並び順がそのままキー割当になる:

    1〜4 件目   F6 / F7 / F8 / F9          (素のキー、バーの中央に固まる)
    5〜8 件目   Shift+F6 〜 Shift+F9       (同じ位置の 2 段目)
    9 件目以降  Shift+F1 / F3 / F4 / F5 / F11 / F12

素の F1 は「ごみ箱を開く」、F11 は「削除」に充てている (MainWindow)。

Shift+F2 (事件フォルダ名変更) と Shift+F10 (Windows 標準のコンテキストメニュー)
は既に意味があるので割り当てない。

保存先は `kfile.db.settings` の `quick_folders_json`。v1.2.2 までの 2 枠固定
(`quick_notes_path` = F6 雑記録 / `quick_temp_path` = F7 一時保管) は、新キーが
まだ無い時に限り読み替えて引き継ぐ (旧キーは消さない = 旧版へ戻しても壊れない)。
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

KEY_QUICK_FOLDERS = "quick_folders_json"
# v1.2.2 までの旧キー (移行元としてのみ参照)
LEGACY_KEY_NOTES = "quick_notes_path"
LEGACY_KEY_TEMP = "quick_temp_path"

# (ファンクションキー番号, Shift 併用か) — 並び順 = 割当順
SLOTS: tuple[tuple[int, bool], ...] = (
    (6, False), (7, False), (8, False), (9, False),
    (6, True), (7, True), (8, True), (9, True),
    (1, True), (3, True), (4, True), (5, True), (11, True), (12, True),
)
MAX_QUICK_FOLDERS = len(SLOTS)


@dataclass(frozen=True)
class QuickFolder:
    label: str
    path: str  # 空文字 = 未設定 (セルは枠だけ出して無効表示)


def slot_name(index: int) -> str:
    """`index` 件目 (0 始まり) に割り当たるキー名。例: 'F6' / 'Shift+F6'。"""
    fn, shift = SLOTS[index]
    return f"Shift+F{fn}" if shift else f"F{fn}"


def load_quick_folders(
    get_setting: Callable[[str, str], str | None],
) -> list[QuickFolder]:
    """設定からクイック起動リストを復元。新キーが無ければ旧 2 枠を読み替える。"""
    raw = get_setting(KEY_QUICK_FOLDERS, "") or ""
    if raw:
        try:
            data = json.loads(raw)
            out = [
                QuickFolder(
                    label=str(d.get("label", "")).strip(),
                    path=str(d.get("path", "")).strip(),
                )
                for d in data
                if isinstance(d, dict)
            ]
            return [q for q in out if q.label or q.path][:MAX_QUICK_FOLDERS]
        except (ValueError, TypeError, AttributeError):
            pass  # 壊れた JSON は旧キーからの復元にフォールバック
    # 旧 2 枠: パス未設定でも枠 (表示名) は残し、F6 / F7 の位置関係を保つ
    return [
        QuickFolder("雑記録", (get_setting(LEGACY_KEY_NOTES, "") or "").strip()),
        QuickFolder("一時保管", (get_setting(LEGACY_KEY_TEMP, "") or "").strip()),
    ]


def save_quick_folders(
    set_setting: Callable[[str, str], None],
    folders: list[QuickFolder],
) -> None:
    data = [
        {"label": q.label, "path": q.path}
        for q in folders[:MAX_QUICK_FOLDERS]
    ]
    set_setting(KEY_QUICK_FOLDERS, json.dumps(data, ensure_ascii=False))
