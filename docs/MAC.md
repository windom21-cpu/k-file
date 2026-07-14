# macOS 対応 (Apple Silicon)

2026-07-10 着手。Windows が主本番であることは変わらず、macOS は第 2 の配布対象。
対象は **Apple Silicon (M1 以降) のみ**、Intel Mac は対象外。
方式・フォント等の基本方針は 2026-07-08 セッションで確定済 (HANDOVER.md §8
2026-07-08 の項): **mac ビルド (PySide6) 一択 / WEB 版不採用 / フォントは
IPAゴシック同梱案 / Mac では描画モード「中間/なめらか」既定**。

このファイルは **Mac 実機側で開く新セッションの一次資料**。事務所の Mac では
セッションを分けて作業するため、Linux 本機との引き継ぎはこのファイル + git 経由で行う。

> **Mac セッションの AI への指示 (ユーザー依頼 2026-07-10)**: このファイルを
> 読んだら、最初に下の「Mac 実機での入手・起動手順」を **そのままユーザーに
> 番号付きで案内する** こと (ユーザーはプログラミング素人前提。artifact の
> DL 場所は URL 付きで、`xattr` はコピペできる完成形コマンドで示す)。
> 起動に成功したら「Phase 2 チェックリスト」を一緒に上から順に進め、結果
> (特にフォントの見え方のスクリーンショット) を記録する。

## 全体ロードマップ

| Phase | 内容 | 状態 |
|---|---|---|
| 1 | CI に build-mac ジョブ + spec の darwin 分岐 (.app 化) | ✅ 2026-07-10 実装 |
| 2 | Mac 実機での挙動確認・修正の往復 (下のチェックリスト) | ✅ 2026-07-10 完了 (下記結果) |
| 3 | フォント同梱 (IPAゴシック) + Mac 用自動アップデート (シェルスクリプト版 updater) | フォント ✅ 2026-07-10 / updater ✅ 2026-07-15 実装 (実機確認待ち) |
| 4 | 署名・公証 (Apple Developer Program、年 99 ドル) — **自分専用なら不要**、事務所内配布を始める段で検討 | ⬜ |

## 仕組み (Phase 1 で入れたもの)

- `k-file.spec` — darwin では icon 無し + `BUNDLE` で `dist/k-file.app` を追加生成
  (`NSHighResolutionCapable` で Retina ぼやけ防止)
- `.github/workflows/build.yml` の `build-mac` ジョブ — `macos-latest` (arm64) で
  PyInstaller → `ditto` で `k-file-macos.zip` に固める → artifact / Release upload。
  Windows と同じく **test ジョブ緑が条件** (`needs: test`)

## 自動アップデート (Mac 版、2026-07-15 実装)

Windows と同じ「起動時チェック → バナー → [更新...] → DL → 再起動して適用」が
**Mac でもボタン 1 つで**動く。ブラウザで DL して差し替える手順はもう要らない。

Win 版との違いは実行系だけ:

| | Windows | macOS |
|---|---|---|
| 配布物 | `dist/k-file/` フォルダ | `k-file.app` バンドル 1 個 |
| asset | `k-file-windows.zip` | `k-file-macos.zip` (+ `.sha256`) |
| 展開 | `Expand-Archive` | **`ditto -x -k`** (実行権限・署名を保つ。Python の zipfile や `unzip` では .app が壊れる) |
| 適用 | PowerShell スクリプト | sh スクリプト (`write_mac_updater_script`) |
| 終了待ち | `Get-Process` ポーリング | `kill -0 $PID` ポーリング |
| 検疫 | — | **付かない** (下記) |

要点:

- **Gatekeeper の警告は出ない。** 検疫マーク (`com.apple.quarantine`) は「ブラウザ等が
  DL したファイル」に付く印で、アプリが自分で DL したファイルには付かない。よって
  手動更新で必要だった `xattr -cr` は自動更新では不要 (スクリプト側でも念のため外す)
- **失敗したら旧版を起動し直す。** 展開失敗・差し替え失敗はロールバックして旧
  `k-file.app` を `open` する (ユーザーを取り残さない)。経緯は
  `~/.config/k-file/updates/updater.log`
- **書き込めない場所には入れない。** `/Applications` (root 所有) に置くと差し替え
  できないため、k-file 終了前に権限を確認して警告を出す。**`~/Applications` に置くこと**
- Release に Win/Mac 両方の zip が載るので、asset は OS で選び分ける
  (`platform_asset_name`)。他 OS の zip・ハッシュは構造的に掴まない
- 表示倍率変更後の自動再起動も Mac 版 (`write_mac_relaunch_script`) で動く

⚠ **v1.2.1 だけは手動 DL が必要** (この機能を積んだ版を入れるまでは自動更新が無いため)。
v1.2.1 以降は Mac もアプリ内更新。


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
   - 補足 (2026-07-08 方針): Gatekeeper の審査は「DL 品の初回起動」のみ。将来の
     Mac 用自動アップデートでアプリ自身が DL する zip には検疫マークが付かない
     ため、初回さえ通せば以後は警告なしの見込み。自分専用の間は署名課金不要
4. 起動しない・即落ちする場合はターミナルから直接実行してエラーを見る:
   ```bash
   /path/to/k-file.app/Contents/MacOS/k-file
   ```
   出力をそのまま報告 (コピペ) すれば Linux 側セッションで解析できる

## Phase 2 チェックリスト (Mac 実機で確認する項目)

Win 機の実機検証と同じ型。**実機でしか出ない挙動** を潰す。
**✅ 2026-07-10 Mac 実機 (Apple Silicon) セッションで全項目クリア (ユーザー確認)。**

- [x] 起動してメインウインドウが出る (Gatekeeper 回避後) — `xattr -cr` で起動、
      ターミナル起動でもエラー出力なし
- [x] フォント / 見た目 — **この Mac ではゴシック系が入っており表示崩れなし
      (ユーザー確認)**。代替フォント環境 (素の Mac) での検証は未実施のため、
      IPAゴシック同梱 (Phase 3、確定方針) は引き続き実施する。描画モードの
      Mac 既定「なめらか」切替も Phase 3 のまま
- [x] frameless ウインドウ: タイトルバードラッグ移動 / 全辺・全角リサイズ — 問題なし
- [x] ツール→設定 で ksystemz.db のパス指定 → 事件検索・タブが開く — 問題なし。
      この Mac の実パスは `~/Library/CloudStorage/Dropbox/K-system/ksystemz/ksystemz.db`、
      `office_info.doc_root_path_mac` は実パスと一致していることを sqlite RO で確認済
- [x] Inbox 監視先の設定 (Mac のデスクトップ) と一覧表示 — 問題なし
- [x] 投入 Option+数字 / D&D / 右クリック + Ctrl+Z Undo + F12 履歴 — いずれも問題なし
      (ダミー事件フォルダ + テストファイルで確認)
- [x] Del でゴミ箱送り → Finder のゴミ箱に入る — 問題なし
- [x] PDF / 画像プレビュー — 問題なし
- [x] コピー → Finder に貼り付け — 問題なし
- [x] 更新通知バナーが出ない (Mac では無効化済) こと — 出ない
      ※ 2026-07-15 に Mac 自動更新を実装 → この項目は下の Phase 3 チェックに置き換わる
- [x] Dropbox 上の事件フォルダ操作のフリーズ (ADR-29/30 の前科) — **Win でフリーズ
      した実績のあるフォルダを開いてプレビューしても発生せず (ユーザー確認
      2026-07-10)**。オンラインのみファイルの DL 遅延は業務並走で継続観察

## Phase 3 チェックリスト (自動アップデート、Mac 実機で確認する項目)

**v1.2.1 を手動で入れた後**、次の版 (v1.2.2 以降) を出したときに確認する。

- [ ] 起動 1.5 秒後にステータスバーへ更新バナーが出る
- [ ] [更新...] → DL 進捗 → 「再起動して適用しますか？」→ はい で k-file が閉じ、
      5-10 秒で新版が自動起動する
- [ ] 起動した新版のバージョンが上がっている (ヘルプ → k-file について)
- [ ] **Gatekeeper の警告が出ない** (アプリ内 DL には検疫マークが付かないため)
- [ ] タブ・ウインドウサイズが更新後も復元される
- [ ] 表示倍率を変えたとき Mac でも自動再起動して反映される (relaunch スクリプト)
- [ ] 失敗時: `~/.config/k-file/updates/updater.log` に経緯が残り、旧版が起動し直す

### Phase 2 で見つけて直したもの

- **ウインドウ内メニューバーが macOS で表示されない** (fix commit `4b21694`):
  親なし `QMenuBar()` は cocoa でグローバルメニューバー扱いになり、しかも一度
  native 扱いになると `setNativeMenuBar(False)` を後から呼んでもレイアウトに
  乗らず非表示のままになる。生成時に親 widget を渡して回避 (Windows/Linux 無影響)。

### Mac 実機側の開発環境 (2026-07-10 構築)

- リポジトリ: `~/Desktop/k-file` (clone 済)、venv: `.venv` (Python 3.14 +
  PySide6 6.11.1 + pytest)。テスト 184 件は Mac でも全緑 (Win の symlink skip 2 件も
  Mac では走る)。ソース起動: `.venv/bin/python -m src.main`
- ビルド版: `~/Applications/k-file.app` (CI artifact を検疫解除して設置。
  メニューバー修正入り run 29084263448 のもの)

問題を見つけたら: スクリーンショット + 再現手順を控えて、Mac 側セッションで修正
できるものは修正して push、大きいものは Linux 本機セッションに持ち帰る
(HANDOVER.md の流儀と同じ)。

## IPAゴシック同梱フォールバック (✅ 2026-07-10 実装)

方針をユーザー決定で一部更新: **システムに MS Gothic があればそれを優先し、
無い環境だけ同梱 IPAゴシックへフォールバック** する (常時 IPA ではない)。

- `src/ui/font_fallback.py` — `ensure_gothic_fallback`: MS Gothic / MS UI Gothic
  が QFontDatabase に揃っていれば何もしない (従来環境は完全無変化)。欠けて
  いれば `resources/fonts/ipag.ttf` を addApplicationFont して
  `QFont.insertSubstitution` で欠けた family の解決先にする。main.py が
  QApplication 生成後・QSS 適用前に呼ぶ
- `resources/fonts/` — ipag.ttf (IPA ゴシック v003.03) + IPA フォント
  ライセンス v1.0 全文 + Readme を同梱 (再配布条件)。spec の datas にも追加
- テスト 4 件追加 (`tests/test_font_fallback.py`、184→188)。両経路を
  PREFERRED_FAMILIES の monkeypatch で強制
- 検証メモ: この Mac は Office 由来の MS Gothic / MS UI Gothic が実在する
  ことを QFontDatabase で確認済 → フォールバック不発 (= 表示崩れが無かった
  理由)。素の Mac での実機確認は未実施 (欠落経路はテストで担保)

## 既知の未対応 (Phase 3 以降)

- Mac 用自動アップデート (現状は手動 DL。PowerShell updater →
  シェルスクリプト + .app 差し替えへの書き直しが最大の作業 — 2026-07-08 見積)
- .icns アプリアイコン (現状は PyInstaller 既定アイコン)
- 署名・公証 → Gatekeeper 警告の根治 (有料。自分専用の間は不要)
- キーボードショートカットの Mac 流儀 (Ctrl↔Cmd) の整理 — 実機確認の結果次第
- Inbox 監視先など X: ドライブ前提のパス設定の Mac 用持ち直し (設定ダイアログで吸収)
