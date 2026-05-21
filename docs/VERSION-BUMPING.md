# バージョン運用 — マイルストーン制 alpha / beta / stable

k-pdf3 で確立されたマイルストーン制を踏襲する。

## 大方針

| 段階 | バージョン形式 | 配布範囲 |
|---|---|---|
| 開発初期 | `0.x.y` (タグなし or alpha タグ) | 本機のみ |
| 機能組み上げ | `1.0.0-alpha.N` (M2〜M5 で打つ) | 本機 + Win 機セルフテスト |
| 業務並走テスト | `1.0.0-beta.N` (M5 完了で開始) | テスター数名に配布 |
| 安定版 | `1.0.0` (M6 完了で) | 業務本番 |

## マイルストーン定義 (例、アプリ詳細で調整)

- **M1**: スケルトン (起動、空ウインドウ、Win95 QSS 適用)
- **M2**: コア機能 1 (主機能の最小実装)
- **M3**: コア機能 2 + 永続化
- **M4**: 周辺機能 + メニューバー / ツールバー完成
- **M5**: 機能網羅 + 配布パッケージング完成 → **β 開始**
- **M6**: 業務並走テスト 1-2 週間で重大バグ無し → **stable**

各 M 完了時に alpha タグを打つ。M5 完了で beta 切替、M6 完了で `v1.0.0` stable。

## β 期間の運用ルール

- β.N で「軽微バグ即修正サイクル」を 30 分で回せる体制
- 報告 → 原因仮説 → 1-2 commit で修正 → β.N+1 配布 → 配布後ログ確認
- 機能追加は β.N+M の M を大きくとってまとめる
- 業務凍結級バグの修正を機能追加より優先

## β リリース手順 (本機 Linux で実施)

```bash
# 1. 修正 commit
git add ...
git commit -m "fix: ..."

# 2. version bump (src/version.py 等)
# 例: __version__ = "1.0.0-beta.5"
git add src/version.py
git commit -m "chore(release): bump to 1.0.0-beta.5"

# 3. push
git push origin main

# 4. tag
git tag v1.0.0-beta.5
git push origin v1.0.0-beta.5
```
→ Actions が `windows-latest` で PyInstaller → Releases に upload (~5 分)。

## stable 移行の判断基準

以下が揃ったら `v1.0.0` を切る:

- [ ] 業務並走テスト 1-2 週間で重大バグ報告なし
- [ ] β フェーズで仕込んだ crash.log 系の診断コードを撤去
- [ ] PyInstaller を `--onedir` + Inno Setup 化 (β は `--onefile` でも、stable は installer 推奨)
- [ ] icon.ico を最終版に
- [ ] README / HANDOVER.md を「現状: stable 配布中」に更新 (ユーザー明示依頼時)
- [ ] code signing 検討 (EV 証明書または当面未署名)

## アンチパターン

- ❌ マイルストーン未達なのに alpha → beta に進める
- ❌ β.N の前後で大規模 refactor (構造変更は M ジャンプの口実に)
- ❌ commit メッセージに version bump 以外を混ぜる (`chore(release):` は単独で)
- ❌ tag 後に force push で書き換える (テスター側でハッシュ不整合)
- ❌ HANDOVER.md を β タグ毎に自動更新する → 明示依頼時のみ

## k-pdf3 の参考実績
- β.1 (2026-05-10) 配布開始 → β.126 (2026-05-21) で 11 日間 / 126 リリース
- 各 β は数十分〜数時間サイクルが多い。「機能追加 β」と「hotfix β」が混在
- β 卒業はまだ。M6 = annotation proxy / qpdf / 真の墨消し / etc 完了し、業務並走テストで重大バグ無し確認待ち
