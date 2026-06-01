r"""事件フォルダの構造スキャン (Qt 非依存・ユニットテスト可能)。

事件フォルダ内のサブフォルダを実フォルダから動的に読み取り、`\d_.*` パターン
(0_〜9_) のものを優先して **Alt+1〜9 に順に繰り上げ割当** する (欠番があれば
次が繰り上がる)。10 個目以降のサブフォルダは Alt 割当なし。事件フォルダ直下の
ファイル (どのサブフォルダにも入っていないもの) も取得する。

UI 層 (case_pane) はこのモジュールの結果を受けてボタン・一覧を組み立てる。
"""
from __future__ import annotations

import os
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


def _entry_from_dirent(de: os.DirEntry) -> FileEntry:
    """os.scandir() の DirEntry から FileEntry を作る (X: フリーズ対策の中核)。

    DirEntry はディレクトリ列挙 (Win の FindFirstFile/FindNextFile) の時点で
    属性・サイズ・日時を取得済みでキャッシュしている。そのため is_dir() /
    is_file() / stat() は追加の syscall を生まない。Path.stat()/Path.is_dir()
    を 1 ファイルにつき個別に呼ぶと metadata 取得が複数回走り、X:(Dropbox)
    上ではメインスレッドをブロックしてフリーズの主因になる (ADR-29 系の続き)。

    stat() は follow_symlinks=True (既定) で旧 _to_entry の p.stat() と同挙動。
    broken symlink ではここで OSError を送出するので、呼び出し側で握り潰して
    スキップすること (旧実装と同じ)。
    """
    # Linux: シンボリックリンクは is_symlink() = True、target に追随して is_dir も決まる
    # Win:   .lnk はただのファイル (is_symlink() = False、suffix=.lnk で判定)
    try:
        is_link = de.is_symlink() or Path(de.name).suffix.lower() == ".lnk"
    except OSError:
        is_link = False
    is_dir = de.is_dir()              # follows symlinks → is_dir reflects target
    st = de.stat()                    # broken symlink ならここで OSError
    return FileEntry(
        name=de.name,
        path=Path(de.path),
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
    entries: list[FileEntry] = []
    try:
        with os.scandir(path) as it:
            for de in it:
                try:
                    entries.append(_entry_from_dirent(de))
                except OSError:
                    continue  # 壊れたシンボリックリンク等はスキップ
    except OSError:
        return []   # 存在しない / ディレクトリでない / 権限エラー等
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

    # os.scandir で 1 回の列挙にまとめ、DirEntry のキャッシュ済み属性
    # (is_dir/is_file/stat) を使う。Path.iterdir + 個別 stat だと X:(Dropbox)
    # 上で metadata 取得がファイル数 × 数回走りメインスレッドが固まるため。
    try:
        with os.scandir(path) as it:
            children = sorted(it, key=lambda de: de.name)
    except OSError:
        children = []

    for de in children:
        try:
            # ショートカット (Linux symlink / Win .lnk) は左ボタン列の
            # サブフォルダ扱いせず、「事件フォルダ直下」ビューに出す
            # (別事件への入口は分類カテゴリではないため)。
            try:
                is_link = de.is_symlink() or Path(de.name).suffix.lower() == ".lnk"
            except OSError:
                is_link = False
            is_dir = de.is_dir()
            is_file = de.is_file()
            if is_dir and not is_link:
                dirs.append(Path(de.path))
            elif is_file or is_link:
                root_files.append(_entry_from_dirent(de))
        except OSError:
            continue

    # \d_ パターンのフォルダを優先、その後その他フォルダ (名前順)
    pattern_dirs = [d for d in dirs if _PATTERN_RE.match(d.name)]
    other_dirs = [d for d in dirs if not _PATTERN_RE.match(d.name)]
    ordered = pattern_dirs + other_dirs

    subfolders: list[SubFolder] = []
    for i, d in enumerate(ordered):
        alt = i + 1 if i < MAX_ALT_SUBFOLDERS else None
        # 件数バッジ用にサブフォルダ直下を 1 回 scandir して数える。
        # DirEntry.is_dir()/is_file() はキャッシュ参照なので追加 syscall 無し
        # (旧実装は e.is_file()/e.is_dir() で 1 ファイルにつき 2 回 stat していた)。
        file_count = 0
        has_child_dirs = False
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir():
                            has_child_dirs = True
                        elif e.is_file():
                            file_count += 1
                    except OSError:
                        continue
        except OSError:
            file_count, has_child_dirs = 0, False
        subfolders.append(SubFolder(d.name, d, alt, file_count, has_child_dirs))

    return CaseScan(root_path=path, subfolders=subfolders, root_files=root_files)
