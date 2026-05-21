# CI / CD — GitHub Actions + PyInstaller

## 全体方針
- Windows 専用配布なので `windows-latest` runner のみ
- β タグ (`v*-beta.*`) で .exe ビルド + Releases upload
- 通常 push は test / lint のみ (Releases 作らない)
- 配布は GitHub Releases に直接 upload (k-pdf3 のような separate releases repo は当面不要)

## ワークフロー雛形

`.github/workflows/build.yml` (新規作成時の出発点):

```yaml
name: build

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install pytest
      - run: pytest

  build:
    needs: test
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: windows-latest
    permissions:
      contents: write          # Releases upload に必要
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install pyinstaller
      - name: Build .exe
        run: pyinstaller k-file.spec
      - name: Upload to Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/k-file.exe
          prerelease: ${{ contains(github.ref, '-beta.') || contains(github.ref, '-alpha.') }}
```

## PyInstaller spec

`k-file.spec` (初稿、最小):

```python
# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('resources/style/win95.qss', 'resources/style'),
        # ('resources/fonts/MS_UI_Gothic.ttf', 'resources/fonts'),  # 同梱フォントがあれば
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter'],     # 不要モジュールを除外してサイズ削減
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name='k-file',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # GUI app は False
    disable_windowed_traceback=False,
    icon='resources/icon.ico',
)
```

### `--onefile` vs `--onedir`
| | onefile | onedir |
|---|---|---|
| 配布 | .exe 1 個 | フォルダ |
| 起動速度 | 遅い (展開する) | 速い |
| ファイルサイズ | 圧縮されて小さく見える | 実態と同じ |
| 推奨 | β 配布 / テスター用 | 業務本番運用 |

→ **β は `--onefile` (DL が単一 .exe で楽) / stable は `--onedir` を installer (Inno Setup 等) でくるむ** が無難。k-pdf3 が installer 配布なのと整合。

## 過去のハマりポイント (k-pdf3 由来)

### A. CI matrix race
- 複数 OS で同時に Releases へ upload すると asset 欠落
- 対策 B-2: β タグでは Windows のみ runner で build
- 上記の `build.yml` は既に Windows 単独なので OK

### B. PAT scope
- GitHub Actions が repo 外 (例: releases 専用リポ) に push する場合は PAT に `workflow` scope が必要
- 単一リポなら `GITHUB_TOKEN` (Actions 自動付与) で十分

### C. Code signing
- 未署名 .exe は Win Defender SmartScreen で警告が出る (β はテスターに事前周知で OK)
- stable 時に EV コード署名証明書を検討 (年額 ~$300)

### D. 依存パッケージのバージョン固定
- `requirements.txt` は `==` でピン留め (`pyside6==6.7.2` 等)
- 開発機と CI で同じバージョンを使う
- 不意の minor update でビルド失敗を防ぐ

### E. アイコン
- `resources/icon.ico` を用意 (.ico 形式、複数解像度埋め込み)
- ImageMagick: `convert icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico`
- PNG から自動変換するワークフロー (k-pdf3 で採用) も可

## stable リリース時の cleanup
- β フェーズで仕込んだ crash.log 系ロガーを撤去
- `prerelease: true` を `false` に
- `--onedir` + Inno Setup installer 化を検討
- (将来) Code sign 導入
