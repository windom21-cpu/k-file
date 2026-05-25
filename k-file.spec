# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for k-file
# 配布形態: --onedir (β/stable 共通) — K-SystemZ から繰り返し起動した時の
# --onefile 展開コスト (3〜10 秒) を回避するため、2026-05-25 連携検討で
# --onedir に切替。配布物は `dist/k-file/` フォルダごと (zip で頒布)。

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['.'],   # repo root を sys.path に含めて `from src.ui...` を解決
    binaries=[],
    datas=[
        ('resources/style/win95.qss', 'resources/style'),
        ('resources/icons', 'resources/icons'),
    ],
    hiddenimports=[
        # send2trash は file_ops 内で関数ローカル import (lazy) のため
        # 静的解析で取りこぼされないよう明示
        'send2trash',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # ← --onedir: bin/datas は COLLECT() に回す
    name='k-file',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icons/favicon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='k-file',           # → dist/k-file/ に展開される
)
