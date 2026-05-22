# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for k-file
# 配布形態: --onefile (β 配布 / テスター用、stable は --onedir + Inno Setup 予定)

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['.'],   # repo root を sys.path に含めて `from src.ui...` を解決
    binaries=[],
    datas=[
        ('resources/style/win95.qss', 'resources/style'),
        ('resources/icons', 'resources/icons'),
    ],
    hiddenimports=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
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
