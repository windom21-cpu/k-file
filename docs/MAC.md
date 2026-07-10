# macOS 対応 (Apple Silicon)

2026-07-10 着手。Windows が主本番であることは変わらず、macOS は第 2 の配布対象。
対象は **Apple Silicon (M1 以降) のみ**、Intel Mac は対象外。

このファイルは **Mac 実機側で開く新セッションの一次資料**。事務所の Mac では
セッションを分けて作業するため、Linux 本機との引き継ぎはこのファイル + git 経由で行う。

## 全体ロードマップ

| Phase | 内容 | 状態 |
|---|---|---|
| 1 | CI に build-mac ジョブ + spec の darwin 分岐 (.app 化) | ✅ 2026-07-10 実装 |
| 2 | Mac 実機での挙動確認・修正の往復 (下のチェックリスト) | ⬜ 次 |
| 3 | 配布形態確定 + Mac 用自動アップデート (shell script 版 updater) | ⬜ |
| 4 | 署名・公証 (Apple Developer Program、年 99 ドル、任意) | ⬜ |

## 仕組み (Phase 1 で入れたもの)

- `k-file.spec` — darwin では icon 無し + `BUNDLE` で `dist/k-file.app` を追加生成
  (`NSHighResolutionCapable` で Retina ぼやけ防止)
- `.github/workflows/build.yml` の `build-mac` ジョブ — `macos-latest` (arm64) で
  PyInstaller → `ditto` で `k-file-macos.zip` に固める → artifact / Release upload。
  Windows と同じく **test ジョブ緑が条件** (`needs: test`)
- 自動アップデートは **Mac では無効** (`UpdateManager.check_async` が win32 以外で
  即 return)。updater が PowerShell + `k-file-windows.zip` 前提のため。
  Mac の更新は当面「新しい zip を手動 DL して差し替え」

## Mac 実機での入手・起動手順

1. zip の入手:
   - タグ版: https://github.com/windom21-cpu/k-file/releases から `k-file-macos.zip`
   - 最新 main: リポジトリの Actions → 該当 run → Artifacts → `k-file-macos`
2. zip をダブルクリックで展開 → `k-file.app` が出る。アプリケーションフォルダに
   置かなくてもよい (任意の場所で動く)
3. **初回起動 (Gatekeeper 回避が必要)**: 署名していないため、普通にダブルクリック
   すると「壊れているため開けません」「開発元を検証できません」等が出る。
   - 方法 A: Finder で k-file.app を **右クリック (control+クリック) → 開く** →
     警告ダイアログで「開く」。最近の macOS (Sequoia 以降) ではこれでも弾かれる
     ことがあるので、その場合は方法 B
   - 方法 B: ターミナルで隔離属性を外す:
     ```bash
     xattr -cr /path/to/k-file.app
     ```
     (パスは k-file.app をターミナルに D&D すれば入る)
   - 2 回目以降は普通にダブルクリックで起動できる
4. 起動しない・即落ちする場合はターミナルから直接実行してエラーを見る:
   ```bash
   /path/to/k-file.app/Contents/MacOS/k-file
   ```
   出力をそのまま報告 (コピペ) すれば Linux 側セッションで解析できる

## Phase 2 チェックリスト (Mac 実機で確認する項目)

Win 機の実機検証と同じ型。**実機でしか出ない挙動** を潰す。

- [ ] 起動してメインウインドウが出る (Gatekeeper 回避後)
- [ ] フォント / 見た目: MS Gothic ビットマップが Retina でどう見えるか
      (ドット感が保てているか、ぼやけ・にじみがないか)。必要なら
      表示→文字の描画 の 3 段階切替 (ADR-31) で好みを探る
- [ ] frameless ウインドウ: タイトルバードラッグ移動 / 全辺・全角リサイズの掴み心地
      (ADR-32/33 の自前実装が macOS で動くか)
- [ ] ツール→設定 で ksystemz.db のパス (Mac 上の Dropbox 内) を指定 → Ctrl+O
      (Mac では Cmd+O になっていないかも確認) で事件検索・タブが開くか
      — 事件フォルダ解決は `office_info.doc_root_path_mac` を読む (実装済)。
      値が Mac の実パスと合っているかは K-SystemZ 側で要確認
- [ ] Inbox 監視先の設定 (Mac のスキャン先 / デスクトップ / 作業フォルダ) と一覧表示
- [ ] 投入 (Alt+0〜9 — Mac では Option+数字。効かない場合は要報告) / D&D / 右クリック
- [ ] Del でゴミ箱送り → Finder のゴミ箱に入るか / 編集→ごみ箱を開く
- [ ] PDF / 画像プレビュー、プレビュー中のファイル操作 (rename / 移動)
- [ ] Dropbox 上の事件フォルダ操作でフリーズしないか (Win で ADR-29/30 の前科あり。
      Mac の Dropbox はオンラインのみファイル = ダウンロード遅延があり得る)
- [ ] 更新通知バナーが出ない (Mac では無効化済) こと

問題を見つけたら: スクリーンショット + 再現手順を控えて、Mac 側セッションで修正
できるものは修正して push、大きいものは Linux 本機セッションに持ち帰る
(HANDOVER.md の流儀と同じ)。

## 既知の未対応 (Phase 3 以降)

- Mac 用自動アップデート (現状は手動 DL)
- .icns アプリアイコン (現状は PyInstaller 既定アイコン)
- 署名・公証 → Gatekeeper 警告の根治 (有料)
- キーボードショートカットの Mac 流儀 (Ctrl↔Cmd) の整理 — 実機確認の結果次第
