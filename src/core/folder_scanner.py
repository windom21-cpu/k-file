r"""事件フォルダの構造スキャン (Qt 非依存・ユニットテスト可能)。

事件フォルダ内のサブフォルダを実フォルダから動的に読み取り、`\d_.*` パターン
(0_〜9_) のものを優先して **Alt+1〜9 に順に繰り上げ割当** する (欠番があれば
次が繰り上がる)。10 個目以降のサブフォルダは Alt 割当なし。事件フォルダ直下の
ファイル (どのサブフォルダにも入っていないもの) も取得する。

UI 層 (case_pane) はこのモジュールの結果を受けてボタン・一覧を組み立てる。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 先頭が「数字 + アンダースコア」のサブフォルダ (1_文書 等) を分類フォルダ扱い
_PATTERN_RE = re.compile(r"^\d_")

# Alt+1〜9 をサブフォルダに割当 (Alt+0 は事件フォルダ直下ビュー)
MAX_ALT_SUBFOLDERS = 9


@dataclass
class FileEntry:
    """フォルダ内の 1 エントリ (ファイルまたはフォルダ)。"""

    name: str
    path: Path
    is_dir: bool
    size: int      # ファイルのバイト数。フォルダは 0
    mtime: float
    is_link: bool = False  # Linux symlink / Win .lnk なら True (事件ショートカット判定用)   # 最終更新 (epoch 秒)


@dataclass
class SubFolder:
    """事件フォルダ直下のサブフォルダ 1 個。"""

    name: str
    path: Path
    alt_key: int | None   # 1〜9。10 個目以降は None (クリック専用)
    file_count: int       # 直下のファイル数 (件数バッジ用)
    has_child_dirs: bool   # ネストフォルダを含むか (M2 Step2 の階層タブ判定用)


@dataclass
class CaseScan:
    """事件フォルダ 1 件のスキャン結果。"""

    root_path: Path
    subfolders: list[SubFolder]
    root_files: list[FileEntry]   # 事件フォルダ直下のファイル


def _to_entry(p: Path) -> FileEntry:
    st = p.stat()                     # follows symlinks → is_dir reflects target
    is_dir = p.is_dir()
    # Linux: シンボリックリンクは is_symlink() = True、target に追随して is_dir も決まる
    # Win:   .lnk はただのファイル (is_symlink() = False、suffix=.lnk で判定)
    try:
        is_link = p.is_symlink() or p.suffix.lower() == ".lnk"
    except OSError:
        is_link = False
    return FileEntry(
        name=p.name,
        path=p,
        is_dir=is_dir,
        size=0 if is_dir else st.st_size,
        mtime=st.st_mtime,
        is_link=is_link,
    )


def list_folder(path: Path) -> list[FileEntry]:
    """フォルダ直下のエントリ一覧 (ファイル + サブフォルダ)。

    存在しない / 読めない場合は空リスト。事件フォルダ内の任意フォルダの中身
    表示・ネスト走査に使う。
    """
    path = Path(path)
    if not path.is_dir():
        return []
    entries: list[FileEntry] = []
    try:
        children = list(path.iterdir())
    except OSError:
        return []
    for p in children:
        try:
            entries.append(_to_entry(p))
        except OSError:
            continue  # 壊れたシンボリックリンク等はスキップ
    return entries


def list_files(path: Path) -> list[FileEntry]:
    """フォルダ直下の「ファイルのみ」一覧。"""
    return [e for e in list_folder(path) if not e.is_dir]


def scan_case_folder(path: Path) -> CaseScan:
    r"""事件フォルダをスキャンし、サブフォルダ構成と直下ファイルを返す。

    - サブフォルダは `\d_` パターンを優先順に並べ、その後その他フォルダ
    - 先頭 9 個に Alt+1〜9 を割当 (繰り上げ)、10 個目以降は alt_key=None
    - root_files = 事件フォルダ直下のファイル (Alt+0「事件フォルダ直下」ビュー)
    """
    path = Path(path)
    dirs: list[Path] = []
    root_files: list[FileEntry] = []

    if path.is_dir():
        try:
            children = sorted(path.iterdir(), key=lambda x: x.name)
        except OSError:
            children = []
        for p in children:
            try:
                # ショートカット (Linux symlink / Win .lnk) は左ボタン列の
                # サブフォルダ扱いせず、「事件フォルダ直下」ビューに出す
                # (別事件への入口は分類カテゴリではないため)。
                try:
                    is_link = p.is_symlink() or p.suffix.lower() == ".lnk"
                except OSError:
                    is_link = False
                if p.is_dir() and not is_link:
                    dirs.append(p)
                elif p.is_file() or is_link:
                    root_files.append(_to_entry(p))
            except OSError:
                continue

    # \d_ パターンのフォルダを優先、その後その他フォルダ (名前順)
    pattern_dirs = [d for d in dirs if _PATTERN_RE.match(d.name)]
    other_dirs = [d for d in dirs if not _PATTERN_RE.match(d.name)]
    ordered = pattern_dirs + other_dirs

    subfolders: list[SubFolder] = []
    for i, d in enumerate(ordered):
        alt = i + 1 if i < MAX_ALT_SUBFOLDERS else None
        try:
            entries = list(d.iterdir())
            file_count = sum(1 for e in entries if e.is_file())
            has_child_dirs = any(e.is_dir() for e in entries)
        except OSError:
            file_count, has_child_dirs = 0, False
        subfolders.append(SubFolder(d.name, d, alt, file_count, has_child_dirs))

    return CaseScan(root_path=path, subfolders=subfolders, root_files=root_files)
