"""単一インスタンス IPC (src/ipc.py) のテスト。

2026-06-04 追加。プライマリ受信を waitForReadyRead/waitForDisconnected の
同期ブロックから readyRead/disconnected シグナルの非同期方式に変えた
(K-SystemZ 連打でメインスレッドが累積ブロックするのを避ける) のに合わせ、
これまで未整備だった IPC のラウンドトリップを固定する。

QLocalSocket は offscreen でも動く。secondary 送信は同期 (try_send_to_primary)、
primary 受信は非同期なので、送信後に event loop を回してコールバック発火を待つ。
"""
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

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
    # str(Path(...)) は OS でセパレータが変わる (Windows は b\c) ため、文字列で
    # なく Path 同士で比較する (分割・strip・空行スキップの契約だけを検証)。
    assert out == [Path("a"), Path("b/c"), Path("日本語")]


def test_send_to_primary_returns_false_without_server():
    _app()
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    # primary が居なければ送信は失敗し、呼び出し側は自分が primary になる。
    assert try_send_to_primary([Path("x")], timeout_ms=200) is False


# secondary を別プロセスで起動するための最小スクリプト。本番 (K-SystemZ が
# subprocess.Popen で k-file.exe を再起動 → IPC でパス送信 → 即終了) と同じ
# 「別プロセスからの送信」を再現する。同一プロセスの loopback では Windows の
# 名前付きパイプが切断タイミング依存になり、受信側が読む前にパイプが閉じると
# ペイロードを取りこぼすため、実プロセス間でないと受信を正しく検証できない。
_SENDER_SCRIPT = """
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from src.ipc import try_send_to_primary
QCoreApplication([])
paths = [Path(a) for a in sys.argv[1:]]
sys.exit(0 if try_send_to_primary(paths) else 1)
"""


def _spawn_sender(paths: list[Path]) -> subprocess.Popen:
    """別プロセスの secondary を非ブロッキングで起動する。

    Popen (= 待たない) なのがポイント。本番では primary が app.exec() で event
    loop を回している最中に secondary が接続してくる。テストでも子の起動と並行に
    primary の loop を回さないと、子が接続→送信→切断→終了し切ってから accept する
    ことになり、本番と違うタイミング (切断後 accept) になってしまう。
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"           # argv の日本語パスを確実に UTF-8 で渡す
    return subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(_SENDER_SCRIPT), *map(str, paths)],
        cwd=str(REPO_ROOT),
        env=env,
    )


def test_ipc_roundtrip_delivers_paths(tmp_path):
    app = _app()
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    received: list[list[Path]] = []
    server = IpcServer(received.append)
    try:
        assert server.is_listening()
        p1, p2 = tmp_path / "事件A", tmp_path / "b"
        # 別プロセス (本番同様の secondary) を起動し、その送信と並行に primary の
        # event loop を回す (= 本番の app.exec() と同じ状況) → readyRead で受信。
        proc = _spawn_sender([p1, p2])
        try:
            _pump(app, lambda: len(received) > 0, timeout_ms=20000)
            assert proc.wait(timeout=20) == 0
        finally:
            if proc.poll() is None:
                proc.kill()
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
