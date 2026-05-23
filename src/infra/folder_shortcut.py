"""事件フォルダへの「ショートカット」を別フォルダ内に作成する。

主な用途は **他事件への集約マーカ**: 夫婦事件 (A/B) で B の root に A への
ショートカットを置き、文書を A に集約する運用 (UI: 「他事件へ」ボタン)。

- Linux/Mac: 配置先に **シンボリックリンク** を作る。
- Windows: 配置先に **.lnk** を作る (PowerShell の WScript.Shell COM 経由、
  外部ライブラリに依存しない)。

既に同名がある場合は再作成せず、既存パスを返す (上書きしない方が安全)。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def detect_desktop_dir() -> Path:
    """ユーザーの実デスクトップ。日本語環境/英語環境の両方を探す。

    case → デスクトップへの「保留戻し」(<< ボタン) の宛先として利用する。
    実デスクトップは OS 管理で消えない (アプリ管理の保留フォルダより安全)。
    """
    for c in (Path.home() / "デスクトップ", Path.home() / "Desktop"):
        if c.is_dir():
            return c
    return Path.home() / "Desktop"


def create_folder_shortcut(
    target: Path, dest_dir: Path, name: str | None = None
) -> Path:
    """target フォルダへのショートカットを dest_dir に作成。

    Returns: 作成された (または既存の) ショートカットの絶対パス。
    Raises: OSError — 対象不正 / 配置先未検出 / 作成失敗。
    """
    target = Path(target)
    dest_dir = Path(dest_dir)
    if not target.is_dir():
        raise OSError(f"対象フォルダが存在しません: {target}")
    if not dest_dir.is_dir():
        raise OSError(f"配置先フォルダが見つかりません: {dest_dir}")
    name = name or target.name

    if sys.platform == "win32":
        return _make_windows_lnk(target, dest_dir, name)
    return _make_symlink(target, dest_dir, name)


def _make_symlink(target: Path, dest_dir: Path, name: str) -> Path:
    link_path = dest_dir / name
    # 既存 (シンボリックリンク含む) は触らず返す
    if link_path.exists() or link_path.is_symlink():
        return link_path
    os.symlink(str(target), str(link_path), target_is_directory=True)
    return link_path


def _make_windows_lnk(target: Path, dest_dir: Path, name: str) -> Path:
    lnk_path = dest_dir / f"{name}.lnk"
    if lnk_path.exists():
        return lnk_path
    # PowerShell で COM 経由の .lnk 作成。pywin32 等の外部依存を避ける。
    # シングルクォートのエスケープ ('' = ')。
    t_esc = str(target).replace("'", "''")
    l_esc = str(lnk_path).replace("'", "''")
    cmd = [
        "powershell.exe", "-NoProfile", "-Command",
        f"$ws=New-Object -ComObject WScript.Shell; "
        f"$s=$ws.CreateShortcut('{l_esc}'); "
        f"$s.TargetPath='{t_esc}'; "
        f"$s.Save()",
    ]
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if res.returncode != 0:
        raise OSError(
            f"PowerShell でのショートカット作成に失敗: {res.stderr.strip() or res.stdout.strip()}"
        )
    return lnk_path
