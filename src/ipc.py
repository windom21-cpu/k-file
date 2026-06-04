"""単一インスタンス + IPC (M6b)。

複数の k-file プロセスが立ち上がるのを避け、2 つ目以降の起動は既存プロセスに
コマンドライン引数 (フォルダパス群) を IPC で渡してから自身は終了する。

仕組み:
  - primary: 起動時に QLocalServer("k-file-instance") を listen
  - secondary: 起動時に QLocalSocket でその名前に接続 → 接続できれば既存 primary
    あり → パスを送信して exit。接続できなければ自身が primary になる

ユーザー経路:
  - 法律実務家が K-SystemZ から「フォルダを開く」を繰り返す。M6b 完成後、
    K-SystemZ 側の「k-file.exe プロセス重複検出」は撤去予定 (k-systemz は
    毎回 `subprocess.Popen(["k-file.exe", path])` を呼ぶだけで OK)。

Win/Linux/Mac で透過的に動く (Win: 名前付きパイプ / Unix: /tmp ソケット)。
プロセス間のソケット権限は OS の既定 (シングルユーザー前提)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# 接続名 (バージョン suffix 付き — プロトコル変更時に旧 server と隔離)
SINGLE_INSTANCE_KEY = "k-file-instance-v1"

# 1 パスは改行区切り、UTF-8。EOF (相手 close) で終了。

# secondary が送信後に disconnect しないまま放置/crash した場合の保険タイムアウト。
_RECV_FALLBACK_MS = 1000


def _parse_paths(text: str) -> list[Path]:
    """改行区切りテキストをパス列に変換する (空行はスキップ、不正は捨てる)。"""
    paths: list[Path] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            paths.append(Path(line))
        except (TypeError, ValueError):
            continue
    return paths


def try_send_to_primary(paths: list[Path], timeout_ms: int = 500) -> bool:
    """既存 primary プロセスにパス群を送る。送信できれば True。

    送信できなかったとき (= primary 不在 / 接続失敗) は False を返し、
    呼び出し側はそのまま自分が primary として起動を続行する。
    """
    sock = QLocalSocket()
    sock.connectToServer(SINGLE_INSTANCE_KEY)
    if not sock.waitForConnected(timeout_ms):
        return False
    try:
        # パスは改行区切り、空送信 (paths=[]) でも window の raise だけ要求できる
        payload = "\n".join(str(p) for p in paths).encode("utf-8")
        sock.write(payload)
        sock.flush()
        sock.waitForBytesWritten(timeout_ms)
        sock.disconnectFromServer()
        if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            sock.waitForDisconnected(timeout_ms)
    finally:
        sock.close()
    return True


class IpcServer(QObject):
    """primary 側の listener。secondary からの送信を受けて on_paths を呼ぶ。

    on_paths(paths: list[Path]) は MainWindow 側で各フォルダを add_case_tab し、
    ウインドウを前面に出す処理を行う。
    """

    def __init__(
        self,
        on_paths: Callable[[list[Path]], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_paths = on_paths
        # 古いソケットファイル (前回 crash 時の残骸) を確実に消す
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        self._server = QLocalServer(self)
        self._server.listen(SINGLE_INSTANCE_KEY)
        self._server.newConnection.connect(self._on_new_connection)

    def is_listening(self) -> bool:
        return self._server.isListening()

    def close(self) -> None:
        self._server.close()
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)

    def _on_new_connection(self) -> None:
        """secondary が接続してきた: メインスレッドをブロックせず非同期に受信する。

        旧実装は waitForReadyRead(500) + waitForDisconnected(200) でメイン
        スレッドを最大 0.7 秒/接続ブロックしていた。K-SystemZ から「フォルダを
        開く」を連打されると累積し、UI が固まりかける一因になりうる。readyRead /
        disconnected シグナルで受け取ってブロックを排除し、相手が切断しないまま
        放置/crash した場合だけ _RECV_FALLBACK_MS のタイマーで打ち切る。
        """
        sock = self._server.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()
        state = {"done": False}
        timer = QTimer(self)
        timer.setSingleShot(True)

        def finish() -> None:
            if state["done"]:
                return
            state["done"] = True
            timer.stop()
            buf.extend(bytes(sock.readAll()))  # 未通知の残バイトを回収
            sock.close()
            sock.deleteLater()
            text = bytes(buf).decode("utf-8", errors="replace")
            # paths が空でも raise だけは行う (旧挙動踏襲)
            self._on_paths(_parse_paths(text))

        timer.timeout.connect(finish)
        sock.readyRead.connect(lambda: buf.extend(bytes(sock.readAll())))
        sock.disconnected.connect(finish)
        timer.start(_RECV_FALLBACK_MS)
        # newConnection を処理する頃には secondary が既に送信 + 切断済みのことが
        # ある。その場合 disconnected シグナルは届かないので明示的に回収する。
        if sock.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            finish()
