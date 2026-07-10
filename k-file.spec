# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for k-file
# 配布形態: --onedir (β/stable 共通) — K-SystemZ から繰り返し起動した時の
# --onefile 展開コスト (3〜10 秒) を回避するため、2026-05-25 連携検討で
# --onedir に切替。配布物は `dist/k-file/` フォルダごと (zip で頒布)。
#
# macOS (Apple Silicon): 同じ spec で BUNDLE を追加生成し `dist/k-file.app` を
# 作る (CI の build-mac ジョブが zip 化)。icon は .ico が Win 専用のため
# darwin では付けない (.icns 化は署名/公証と同じく後続フェーズ)。

import sys

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['.'],   # repo root を sys.path に含めて `from src.ui...` を解決
    binaries=[],
    datas=[
        ('resources/style/win95.qss', 'resources/style'),
        ('resources/icons', 'resources/icons'),
        # IPAゴシック (MS Gothic 欠落環境のフォールバック) + ライセンス全文
        ('resources/fonts', 'resources/fonts'),
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
    icon='resources/icons/favicon.ico' if sys.platform == 'win32' else None,
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

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='k-file.app',
        icon=None,
        bundle_identifier='com.windom21.kfile',
        info_plist={
            # Retina で等倍のぼやけ描画にならないようにする
            'NSHighResolutionCapable': True,
        },
    )
