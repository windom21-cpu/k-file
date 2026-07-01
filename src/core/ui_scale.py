"""表示倍率 (UI scale) のドメインロジック — Qt 非依存。

k-file 全体 (ウインドウ・文字・全 widget) を一律に拡大縮小するための倍率を扱う。
実際の拡大は QApplication 生成前に環境変数 QT_SCALE_FACTOR を設定して Qt に任せる
(src/main.py の `_apply_ui_scale`)。この方式なら QSS も固定 px も一切書き換えず、
デバイスピクセル段で全要素を同じ比率でスケールできるため、Win95 風レイアウトの
緻密な px 不変条件 (バナー/バー offset 等 ADR-42、行高 18px 等) を比率のまま保てる。

QT_SCALE_FACTOR は Qt が起動時に一度だけ読むため、倍率変更は再起動で反映する
(MainWindow が updater の relaunch を流用して自動再起動する)。100% のときは環境変数を
一切触らない = OS 側のスケール (125%/150% 等、ADR-45 の PassThrough) にも無干渉。

このモジュールは「値の正規化と段階移動」だけを持つ (Qt / DB / OS に触れない):
  - SETTING_KEY        — kfile.db settings のキー
  - SCALE_STEPS        — メニュー / Ctrl+± で選べる離散倍率 (%)
  - clamp_scale        — MIN..MAX に収める
  - parse_scale        — db 文字列 → 倍率 int (不正値は既定)
  - scale_factor_str   — QT_SCALE_FACTOR 用文字列 ("1.25" 等)
  - step_up / step_down — Ctrl+± の 1 段移動
"""
from __future__ import annotations

# kfile.db settings のキー
SETTING_KEY = "ui_scale_percent"

DEFAULT_SCALE = 100
MIN_SCALE = 75
MAX_SCALE = 200

# メニューに並べる離散倍率 (昇順、DEFAULT_SCALE を必ず含める)。
# 25% 刻みは QT_SCALE_FACTOR が正確な二進小数 (1.25/1.5/1.75/0.75) になり、
# にじみ計算上も素直。上限 200% は OS 側スケールと掛かるので実効はさらに上まで届く。
SCALE_STEPS = [75, 100, 125, 150, 175, 200]


def clamp_scale(percent: int) -> int:
    """倍率を MIN_SCALE..MAX_SCALE に収める。"""
    if percent < MIN_SCALE:
        return MIN_SCALE
    if percent > MAX_SCALE:
        return MAX_SCALE
    return percent


def parse_scale(value: str | None) -> int:
    """db に保存された文字列を倍率 int に変換する。

    未設定 (None) や数値化できない値は DEFAULT_SCALE、範囲外は clamp。
    手書き db 等で "150.0" のような表記が来ても拾えるよう float 経由で解釈する。
    """
    if value is None:
        return DEFAULT_SCALE
    try:
        pct = int(round(float(value)))
    except (TypeError, ValueError):
        return DEFAULT_SCALE
    return clamp_scale(pct)


def scale_factor_str(percent: int) -> str:
    """QT_SCALE_FACTOR に渡す倍率文字列。100%→"1"、125%→"1.25"、75%→"0.75"。"""
    factor = clamp_scale(percent) / 100
    # 末尾の余分な 0 と小数点を落として "1.25" / "1.5" / "1" の形に整える
    return f"{factor:.4f}".rstrip("0").rstrip(".")


def step_up(percent: int) -> int:
    """現在倍率より 1 段上の SCALE_STEPS を返す (上限では据え置き)。"""
    cur = clamp_scale(percent)
    for s in SCALE_STEPS:
        if s > cur:
            return s
    return SCALE_STEPS[-1]


def step_down(percent: int) -> int:
    """現在倍率より 1 段下の SCALE_STEPS を返す (下限では据え置き)。"""
    cur = clamp_scale(percent)
    for s in reversed(SCALE_STEPS):
        if s < cur:
            return s
    return SCALE_STEPS[0]
