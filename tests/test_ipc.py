"""単一インスタンス IPC (src/ipc.py) のテスト。

2026-06-04 追加。プライマリ受信を waitForReadyRead/waitForDisconnected の
同期ブロックから readyRead/disconnected シグナルの非同期方式に変えた
(K-SystemZ 連打でメインスレッドが累積ブロックするのを避ける) のに合わせ、
これまで未整備だった IPC のラウンドトリップを固定する。

QLocalSocket は offscreen でも動く。secondary 送信は同期 (try_send_to_primary)、
primary 受信は非同期なので、送信後に event loop を回してコールバック発火を待つ。
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtNetwork import QLocalServer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.ipc import (  # noqa: E402
    SINGLE_INSTANCE_KEY,
    IpcServer,
    _parse_paths,
    try_send_to_primary,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pump(app: QApplication, predicate, timeout_ms: int = 3000) -> None:
    """predicate() が True になるか timeout まで event loop を回す。"""
    waited = 0
    while not predicate() and waited < timeout_ms:
        app.processEvents()
        time.sleep(0.02)
        waited += 20
    app.processEvents()


def test_parse_paths_splits_and_skips_blanks():
    out = _parse_paths("a\n\n  b/c  \n日本語\n")
    assert [str(p) for p in out] == ["a", "b/c", "日本語"]


def test_send_to_primary_returns_false_without_server():
    _app()
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    # primary が居なければ送信は失敗し、呼び出し側は自分が primary になる。
    assert try_send_to_primary([Path("x")], timeout_ms=200) is False


def test_ipc_roundtrip_delivers_paths(tmp_path):
    app = _app()
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    received: list[list[Path]] = []
    server = IpcServer(received.append)
    try:
        assert server.is_listening()
        p1, p2 = tmp_path / "事件A", tmp_path / "b"
        assert try_send_to_primary([p1, p2]) is True
        _pump(app, lambda: len(received) > 0)
        assert len(received) == 1
        assert [p.name for p in received[0]] == ["事件A", "b"]
    finally:
        server.close()


def test_ipc_empty_send_still_fires_callback():
    app = _app()
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    received: list[list[Path]] = []
    server = IpcServer(received.append)
    try:
        # paths=[] でも window を前面に出す合図として callback は呼ばれる。
        assert try_send_to_primary([]) is True
        _pump(app, lambda: len(received) > 0)
        assert received == [[]]
    finally:
        server.close()
