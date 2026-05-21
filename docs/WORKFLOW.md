# 開発ワークフロー (本機 ↔ Win 機 往復)

## 全体像
```
[本機 Linux]                    [GitHub]              [Win 機]
  実装 / commit  ─push─→  main / tag        ─CI build─→  Release (.exe)
       ↑                      │                              │
       │                      │                              ↓
       └────pull──────────────┘  ←─push─ 修正 commit ←──業務試用
```

## 1. 本機 (Linux Ubuntu Wayland) での作業

### セットアップ
```bash
cd ~/デスクトップ/k-file
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

### Wayland 既知の制約 (k-pdf3 由来)
- F5 / Ctrl+R / F12 が Ubuntu Wayland では発火しないケースがある
- Hot-reload 系ツール (electronmon 相当) は Qt にないので、再起動で対応
- スクリーンショットは別ツール (gnome-screenshot 等) で取る

### コミット運用
- 1 機能 / 1 修正 = 1 commit 原則
- メッセージは日本語可、prefix で種別 (`feat:` / `fix:` / `chore:` / `docs:` / `perf:`)
- 例: `fix(ui): メニューバーの太字が反映されない問題を修正`

## 2. GitHub push → CI

### 通常 push
```bash
git push origin main
```
→ Actions が起動するが、リリースは作らない (test と lint のみ)。

### β タグ
```bash
# 1. version bump (src/version.py or package metadata)
# 2. commit
git commit -am "chore(release): bump to 1.0.0-beta.N"
# 3. push
git push origin main
# 4. tag
git tag v1.0.0-beta.N
git push origin v1.0.0-beta.N
```
→ Actions が PyInstaller で .exe ビルド → GitHub Releases に upload。詳細 `CI-CD.md`。

## 3. Win 機での試用 / 修正

### 試用
- Releases から `.exe` をダウンロード → 業務 PC で実利用
- 不具合があれば crash.log や再現手順を本機に共有

### Win 機側で修正する場合
- Win 機にも repo clone 済み前提
- 修正 → commit → push
- 本機側で `git pull` して同期

### 注意
- Win 機側で venv を作る場合は `.venv/Scripts/activate` (バッチ)
- Line ending: `.gitattributes` で `* text=auto eol=lf` 推奨 (Python は LF が無難)
- Win 機側の Python は 3.11 系で本機と揃える (PyInstaller の bytecode 互換のため)

## 4. 本機 pull → 続行

```bash
git fetch origin
git status            # ローカル変更が無いか確認
git pull --ff-only origin main
```

### リモートが進んでいる時の確認手順 (k-pdf3 で確立済)
1. `git fetch origin`
2. `git log --oneline -20 origin/main` でリモート差分を確認
3. ローカル未 commit が無ければ `git pull --ff-only`
4. あれば commit / stash してから pull

## 5. 事故ポイント (k-pdf3 経験)

### A. リポ Public 化 + force push
- 過去 commit に個人メアドが混入していた場合、Public 化前に `git filter-branch` で抹消
- これをやると全 commit hash が変わるため、クローン環境では `git reset --hard origin/main` 必須
- メールアドレスの混入を防ぐため、初回 commit 前に `git config user.email` を確認

### B. CI matrix race
- GitHub Actions で複数 OS 並列 build → Releases に同時 upload すると race condition で asset 欠落
- 対策: β タグでは Windows 単独 build (`docs/CI-CD.md` 案 B-2 参照)

### C. 「後で」仮説 (autoUpdater 系)
- k-pdf3 では autoUpdater「後で」を選ぶと部分 DL 残留 → 次回起動クラッシュの仮説あり
- k-file は当面 autoUpdater 無しなので無関係だが、将来導入時は注意

### D. クラッシュ診断ロガー
- β フェーズでは詳細ログを常時記録 (stable リリース時に撤去予定)
- k-pdf3 と同様、`crash.log` に `<timestamp> <event> <data>` 形式で append

## 6. 業務並走テスト
- β.5 以降 (k-pdf3 流) はテスター数名に配布
- 業務での実利用をテスト
- 重大バグ無く 1-2 週間運用できれば stable へ
