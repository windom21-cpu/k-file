"""クイック起動フォルダ (core/quick_launch) と FunctionKeysBar の Shift 段。"""
import json

from src.core.quick_launch import (
    KEY_QUICK_FOLDERS,
    LEGACY_KEY_NOTES,
    LEGACY_KEY_TEMP,
    MAX_QUICK_FOLDERS,
    SLOTS,
    QuickFolder,
    load_quick_folders,
    save_quick_folders,
    slot_name,
)
from src.ui.function_keys_bar import FunctionKeysBar


def _store(initial=None):
    d = dict(initial or {})
    return d, (lambda k, default=None: d.get(k, default)), d.__setitem__


def test_slot_order_plain_keys_are_contiguous_then_shift():
    assert [slot_name(i) for i in range(5)] == ["F6", "F7", "F8", "F9", "Shift+F6"]
    assert (1, False) not in SLOTS  # 素の F1 = ごみ箱
    assert len(set(SLOTS)) == len(SLOTS)
    # 既に意味のある Shift+F2 / Shift+F10 には割り当てない
    assert (2, True) not in SLOTS and (10, True) not in SLOTS


def test_legacy_two_slots_are_migrated_in_place():
    _, get, _ = _store({LEGACY_KEY_NOTES: "/a/notes", LEGACY_KEY_TEMP: ""})
    assert load_quick_folders(get) == [
        QuickFolder("雑記録", "/a/notes"),
        QuickFolder("一時保管", ""),  # 未設定でも F7 の枠は残る
    ]


def test_save_then_load_roundtrip_and_new_key_wins_over_legacy():
    d, get, put = _store({LEGACY_KEY_NOTES: "/old"})
    folders = [QuickFolder("雑記録", "/a"), QuickFolder("書式", "/b"), QuickFolder("判例", "/c")]
    save_quick_folders(put, folders)
    assert load_quick_folders(get) == folders
    assert json.loads(d[KEY_QUICK_FOLDERS])[2] == {"label": "判例", "path": "/c"}


def test_empty_list_stays_empty_and_broken_json_falls_back():
    d, get, put = _store({LEGACY_KEY_NOTES: "/old"})
    save_quick_folders(put, [])
    assert load_quick_folders(get) == []  # 全削除が旧 2 枠で復活しない
    d[KEY_QUICK_FOLDERS] = "{broken"
    assert load_quick_folders(get)[0] == QuickFolder("雑記録", "/old")


def test_load_caps_at_slot_count():
    d, get, put = _store()
    d[KEY_QUICK_FOLDERS] = json.dumps(
        [{"label": f"n{i}", "path": f"/p{i}"} for i in range(MAX_QUICK_FOLDERS + 5)]
    )
    assert len(load_quick_folders(get)) == MAX_QUICK_FOLDERS


def test_bar_shift_layer_switches_only_when_populated():
    bar = FunctionKeysBar()
    bar.set_slot(6, "雑記録", enabled=True)
    bar.set_shift_active(True)
    assert not bar.shift_active()  # Shift 段が空なら切り替えない
    assert bar._cells[5].text() == "F6 雑記録"

    bar.set_slot(6, "判例", enabled=True, shift=True)
    fired = []
    bar.keyTriggered.connect(lambda k, sh: fired.append((k, sh)))
    bar.set_shift_active(True)
    assert bar._cells[5].text() == "F6 判例"
    assert not bar._cells[6].isEnabled()  # Shift 段で未割当のセルは枠だけ
    bar._cells[5].click()
    bar.set_shift_active(False)
    assert bar._cells[5].text() == "F6 雑記録"
    bar._cells[5].click()
    assert fired == [(6, True), (6, False)]

    bar.set_shift_active(True)
    bar.clear_slot(6, shift=True)  # Shift 段が空になったら通常段へ戻る
    assert not bar.shift_active() and bar._cells[5].text() == "F6 雑記録"
