"""OS クリップボード経由のファイル コピー / 切り取り / 貼り付け (Explorer 相互運用)。

Windows Explorer と同じ仕組みでファイルをクリップボードに載せる:
- ファイルの実体は `text/uri-list` (= Win では CF_HDROP) に URL として載せる。
  Qt が両者を相互変換するため、Explorer でコピーしたファイルを k-file で
  貼り付け / k-file でコピーしたファイルを Explorer で貼り付け、が両方向で効く。
- 「コピー」か「切り取り」かは Windows シェル独自の `Preferred DropEffect`
  形式 (4 byte の DWORD: COPY=1 / MOVE=2) で伝える。これを書けば Explorer 側の
  Ctrl+V がコピー/移動を正しく選び、読めば Explorer 側が Ctrl+C/Ctrl+X どちらを
  したかが分かる。

Linux/Mac では CF_HDROP は無いが、Qt が urls を text/uri-list として保持し、
`Preferred DropEffect` も独自 MIME 型として往復するので、k-file 内のコピー貼り付け
(in-app) は問題なく動く (= 貼り付けロジックを Linux 本機でテスト可能)。Explorer との
相互運用は Windows 固有なので実機確認する。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QMimeData, QUrl
from PySide6.QtWidgets import QApplication

# Windows シェルが cut/copy の区別に使うクリップボード形式とその値。
_PREFERRED_DROP_EFFECT = "Preferred DropEffect"
_DROPEFFECT_COPY = 1
_DROPEFFECT_MOVE = 2


def build_file_mime(paths: list[Path], cut: bool) -> QMimeData:
    """ファイル群を載せた QMimeData を作る (Explorer 互換)。

    クリップボードに依存しない純粋関数なのでユニットテストしやすい
    (グローバル QClipboard を触ると offscreen Qt が終了時に segfault するため、
     テストはこの mime レベルで検証する)。
    """
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    effect = _DROPEFFECT_MOVE if cut else _DROPEFFECT_COPY
    mime.setData(
        _PREFERRED_DROP_EFFECT, QByteArray(effect.to_bytes(4, "little"))
    )
    return mime


def parse_file_mime(mime: QMimeData | None) -> tuple[list[Path], bool] | None:
    """QMimeData からファイル群を取り出す。

    Returns: (paths, cut) — cut=True なら切り取り (貼り付けで移動)。
    ファイルが載っていなければ None。クリップボード非依存。
    """
    if mime is None or not mime.hasUrls():
        return None
    paths: list[Path] = []
    for u in mime.urls():
        if u.isLocalFile():
            local = u.toLocalFile()
            if local:
                paths.append(Path(local))
    if not paths:
        return None
    cut = False
    if mime.hasFormat(_PREFERRED_DROP_EFFECT):
        data = bytes(mime.data(_PREFERRED_DROP_EFFECT))
        if len(data) >= 4:
            val = int.from_bytes(data[:4], "little")
            # MOVE ビットが立っていて COPY ビットが立っていなければ「切り取り」。
            # Explorer は cut で 2、copy で 1 (または 5 = COPY|LINK) を入れる。
            cut = bool(val & _DROPEFFECT_MOVE) and not (val & _DROPEFFECT_COPY)
    return paths, cut


def set_file_clipboard(paths: list[Path], cut: bool) -> None:
    """ファイル群をクリップボードに載せる (Explorer 互換)。

    cut=True なら「切り取り」(貼り付けで移動)、False なら「コピー」。
    """
    cb = QApplication.clipboard()
    if cb is None or not paths:
        return
    cb.setMimeData(build_file_mime(paths, cut))


def read_file_clipboard() -> tuple[list[Path], bool] | None:
    """クリップボードからファイル群を読む。

    Returns: (paths, cut) — cut=True なら切り取り (貼り付けで移動)。
    ファイルが載っていなければ None。
    """
    cb = QApplication.clipboard()
    if cb is None:
        return None
    return parse_file_mime(cb.mimeData())


def clipboard_has_files() -> bool:
    """クリップボードにファイルが載っているか (貼り付けメニューの enable 判定用)。"""
    cb = QApplication.clipboard()
    if cb is None:
        return False
    mime = cb.mimeData()
    return mime is not None and mime.hasUrls()


def clear_file_clipboard() -> None:
    """クリップボードを空にする (切り取り → 貼り付け後に一度きりにするため)。"""
    cb = QApplication.clipboard()
    if cb is not None:
        cb.clear()
