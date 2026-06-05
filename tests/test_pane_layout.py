"""INBOX と参照フォルダの「更新列の出し入れ」同期テスト。

2026-06-05 追加。F4 で半幅にした時 (特に Win で参照フォルダにファイルが多い時)、
INBOX と参照フォルダで Name 列幅が大きく食い違う現象があった。原因は両ペインが
それぞれ自前の viewport 幅で「更新列を出すか隠すか (date_avail < 30)」を独立判定し、
両 viewport の数 px 差が 30px 閾値をまたいだ瞬間に片方だけ更新列が消える点。

修正後は MainWindow が両テーブルの実 viewport の小さい方を共通基準として両ペインへ
渡し (_sync_responsive_columns → set_shared_name_width)、判定が必ず一致する。
ここではその不一致が「どの幅でも起きない」ことと、Name 列幅の残差が小さいことを固定する。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import src.ui.inbox_pane as inbox_pane_mod  # noqa: E402
from src.core.inbox_watcher import InboxSource  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _settle(app: QApplication, n: int = 6) -> None:
    # _apply_pane_layout は singleShot(0) で _sync_responsive_columns を呼ぶので、
    # イベントループを数回回して同期を確定させる。
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    # kfile.db をテンポラリに隔離 (ユーザーの app data を汚さない)。
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))

    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    for i in range(3):
        (inbox_dir / f"in_{i}.pdf").write_bytes(b"%PDF-1.4\n")

    # 参照フォルダ: サブフォルダ複数 + ファイル多数 (再現条件に寄せる)。
    case_root = tmp_path / "case"
    case_root.mkdir()
    for d in range(6):
        sub = case_root / f"{d + 1}_s{d}"
        sub.mkdir()
        (sub / "x.pdf").write_bytes(b"%PDF-1.4\n")
    for i in range(200):
        (case_root / f"f_{i:03d}.pdf").write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        inbox_pane_mod, "_DEV_INBOX_SOURCES", [InboxSource("scan", inbox_dir)]
    )

    app = _app()
    from src.ui.main_window import MainWindow

    win = MainWindow(initial_paths=None)
    win.inbox_pane.reload_sources([InboxSource("scan", inbox_dir)])
    win.case_pane.add_case_tab(case_root)
    win.show()
    _settle(app, 8)
    yield app, win
    win.close()


def _date_hidden(win):
    return (
        win.inbox_pane.table.isColumnHidden(2),
        win.case_pane.table.isColumnHidden(2),
    )


def _name_delta(win):
    return win.inbox_pane.table.columnWidth(0) - win.case_pane.table.columnWidth(0)


def test_no_date_column_disagreement_across_widths(main_window):
    """どの幅でも INBOX と参照フォルダの更新列の表示状態が一致する。"""
    app, win = main_window
    disagreements = []
    worst_delta = 0
    # 旧不一致バンド (≒831-835px) を含む広い範囲を 1px 刻みで掃引。
    for w in range(700, 1500):
        win.resize(w, 860)
        _settle(app, 4)
        ih, ch = _date_hidden(win)
        if ih != ch:
            disagreements.append(w)
        worst_delta = max(worst_delta, abs(_name_delta(win)))
    assert disagreements == [], (
        f"更新列の表示が食い違う幅が残っている: {disagreements[:10]}"
    )
    # 残差は左カラム/枠の固定誤差ぶん (数 px) のみ。閾値またぎの大ズレは無いこと。
    assert worst_delta <= 6, f"Name 列の残差が大きすぎる: {worst_delta}px"


def test_f4_half_width_keeps_panes_in_lockstep(main_window):
    """F4 半幅トグルが旧バンドに着地しても両ペインが一致する。"""
    app, win = main_window
    # start//2 が旧straddleバンド (831-835) に入る開始幅を含む。
    for start in (1662, 1664, 1670, 1400):
        win.resize(start, 860)
        _settle(app)
        win._half_width_prev = None  # 確実に「縮める」側にする
        win._toggle_half_width()
        _settle(app)
        ih, ch = _date_hidden(win)
        assert ih == ch, (
            f"F4 半幅 (start={start}, half={win.width()}) で更新列が食い違った"
        )
        assert abs(_name_delta(win)) <= 6


def test_preview_pane_min_width_not_inflated_by_long_filename():
    """長いファイル名でもプレビューペインの最小幅が膨らまないこと。

    折返し無し QLabel は minimumSizeHint = 全文幅 になり、放置すると
    プレビューペインの最小幅がファイル名長ぶん膨らむ → splitter がプレビューを
    広げて INBOX だけを極端に狭くする。横 SizePolicy=Ignored + elide で防ぐ。
    """
    app = _app()
    from src.ui.preview_pane import PreviewPane

    pv = PreviewPane()
    pv.resize(400, 600)
    pv.show()
    _settle(app, 4)
    long_name = (
        "R08020011文書フォルダ(田中太郎)損害賠償請求事件_第3準備書面_"
        "証拠説明書_2026年6月05日.pdf/2.3MB/2026-06-05 14:30/12 ページ"
    )
    pv._set_info_text(long_name)
    _settle(app, 4)
    assert pv.minimumSizeHint().width() <= 200, (
        f"プレビューペイン最小幅がファイル名で膨らんでいる: "
        f"{pv.minimumSizeHint().width()}px"
    )
    pv.close()


def test_inbox_not_squeezed_in_preview_mode_with_long_name(main_window):
    """3カラム時に長いファイル名を表示しても INBOX が極端に狭くならないこと。"""
    app, win = main_window
    win.resize(1400, 860)
    _settle(app)
    if not win._preview_visible:
        win._toggle_preview()
        _settle(app)
    win.preview_pane._set_info_text(
        "超長い案件ファイル名" * 10 + ".pdf/2.3MB/2026-06-05 14:30/30 ページ"
    )
    win._apply_pane_layout()
    _settle(app)
    inbox_w = win.splitter.sizes()[0]
    assert inbox_w >= 200, f"INBOX が squeeze された: {inbox_w}px"


def test_shared_width_override_falls_back_when_none(main_window):
    """共有基準を None にすると自前 viewport にフォールバックする (単体利用の保険)。"""
    app, win = main_window
    win.resize(1400, 860)
    _settle(app)
    # None を渡しても例外なく動き、列が壊れないこと。
    win.inbox_pane.set_shared_name_width(None)
    win.case_pane.set_shared_name_width(None)
    _settle(app)
    assert win.inbox_pane.table.columnWidth(0) > 0
    assert win.case_pane.table.columnWidth(0) > 0
