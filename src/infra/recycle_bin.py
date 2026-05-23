"""OS のごみ箱フォルダを開く (削除 Undo の主動線)。

Win: explorer.exe shell:RecycleBinFolder で標準のごみ箱ウインドウを開く →
ユーザーは右クリック「元に戻す」で復元する (Windows ネイティブ UX)。

Linux/Mac は dev 用フォールバック (本番の配布対象は Windows のみ)。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_recycle_bin() -> tuple[bool, str]:
    """OS の native なごみ箱フォルダを開く。(ok, message) を返す。"""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"])
            return True, "ごみ箱を開きました"
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(Path.home() / ".Trash")])
            return True, "ごみ箱を開きました"
        # Linux (dev 用フォールバック)
        subprocess.Popen(["xdg-open", "trash:///"])
        return True, "ごみ箱を開きました"
    except OSError as e:
        return False, f"ごみ箱を開けませんでした: {e}"
