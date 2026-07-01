"""表示倍率 (UI scale) のドメインロジック + relaunch スクリプト書き出しの単体テスト。

Qt / DB / OS には触れない (ui_scale は純ロジック、relaunch は実ファイル生成のみ)。
"""

from __future__ import annotations

from src.core.ui_scale import (
    DEFAULT_SCALE,
    MAX_SCALE,
    MIN_SCALE,
    SCALE_STEPS,
    clamp_scale,
    parse_scale,
    scale_factor_str,
    step_down,
    step_up,
)
from src.core.updater import write_relaunch_script


# ───────── SCALE_STEPS / 既定値の健全性 ─────────


def test_scale_steps_sorted_and_contains_default():
    assert SCALE_STEPS == sorted(SCALE_STEPS)
    assert DEFAULT_SCALE in SCALE_STEPS
    assert SCALE_STEPS[0] == MIN_SCALE
    assert SCALE_STEPS[-1] == MAX_SCALE


def test_default_within_range():
    assert MIN_SCALE <= DEFAULT_SCALE <= MAX_SCALE


# ───────── clamp_scale ─────────


def test_clamp_scale_in_range():
    assert clamp_scale(125) == 125


def test_clamp_scale_below_min():
    assert clamp_scale(10) == MIN_SCALE


def test_clamp_scale_above_max():
    assert clamp_scale(9999) == MAX_SCALE


# ───────── parse_scale ─────────


def test_parse_scale_none_is_default():
    assert parse_scale(None) == DEFAULT_SCALE


def test_parse_scale_valid():
    assert parse_scale("150") == 150


def test_parse_scale_float_string():
    assert parse_scale("150.0") == 150


def test_parse_scale_garbage_is_default():
    assert parse_scale("abc") == DEFAULT_SCALE
    assert parse_scale("") == DEFAULT_SCALE


def test_parse_scale_out_of_range_is_clamped():
    assert parse_scale("500") == MAX_SCALE
    assert parse_scale("1") == MIN_SCALE


# ───────── scale_factor_str (QT_SCALE_FACTOR 文字列) ─────────


def test_scale_factor_str_common_steps():
    assert scale_factor_str(100) == "1"
    assert scale_factor_str(125) == "1.25"
    assert scale_factor_str(150) == "1.5"
    assert scale_factor_str(175) == "1.75"
    assert scale_factor_str(75) == "0.75"


def test_scale_factor_str_is_float_parseable():
    # QT_SCALE_FACTOR は Qt が float として読むので、常に float() 可能であること。
    for pct in SCALE_STEPS:
        assert float(scale_factor_str(pct)) == pct / 100


# ───────── step_up / step_down ─────────


def test_step_up_moves_one_notch():
    assert step_up(100) == 125
    assert step_up(75) == 100


def test_step_up_saturates_at_max():
    assert step_up(MAX_SCALE) == MAX_SCALE
    assert step_up(999) == MAX_SCALE


def test_step_down_moves_one_notch():
    assert step_down(125) == 100
    assert step_down(200) == 175


def test_step_down_saturates_at_min():
    assert step_down(MIN_SCALE) == MIN_SCALE
    assert step_down(1) == MIN_SCALE


def test_step_from_off_ladder_value():
    # SCALE_STEPS 外 (110%) からでも隣接段へ動ける。
    assert step_up(110) == 125
    assert step_down(110) == 100


# ───────── write_relaunch_script ─────────


def test_write_relaunch_script_basic(tmp_path):
    install = tmp_path / "k-file-windows"
    install.mkdir()
    out = tmp_path / "relaunch.ps1"
    result = write_relaunch_script(
        install, new_exe_name="k-file.exe", script_path=out
    )
    assert result == out
    assert out.exists()
    text = out.read_text(encoding="utf-8-sig")
    # 旧プロセス消滅待ち (IPC 競合回避) と exe 起動が含まれること
    assert "Get-Process -Name 'k-file'" in text
    assert "Start-Process -FilePath $exe" in text
    assert str((install / "k-file.exe").resolve()) in text


def test_write_relaunch_script_no_zip_expand(tmp_path):
    # relaunch は更新と違い zip 展開しない (Expand-Archive を含まない)。
    install = tmp_path / "app"
    install.mkdir()
    out = tmp_path / "relaunch.ps1"
    write_relaunch_script(install, script_path=out)
    text = out.read_text(encoding="utf-8-sig")
    assert "Expand-Archive" not in text
