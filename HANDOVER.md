# k-file 引き継ぎドキュメント

このファイルは AI セッション間でプロジェクトの現状を引き継ぐための master document。
**ユーザー明示依頼時のみ更新する。マイルストーン完了の都度自動更新しない。**

---

## 現状サマリ
- 現在地: **M5f (フリーズ根治セッション Phase 1) 完了 (2026-05-29)。プレビュー読込を別スレッド化してフリーズを修正、main push 済 (commit `5a46013`、CI 成功 = artifact `k-file-windows` 48MB)。ユーザーが実機で様子見中**
  - M1〜M5b 完了 → 2026-05-25 1 回目 Win 機本番テスト → M5c で業務凍結級バグ + 設計修正 → 2026-05-26 2 回目検証 → M5d で消化 → 2026-05-27 M5e で β 直前 polish + 自動アップデート機構 (案②) → `v0.1.0-beta.1` タグ切り → 2026-05-29 M5f で「ファイルクリック / 移動・リネーム後にアプリが固まる」フリーズを調査・Phase 1 修正
  - **フリーズの主因 = 事件フォルダ (= Dropbox を X ドライブにレジストリマウント) 上のファイルの同期 I/O (read/stat) がメインスレッドをブロック** (詳細 §15 ADR-29)。Inbox は全てローカルなので無傷で、事件 (X:) 側操作で固まる非対称と一致
  - 2 回目検証で .k-photo (= 実際は `.kphoto` / `.kevi`) プレビュー / デスクトップフォルダ移動 / IPC ウインドウ単一性 / 日本語名・case_code 衝突 系は **問題なし** と判明
  - **本機 = Win 機**。CLAUDE.md / 旧記述の「本機 = Linux」は実態とズレ (2026-05-29 ユーザー確認、開発も配布確認もこの Win 機で実施)
- スタック: Python + PySide6、PyInstaller `--onedir` + zip 配布 (M5c で `--onefile` から切替、起動 3-10 秒→1 秒)
- UI 方針: Windows95/98 風 (**MS Gothic 12pt 埋め込みビットマップ** / 灰色 / beveled / 高密度業務アプリ感)
- リポジトリ: https://github.com/windom21-cpu/k-file (public)
- 配布: GitHub Releases (zip、`dist/k-file/` フォルダごと) + **自動アップデート機構 (案②)** で起動時通知 → 1 クリック DL → 再起動で新版反映
- テスト: **112 件** (`tests/test_file_ops.py` / `test_undo_ops.py` / `test_inbox_watcher.py` / `test_case_repo.py` / `test_version.py` / `test_updater.py` / `test_preview.py`) 全緑。ローカル Win venv で実行: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest`。CI (build.yml) は pytest を走らせず .exe ビルドのみ

---

## 0. このドキュメントの読み方

最低限読む順:
1. このページ冒頭 (現状サマリ)
2. §1 プロジェクトの全体像
3. §2 設計思想と禁止事項
4. §3 協働方針 → `docs/COLLABORATION.md` も
5. §6 開発ロードマップ / マイルストーン
6. §15 確定した設計判断 (ADR)
7. §8 次にやること

---

## 1. プロジェクトの全体像

### 何を作るか
**案件ドキュメント作業台** — 法律実務に特化した **2/3 ペイン型ファイラー**。
未整理 PDF・画像・FAX 結果・スキャン文書 (Inbox 側) と複数の事件フォルダ (出ていく側) を横並びで一体表示し、Inbox から事件サブフォルダへの投入を最速で行う。同時に各事件フォルダタブは小型ファイラーとして機能し、ファイルの閲覧・既定アプリで開く・名前変更・削除・事件をまたぐ移動など **通常のファイル操作も完備** する。

「紙の机・事件棚・未処理トレー」をデジタル上で再構築する。Explorer の完全代替は目指さないが、**案件文脈の中では Explorer を開かなくても済む** 状態を維持する。そのため任意のフォルダもタブで開ける汎用ファイラー機能を併せ持つ (詳細 §2 / §15 ADR-2)。

### 想定運用
- 日常的に scan / Desktop / 作業フォルダに集積される未整理ファイルを、**統合 Inbox** で一覧
- 進行中の事件 (5〜15 件程度) を **タブで同時に開いておく** — 各事件フォルダは小型ファイラー
- Inbox から事件のサブフォルダ (`1_文書 / 2_発信 / 3_受信 / 4_資料 / 5_申立書類 / 6_訟務資料`) へ **Alt+0〜9 / 右クリックメニュー / D&D で投入** (rename ダイアログ → Enter 確定)
- 事件をまたぐ移動・事件内での整理・既定アプリで開く等もこのツール内で完結

事件フォルダ自体は既存事件管理システム **K-SystemZ** が管理しており、本ツールはこれを **読み取り専用で参照** する (詳細 §4)。本ツールは事件管理そのものは行わない。

### 何を作らないか
- Explorer の完全置換 (任意フォルダもタブで開けるが、フォルダ既定ハンドラの OS 乗っ取りはしない — §15 ADR-2)
- 事件管理機能 (K-SystemZ の領分)
- モダン Web 風 / ミニマル / マテリアル UI
- クラウド連携 (ローカル完結)
- 独自ファイル形式 (実ファイル主義)
- タッチ UI / アニメーション / 半透明 / ダークモード
- ツリービューによる事件フォルダ表示 (200 ファイル/事件規模で見にくいため禁止、サブフォルダタブ + フラット一覧で実装)

---

## 2. 設計思想と禁止事項

### 不変の制約
- **アクティブな事件タブ = 閲覧かつ投入先**。「投入先」を別概念として持たず、現在開いているタブそのものが投入先となる。これにより操作は最速 (タブ切替 = 投入先切替)。
- **誤投入対策は「可視化 + 回復」で担保** (「確認」ではない):
  - アクティブタブを強い色 (紺地白文字 + 事件ごと自動配色 + 太字) で目立たせる
  - タブ名そのものに事件名が出ているので、投入時の視覚的確認が常時成立
  - **投入履歴 (F12)** — サムネイル付きの全投入操作リスト。各行から個別 Undo 可能
  - **Ctrl+Z** で直前操作の Undo
- **6 分類は基本スキーマ**。事件フォルダ内のサブフォルダを **実フォルダから動的読み取り** し、`\d_.*` パターンの先頭 9 個を **Alt+1〜9 に順に繰り上げ割当** (欠番があれば次のものが上がる)。10 個目以降のサブフォルダは Alt 割当なし・クリック専用。
- **事件フォルダの中身はサブフォルダボタン + フラット一覧** で表示 (ツリー禁止、200 ファイル/事件規模で見にくいため)。サブフォルダボタンには件数バッジを付ける。
- **サブフォルダ操作は「左クリック＝閲覧 / Alt・右クリック＝投入」で分離** (詳細 §15 ADR-1):
  - 左クリック = そのサブフォルダの中身を表示するだけ (ファイルは動かさない)
  - Alt+0〜9 = 選択中の Inbox ファイルを投入。右クリックメニュー / D&D もマウス投入手段
- **「事件フォルダ直下」ビュー** (Alt+0、ボタン番号 0): どのサブフォルダにも入っていない事件フォルダ直下のファイルを表示。Explorer を開かず直下ファイルを扱えるようにする。
- **サブフォルダ内のネストフォルダはファイル一覧に「フォルダ行」として表示** (詳細 §15 ADR-3): 子フォルダを一覧先頭に行で並べ (フォルダアイコン + サイズ欄「フォルダ」)、ダブルクリックで中へ入る。戻るはパンくず (「事件フォルダ:」バーを拡張)。何階層でも可。縦一覧なので子フォルダが多くてもスクロールで対応。ツリービューではない (常に 1 フォルダのフラット一覧)。
- **投入操作は「Copy → 検証 → 元削除」を 1 アクション**: 途中失敗時は元ファイルが残るため安全。Undo で完全復元可能。
- **投入時にファイル名を rename** (Enter で確定、**Esc で「元名のまま投入」を確定**、最近使った名前を候補表示)。
- **ファイル名衝突は自動連番 + ステータスバー通知** (例: `受領書.pdf` 既存なら `受領書 (2).pdf`、通知「衝突を回避して (2) を付与」)。確認ダイアログは出さない。
- **削除は OS ごみ箱 + 自前履歴** のハイブリッド。Del キーで OS のごみ箱に送りつつ drop_history に経路記録、Ctrl+Z で復元試行 (失敗時は「OS のごみ箱から手動復元してください」と通知)。
- **事件をまたぐ D&D は Move** (Dropbox 30 日履歴 + 自前 Undo が保険)。
- **UI は Win95/98 業務アプリ感を絶対遵守** (詳細 `docs/UI-PRINCIPLES.md`)。タイトルバーも自作 (Frameless + 自前タイトルバーウィジェット)。
- **K-SystemZ DB は読み取り専用** (`mode=ro`)。k-file 自身の状態は別 DB (`kfile.db`) に持つ。

### Inbox 表示ルール
- デフォルトは PDF + 画像 (jpg/png/tiff) のみ。`.lnk` / `.txt` / フォルダ等は非表示。
- ファイル単位の「無視」フラグで個別除外 (実ファイルは触らない)。
- 更新日時フィルタを設定可能 (例: Desktop は「7日以内」)。
- 監視対象 (scan / Desktop / 作業フォルダ) は **(c) ハイブリッド**: デフォルトは統合一覧 + 出所列で識別、フィルタタブ (全て / scan / Desktop / 作業) で出所別に絞り込み可能。

### 事件フォルダの取得方針
- **K-SystemZ DB を読んで事件リスト** を持つ (案件名・case_code・依頼者名で検索)
- **タブ追加経路** (M5/M6 で実装):
  - 「事件を開く」ダイアログ (Ctrl+O) — 検索 → 選択
  - フォルダを k-file ウインドウに **D&D** で追加
  - コマンドライン引数: `k-file.exe "C:\path\to\folder"` — K-SystemZ や他ツールからの呼び出し用
  - Explorer 右クリック「k-file で開く」 — Windows シェル拡張で登録 (M6 polish)
- **K-SystemZ 側改修は必須ではない** (上記コマンドライン引数で十分連携可能)。

### 禁止事項
- HANDOVER.md の勝手更新 (明示依頼時のみ)
- レトロ UI 方針からの逸脱
- 確認ダイアログの追加 (Undo・履歴で対処)
- K-SystemZ DB への書き込み (RO 厳守、Dropbox 同期下のため競合リスク)
- 独自ファイル形式の導入 (実ファイル主義)
- ツリービューでの事件フォルダ表示 (常に「サブフォルダボタン + フラット一覧」、ネストはフォルダ行 + ドリルダウン)
- サブフォルダボタンのクリックでの投入 (クリックは閲覧専用、誤投入防止 — §15 ADR-1)
- 巨大な抽象化 (MVP は単純さ優先)

---

## 3. ユーザーとの協働方針

詳細 → `docs/COLLABORATION.md`

要点:
- 素人前提・先回り提案・趣旨読み取り
- 長期目的を見失わない (architecture-first)
- 「分かりやすい説明」と「妥協した実装」を取り違えない

---

## 4. アーキテクチャ詳細

### レイヤ構成
- `src/ui/` — PySide6 widget 群 (Qt 依存)
- `src/core/` — ドメインロジック (Qt 非依存、ユニットテスト可能)
- `src/infra/` — 永続化・OS 連携 (SQLite、ファイル操作、外部 DB 連携)

### UI レイアウト (主画面)
```
┌─ 自作タイトルバー (Win95 風: 紺地白文字 + システムメニュー + 最小化/最大化/×) ─┐
├─ メニューバー (ファイル / 編集 / 表示 / ツール / ヘルプ) ───────────────────┤
├─ 事件タブ: ▶[A 山田 損害賠償]◀  [B ㈱A 売買]  [C 鈴木 離婚]  +  [全事件…]─┤
├──────────┬───────────────────────────────────┬────────────────────┤
│          │ R060200042 山田太郎 損害賠償      │                     │
│  Inbox   │ ─────────────────────────────    │                     │
│          │ [1_文書][2_発信][▶3_受信(5)◀]    │   プレビュー        │
│ 全/scan  │ [4_資料][5_申立][6_訟務(12)]      │   (PDF / 画像)      │
│ /Desk/作業│ ──────────────────────────       │                     │
│ ──────── │ 検索 [______]  並び順 [日付↓ ▼]  │   M2 で実装         │
│ • a.pdf  │ Name        更新日       サイズ   │                     │
│ • b.pdf  │ • 受領書    5-20    2.3MB ←選択  │                     │
│ • c.pdf  │ • 連絡書    5-19    1.1MB         │                     │
│ • d.pdf  │ • FAX結果   5-19    340KB         │                     │
│          │                                    │                     │
├──────────┴───────────────────────────────────┴────────────────────┤
│ ステータスバー: 直近 — 受領書.pdf → 3_受信 (Ctrl+Z で取消)            │
└──────────────────────────────────────────────────────────────────┘
```

### 状態モデル
- **事件タブ = 閲覧 + 投入先 (一体)**。アクティブタブの事件が常に投入先。タブ切替で投入先も切替。
- **タブ強調**: アクティブタブは紺地白文字 + 太字 + 事件ごとの自動配色枠で誤認防止。
- **同時に開くタブ**: 5〜15 が想定。100 事件の全件は「事件を開く」ダイアログで検索 (Ctrl+O)。
- **Inbox**: (c) ハイブリッド構成 — デフォルトは統合一覧 + 出所列、フィルタタブで scan/Desktop/作業 別表示。

### 主要操作
| 操作 | 方法 |
|---|---|
| サブフォルダの中身を見る | サブフォルダボタンを左クリック (閲覧のみ・投入しない) |
| Inbox → サブフォルダ投入 | Inbox で選択 → Alt+0〜9 (rename ダイアログ → Enter 確定 / Esc で元名のまま投入) |
| Inbox → サブフォルダ投入 (マウス) | サブフォルダボタンへ D&D、右クリック →「ここへ投入」、中央コマンドストリップ ▶▶ |
| Inbox 選択を無視 / 解除 | 右クリック → 「無視」、または中央コマンドストリップ ✕ |
| 親フォルダへ戻る (ネスト中) | ファイル一覧最先頭の `..` 行をダブルクリック、もしくはパンくず |
| 既定アプリで開く | ファイルでダブルクリック / Enter |
| ファイル名変更 | F2 |
| 事件フォルダ自体の名前変更 | Shift+F2 |
| プレビュー開閉 (1:1 ↔ 1:2:2) | F3 |
| 削除 | Del (確認なし、OS ごみ箱 + 自前履歴) |
| 別事件タブへ移動 | D&D = Move (Dropbox 30 日履歴 + 自前 Undo が保険) |
| Undo | Ctrl+Z |
| 投入履歴 (サムネ付) | F12 |
| 事件を開く (ダイアログ) | Ctrl+O |
| フォルダ D&D で事件タブ追加 | k-file ウインドウへフォルダを D&D |
| サイズ列 KB/MB 切替 | サイズ列ヘッダーを右クリック → メニュー |
| 列ソート | ヘッダー左クリック (両ペインとも) |

### K-SystemZ 連携
- **読み取り専用 DB 参照**: 起動時に `ksystemz.db` を `mode=ro` で開き、`cases` (case_code, case_name, status, case_type 等) と `office_info` (`doc_root_path` / `doc_root_path_mac`) を読む。
- **事件 → 実フォルダ解決**: `doc_root_path` 直下を `{case_code}*` で前方一致検索 (K-SystemZ の `GET /api/cases/{id}/open-folder` と同じロジック)。
- **タブ追加経路**:
  - 「事件を開く」ダイアログ (Ctrl+O) — ksystemz.db から事件検索 → 選択
  - フォルダを k-file ウインドウに D&D
  - コマンドライン: `k-file.exe "C:\path\to\folder"` (外部ツールからの呼び出し用、K-SystemZ 改修なしで連携可)
  - Explorer 右クリック「k-file で開く」 (M6 でシェル拡張を登録)
- **K-SystemZ 側改修は必須ではない**。任意で K-SystemZ の `os.startfile(path)` を `subprocess.Popen(["k-file.exe", path])` に変えれば自動連携できるが、必須ではない (M6 polish 扱い)。
- **書き込み厳禁**: ksystemz.db は Dropbox 同期下にあるため、k-file は絶対に書き込まない。k-file 自身の状態は別 DB (`kfile.db`) に持つ。

### コンポーネント分離 (予定)
- `core/case_repo.py` — K-SystemZ DB の RO 読み出し + 事件→実フォルダ解決
- `core/file_ops.py` — Copy→検証→元削除、Move (cross-case)、自動連番衝突回避、send2trash 削除、Undo 用履歴
- `core/inbox_watcher.py` — 監視対象フォルダの変更検知 (QFileSystemWatcher)
- `core/folder_scanner.py` — 事件フォルダ内のサブフォルダ動的取得 + `\d_.*` パターンの先頭 9 個を Alt+1〜9 に繰り上げ割当 + ネストフォルダ走査
- `infra/kfile_db.py` — k-file 専用 SQLite (kfile.db) ラッパー
- `ui/title_bar.py` — Win95 風自作タイトルバー (Frameless + 自前。minimal モードでダイアログにも流用)
- `ui/main_window.py` — メインウインドウ全体組立
- `ui/pane_header.py` — ペイン見出し (タイトル + 上下の彫り込み線) ※実装済
- `ui/inbox_pane.py` — 左 Inbox ペイン (出所フィルタ + 統合一覧)
- `ui/case_pane.py` — 中央事件フォルダペイン (サブフォルダボタン + フラット一覧)
- `ui/preview_pane.py` — 右プレビューペイン
- `ui/about_dialog.py` — Win95/98 風バージョン情報ダイアログ ※実装済
- `ui/history_view.py` — 投入履歴 (F12) サムネ付き

---

## 5. 技術スタック

| 領域 | 採用 | 備考 |
|---|---|---|
| 言語 | Python 3.11+ | Win11 標準 / 配布 runner と揃える |
| GUI | PySide6 (LGPL) | PyQt6 ではなく PySide6 (Qt for Python 公式) |
| パッケージング | PyInstaller | `--onefile` か `--onedir` は要検討 (docs/CI-CD.md) |
| CI | GitHub Actions (windows-latest) | k-pdf3 と同じ流儀 |
| 配布 | GitHub Releases | autoUpdater は当面なし、手動 DL |

---

## 6. 開発ロードマップ / マイルストーン

詳細 → `docs/VERSION-BUMPING.md`

- **M1 スケルトン (✅ 2026-05-22 完了)**: PySide6 起動 + Win95 QSS + 自作タイトルバー (14px) + 事件タブ (アクティブ強調、中央ペイン内) + 3 ペイン 1:2:2 (Inbox / 事件フォルダ / プレビュー) + 中央ペイン左右の sunken 縦枠で視覚分離 + サブフォルダボタン + 件数バッジ + 行高 14px + ステータスバー (全てダミーデータ)
- **M2 実ファイル接続 + プレビュー (✅ 2026-05-22 完了)**: 事件フォルダ実読込 (`core/folder_scanner.py`)、Inbox 実読込 + QFileSystemWatcher 自動更新 (`core/inbox_watcher.py`)、PDF/画像プレビュー + 複数ページのページ送り (QPdfView / QPixmap)、PDF + 画像フィルタ、kfile.db + 無視機能 (`infra/kfile_db.py`)、ネストフォルダのフォルダ行表示。残: 更新日時フィルタ (設定ダイアログ要・M3 以降)
- **M2 補強 — UI 詰め 2 (✅ 2026-05-23 完了)**: `..` 行 / 下部ファンクションキーバー / Shift+F2 事件フォルダ rename / F3 プレビュー開閉トグル / 動的レイアウト (Inbox 幅 ≒ ファイル一覧幅) / 中央コマンドストリップ / Inbox 列を参照フォルダに統一 + ソート / サイズ KB 統一 + 右クリックで KB/MB / Inbox 右枠と CasePane 左枠を sunken 対称化。詳細 §7
- **M3 投入 + cross-case 移動 (✅ 2026-05-23 完了)**: `core/file_ops.py` (Copy→検証→元削除 / Move / 衝突自動連番 / send2trash)、Alt+0〜9 / 右クリック / D&D で即時投入 (rename ダイアログを挟まない — ADR-7)、**F2 = 単独 rename ダイアログ** + recent_names 候補、cross-case D&D Move (同名サブフォルダ自動マッピング)、`drop_history` 記録、ステータスバー反映、Inbox 更新日時フィルタ (cutoff_days)。詳細 §7
- **M4 Undo + 削除 + 履歴 (✅ 2026-05-23 完了)**: Del / F8 / − ボタン → OS ごみ箱 (`file_ops.trash`) + 履歴記録、Ctrl+Z Undo (inject/move/rename — trash は除外 ADR-13)、↶ ボタン enable 状態管理、F12 投入履歴ビュー (テキスト版、各行から個別 Undo)、「ごみ箱を開く」(編集メニュー) で Windows ネイティブ Recycle Bin を起動。サムネは後回し
- **M5 K-SystemZ 連携 + 設定 + セッション復元 (✅ 2026-05-23 完了)**: 「事件を開く」ダイアログ (Ctrl+O) で `core/case_repo.CaseRepo` 経由の RO 検索 (cases + case_persons + persons join、active_only フィルタ)、複数事件タブ同時開き、セッション復元 (`open_tabs` テーブル)、フォルダ D&D で事件タブ追加 (mainwindow への drop イベント)、設定ダイアログ (`ui/settings_dialog.py` Inbox 監視先 / ksystemz.db パス 編集)、事件ショートカット (B 内の A symlink) のダブルクリックで A タブへ切替 (ADR-16)。起動時タブ自動 load 撤去 (ADR-15)。**ksystemz.db 本体は持ち出さずモック (`tests/fixtures/build_mock_ksystemz_db.py`) で Linux 実装 → Win 機検証フロー** (詳細 §8)。Win 機検証完了で **β タグ** (v0.1.0-beta.1) 開始予定
- **M5b UX polish (✅ 2026-05-24 完了)**: β 配布前の磨き込みセッション。詳細 §7 (M5b セクション)。主要点:
  - **MS Gothic 12pt 埋め込みビットマップを全 widget に強制適用** — Qt 既定のベクトル AA を上書き (ADR-17)
  - **複数選択対応** (両テーブル ExtendedSelection): Shift/Ctrl で多選択 → D&D / Del / Alt 投入が batch 化
  - **D&D 視覚フィードバック**: ドラッグ中の黄色付箋 + drop ターゲット強調
  - **F6 雑記録 / F7 一時保管** クイック起動 (kfile.db settings)
  - **タブキーで Inbox ↔ 中央ファイル一覧 を往復**、Enter キー / ダブルクリックで OS 既定アプリ起動
  - **ファイル一覧/タブ右クリックメニュー** (Explorer で開く / フルパスコピー / 他を閉じる 等)
  - **プレビュー上部固定ヘッダー** (ファイル名 / サイズ / 更新日 / ページ数)
  - **ステータスバー 2 分割** (左 = showMessage / 右 = 選択ファイル フルパス)
  - **ウインドウサイズ永続化**、Inbox/中央ファイル名列の幅同期 (ADR-18)、孫フォルダへ Inbox D&D 投入、KB/MB 切替時にソート維持、サブフォルダボタン末尾省略 (…)
  - **UI 整理**: 半角カタカナ メニュー (ﾌｧｲﾙ / ﾂｰﾙ / ﾍﾙﾌﾟ) と「参照ﾌｫﾙﾀﾞ」、タイトルバー = `K-FILE`、`<DIR>` (フォルダ行)、`.PDF` 大文字拡張子、削除ボタン (無視と分離)、「他事件へ」→ `↗` アイコン化、ダイアログは 9pt + raised 外縁 2px 内側マージン
- **M5c 本番テスト対応 + polish (✅ 2026-05-25 完了)**: 1 回目 Win 機本番テスト報告
  (`/home/sk/デスクトップ/260525k-fileテスト結果.txt`) を受けた緊急対応。詳細 §7。主要点:
  - **プレビューファイルロック解放**: `QPdfDocument` がファイルハンドルを保持して
    削除/移動/リネームが失敗していた業務凍結級バグ。`PreviewPane.clear()` で
    明示 close + 操作前 / F3 閉 / ウインドウ非アクティブ / Inbox↔参照フォルダ
    間 focus 切替で呼ぶ (ADR-22)
  - **タブ氏名抽出**: `R08020011文書フォルダ(田中太郎)売買` 形式の事件フォルダ
    名から「依頼者名 + 事件名」を抜き出してタブ表示 (半角/全角括弧両対応、
    旧スペース区切りも後方互換)
  - **単一インスタンス + IPC (M6b)**: `QLocalServer/QLocalSocket` (`src/ipc.py`) で
    2 つ目以降は primary にパス送信 → exit。K-SystemZ から連打しても 1 ウインドウ
    にタブ集約 (ADR-20)
  - **Inbox 設計転換**: ホワイトリスト撤去 → ブラックリスト方式
    (`.tmp/.DS_Store/Thumbs.db/desktop.ini` 等のみ除外、`.k-*` は明示的に通す)。
    フォルダも Inbox に出して Alt+0〜9/D&D/右クリックで事件サブフォルダに丸ごと
    移動可能 (`file_ops.inject` にフォルダ分岐)。Inbox フォルダ行ダブルクリックで
    事件タブとして開く (ADR-19)
  - **0KB スキャン抑制**: 0 バイト & 更新 5 秒以内は書き込み中扱いで非表示。
    `InboxWatcher` に 700ms debounce + 5.5 秒後 follow-up refresh
  - **重複ソース dedupe**: `list_inbox_files` で resolve 済みパス重複を排除
    (ユーザー設定で Desktop 行が 2 件並んで 2 倍表示される事故への保険)
  - **テキスト/JSON プレビュー**: `.txt/.log/.md/.csv/.tsv/.ini/.cfg/.json/.k-photo`
    を QPlainTextEdit で表示。JSON は indent=2 整形、64KB cap、UTF-8 → CP932 →
    latin-1 文字コードフォールバック
  - **更新列 = YY-MM-DD HH:MM** に統一 (両ペイン)、列幅 110 → 130
  - **サイズ列 = カンマ区切り + ヘッダー単位** (`ｻｲｽﾞ (KB)` / `ｻｲｽﾞ (MB)` 動的切替)
  - **K-SystemZ 連携技術対応**: ksystemz.db RO 接続と kfile.db に `PRAGMA busy_timeout=5000`、
    起動致命例外を `%APPDATA%\k-file\error.log` に追記、PyInstaller を `--onedir` 化
    + CI で zip 化して artifact / Release upload (ADR-21)
- **M5d Win 2 回目検証フォロー + cross-case Copy + K-SystemZ 連携詰め (✅ 2026-05-26 完了)**:
  2026-05-26 Win 機 2 回目検証で見つかった追加バグの修正と、ユーザー要望の
  新機能を追加。詳細 §7 (M5d セクション)。主要点:
  - **F2 リネーム Win ファイルロック根治 (ADR-23)**: M5c の `QPdfDocument.close()` だけでは
    Win 上で PDFium がファイルハンドルを保持し続けるケースが残っており、F2 → OK 時に
    「別のプロセスが実行中です」エラーで rename 失敗。`QBuffer` 経由で bytes を
    in-memory 読込みする方式に変更 → Qt 側にファイルハンドルを持たせない
  - **F2 中の preview 維持**: `_internal_modal_count` フラグで `changeEvent` の
    `ActivationChange` 経由 preview clear をスキップ。「プレビューを見ながら
    リネーム」操作を実現 (ADR-22 補足)
  - **選択ドリフト修正 (ADR-24)**: Inbox / CasePane の `_populate` で「rebuild 前
    に選択 path 集合を保存 → rebuild + sort 後に同 path を再選択」する処理を追加。
    Inbox auto refresh や rename refresh で「同じ row index = 別ファイル」になり
    意図と違うファイルを操作する事故を防ぐ。multi-select 対応
  - **cross-case Copy 動線 2 系統 (ADR-25)**: 事件 A → 事件 B にファイルをコピー
    する動線が無かった。Ctrl+D&D (Win Explorer 流儀、自動マッピング) + 右クリック
    「他事件へコピー / 移動 → サブフォルダ明示」の 2 系統で追加。`file_ops.copy`
    新設、`undo_ops` に "copy" 対応 (Ctrl+Z で dst を OS ごみ箱へ)、MainWindow に
    共通ヘルパ `_do_cross_case_op(op, target_case_root, resolver, src_paths)`
    でロジック集約
  - **K-SystemZ サブアプリ拡張子対応**: 実拡張子は `.kphoto` / `.kevi` (ハイフン
    無し) と判明 (`.k-photo` は誤称)。Inbox は既存ブラックリスト方式で問題なく
    通過するが、dotfile 例外パターンを `.k-` 始まり → `.k` 始まりに緩和、
    プレビュー JSON 対象に `.kphoto` / `.kevi` を追加 (`.k-photo` も後方互換維持)
  - **K-SystemZ 側の追従対応 (k-file 側変更不要)**: `_is_kfile_running()` 撤去
    + `psutil` 依存削除 (ADR-20 IPC 前提)、`--onedir` 配布対応マニュアル更新、
    サブアプリ JSON は絶対パス記憶なし設計で堅牢 (返信書: `X:\K-system\k-systemz向け_k-file連携状況_260526.md`)
  - **2 回目検証で問題なしと確認できた項目**: `.kphoto`/`.kevi` プレビュー、デスクトップ
    フォルダの Inbox → 事件サブフォルダ移動、IPC によるウインドウ単一性、日本語
    フォルダ名 (㈱、㊗ 等) のパス解決、case_code 前方一致衝突 — いずれも実環境で
    支障なし。残るは β タグ + 自動アップデート機構の検討のみ
- **M5e β タグ準備 polish + 自動アップデート (✅ 2026-05-27 完了、`v0.1.0-beta.1` タグ切り)**:
  Win 機 β 配布前の最終 polish と、ユーザー要望「自分で DL + 古いの消すのがだるい」を
  受けた自動アップデート機構 案② の実装。詳細 §7 (M5e セクション)。主要点:
  - **自動アップデート機構 案② 実装 (ADR-27)**: 起動時に裏で GitHub Releases API
    チェック → 新版あれば status bar に通知バナー → 「更新...」クリックで zip 自動 DL
    (進捗ダイアログ) → 「再起動して適用」で updater バッチ生成 + detached 起動 +
    k-file 終了 → updater が旧フォルダ退避 + zip 展開 + 新版起動 + .old 削除
  - **`v0.1.0-beta.1` タグ切り (1ff5e87)**: CI 成功で Releases に prerelease として
    `k-file-windows.zip` upload 済。これ以降の更新は自動アップデート通知が走る
  - **ファイル名 絞込検索 (Ctrl+F、ADR-26)**: 中央ペイン breadcrumb 右端に 🔍 アイコン
    + 折り畳み式 LineEdit。空白区切り AND 検索 (大小無視 部分一致)、件数表示
    「N / M 件」、サブフォルダ/タブ切替で自動クリア
  - **defensive preview clear の撤回 (ADR-28)**: ADR-22 で多数置いた防御 clear() を
    ADR-23 (QBuffer in-memory) で不要になった箇所から撤去。`changeEvent` の
    ActivationChange と F3 close で preview を維持 → ウインドウ外クリックや別アプリ
    切替で preview が消えなくなり業務感が向上
  - **選択追従 + プレビュー連動 修正**: `_restore_selection_by_paths` を bool 返却化
    + 旧選択クリア、`_populate` に「同 row index 隣接行」フォールバック (削除/移動後)、
    `select_path_in_table` / `select_path` を `_restore_selection_by_paths` に統一
    (= 点線囲いのみ・濃紺なし事故の根治)、`_on_selection` / `_on_table_selection`
    で選択 0 件なら必ず "" emit (clearSelection 後の stale path 再 emit 防止)
  - **Inbox→事件投入後の focus 設計検討**: 当初「移動先 case_pane に focus 追従」で
    実装 → 実際使ってみるとキーボード連続さばきで Tab 戻りが煩雑と判明 → **「ソース
    側 (Inbox) で隣接行に fallback」に転換** (より高頻度の workflow を優先)
  - **Name 幅同期の補強 (ADR-18)**: `case_pane.subfoldersChanged` /
    `inbox_pane.inboxChanged` を `_apply_pane_layout` にフック (リネーム/移動後に
    bal 崩れが起こり得るケースの保険)
  - テスト: 67 → 102 件 (version 23 + updater 12 追加) 全緑
- **M6 配布**: コマンドライン引数 `k-file.exe "path"` 対応 (M6a 完了)、Explorer 右クリック「k-file で開く」シェル拡張、任意フォルダをタブで開く汎用ファイラー化 (M6a 完了)、PyInstaller `--onedir` + GitHub Actions ビルド (M5c 完了)、**自動アップデート機構 案② (M5e で実装済)**、Win 機で業務並走 → v1.0 stable
  - ※フォルダ既定ハンドラの OS 乗っ取りは行わない (§15 ADR-2)。literal な「Explorer ダブルクリック→k-file」は、やるとしても Win 実機実験 → 上級者向け自己責任トグル止まり
- **M6c 自動アップデート機構 (✅ M5e で案② を実装完了)**: 起動時 GitHub Releases
  API チェック → 通知 → 自動 DL + 自動適用 + 再起動。詳細 §15 ADR-27。差分更新 (案③)
  は法律実務系業務アプリでリスク高 (アップデート途中で起動不能) のため v1.0 安定期まで保留

### 確定したショートカット体系 / サブフォルダ操作 (原仕様の F1〜F6 から変更済)
- **サブフォルダボタン 左クリック**: そのサブフォルダの中身を表示 (閲覧のみ・ファイルは動かさない)
- **Alt+0〜9**: 選択中の Inbox ファイルを投入 (0=事件フォルダ直下 / 1〜9=サブフォルダ先頭 9 個)。Inbox 未選択時は閲覧のみ。即時投入 (ダイアログなし)
- **サブフォルダボタン 右クリック**: 投入メニュー (D&D 以外のマウス投入手段)
- **中央ストリップ `>1`〜`>0`**: Alt+N 相当の動的ボタン群 (現在事件のサブフォルダ構成に追従)
- **中央ストリップ `<<`**: 中央選択ファイル → OS デスクトップへ戻す (一時保留)
- **F2**: ファイル/フォルダ名変更 (Windows 標準) — 中央 / Inbox 両方で動く
- **Shift+F2**: 事件フォルダ自体の rename ダイアログ (滅多に使わない用途、case_code 変更時は警告)
- **F3**: プレビュー開閉トグル (1:1 二カラム ↔ 1:2:2 三カラム、初期は二カラム)
- **F5**: Inbox 更新 (Windows 標準)
- **Del / F8**: 選択ファイル/フォルダを OS ごみ箱へ送る (中央 / Inbox 両方)
- **F12 / 編集→投入履歴**: 投入履歴ビュー (各行から個別 Undo)
- **編集→ごみ箱を開く**: OS のごみ箱ウインドウを起動 (削除の復元動線)
- **Ctrl+O**: 事件を開くダイアログ (ksystemz.db 検索 + 事件タブ追加)
- **Ctrl+Z / 編集→元に戻す**: Undo (inject/move/rename。trash は OS ごみ箱右クリックに委譲 — ADR-13)
- **Ctrl+Q**: 終了
- 下部ファンクションキーバー (DOS ファイラー風) に F1〜F12 を全 12 枠表示、未実装は薄色グレー (F2/F3/F5/F8/F12 が enable)

---

## 7. 実装済み機能カタログ

### M1 (2026-05-22 完了)
- ✅ PySide6 6.11 / Python 3.12 起動
- ✅ Win95 高密度 QSS (`resources/style/win95.qss`、14-16px 統一、文字ぴったり行高)
- ✅ 自作タイトルバー (`src/ui/title_bar.py`、14px、紺色、最小化/最大化/×、startSystemMove で Wayland 対応)
- ✅ メニューバー (ファイル/編集/表示/ヘルプ、ショートカット結線)
- ✅ 事件タブ (`src/ui/case_pane.py` 上端、複数案件同時、アクティブ強調、× 閉じ、D&D 並替)
- ✅ 3 ペイン splitter (1:2:2、handle 4px、ドラッグ可変)
- ✅ Inbox ペイン (`src/ui/inbox_pane.py`、出所フィルタタブ + Name 列のみ、ダミー 7 ファイル)
- ✅ 事件フォルダペイン (左右 sunken 縦枠で視覚分離、サブフォルダ縦ボタン、件数バッジ、3 列ファイル一覧 Name/更新/サイズ)
- ✅ プレビューペイン (`src/ui/preview_pane.py`、M2 までプレースホルダ)
- ✅ ステータスバー (Inbox 件数 / Undo 段数 / 直近操作通知)
- ✅ サブフォルダ操作のダミー反映 (左クリック=閲覧表示 / Alt・右クリック=投入ダミーメッセージ。実投入は M3)
- ✅ PyInstaller spec (`k-file.spec`、--onefile、`sys._MEIPASS` 対応で resources バンドル)
- ✅ GitHub Actions ワークフロー (`.github/workflows/build.yml`、main push で .exe artifact、v* タグで Releases)
- ✅ GitHub 公開リポジトリ作成 (`windom21-cpu/k-file`、public、CI 分数無制限)

### M1 補強 — UI/操作 設計詰めセッション (2026-05-22 同日)
- ✅ メニューバー表示バグ修正 (QMenuBar の高さ固定で全項目がオーバーフローに追い出されていた)
- ✅ 「ツール」メニュー新設 (設定… プレースホルダ)、未実装メニュー項目をグレーアウト表示
- ✅ ヘルプ→「k-file について」を Win95/98 風ダイアログ化 (`src/ui/about_dialog.py`、Frameless + 自作タイトルバー)
- ✅ 3 ペインにタイトル見出し (INBOX / 参照フォルダ / プレビュー)、見出しを上下の彫り込み線で挟む (`src/ui/pane_header.py`)
- ✅ 中央ペインの凹み枠を左右の縦枠のみに (上下撤去、見出しの彫り込み線が担当)
- ✅ 「事件フォルダ:」パス表示をペイン全幅・中央揃え
- ✅ サブフォルダボタン: 左クリック=閲覧 / Alt+0〜9・右クリックメニュー=投入 に分離 (§15 ADR-1)
- ✅ 「0 事件フォルダ直下」ボタン追加 (どのサブフォルダにも入っていない直下ファイル)
- ✅ TitleBar に minimal モード追加 (ダイアログ用、× ボタンのみ)

### M2 補強 — UI 詰めセッション 2 (2026-05-23 完了)
- ✅ ファイル一覧の最先頭に `..` 行 (`src/ui/case_pane.py` の `_NameItem.is_parent`)。物理的に親階層がある時のみ表示 (サブフォルダトップ・事件フォルダ直下では非表示) — §15 ADR-2 と整合
- ✅ 下部ファンクションキーバー (`src/ui/function_keys_bar.py`、DOS ファイラー風)。F1〜F12 全枠表示、未実装は薄色 + clickable=False
- ✅ Shift+F2 = 事件フォルダ自体の rename ダイアログ (Win 禁則文字 + 衝突 + case_code 変更警告)
- ✅ F3 = プレビュー開閉トグル (1:1 二カラム ↔ 1:2:2 三カラム、初期は二カラム)
- ✅ 動的レイアウト計算 (`MainWindow._apply_pane_layout`): 2 カラム時に「Inbox 幅 ≒ 中央のファイル一覧幅」が成立するよう毎回算出。3 カラム時は従来 1:2:2
- ✅ 中央コマンドストリップ (`src/ui/command_strip.py`、Inbox と参照フォルダの間に縦バー、幅 28px)。ボタン縦中央自動センタリング
  - `▶▶` 投入 (Inbox 選択 → アクティブサブフォルダ、M3 までダミー)
  - `✕` 無視 (Inbox 選択を表示から除外/解除トグル、実機能)
  - `↶` Undo (M4 まで disabled)
- ✅ Inbox 右枠と CasePane 左枠を sunken 対称化 (両側「ペインの暗 2px + ストリップの明 1px」)。splitter handleWidth=0 (動的計算で配置するため drag 不要)
- ✅ Inbox 列構成を参照フォルダと統一 (出所列削除 → Name / 更新 / サイズ、列幅 Stretch/90/70)
- ✅ サイズ列 KB 統一 (整数 `121KB` 表示) + ヘッダー**右クリック**メニューで KB/MB 切替 (両ペイン独立) — §15 ADR-4
- ✅ Inbox にソート追加 (ヘッダー**左クリック**、既定は更新降順 = 新着順)。サイズはバイト数で正しくソート、行参照は UserRole パス埋込で破綻防止

### M2 実ファイル接続 + プレビュー (2026-05-22 完了)
- ✅ `core/folder_scanner.py` — 事件フォルダ実読込 (サブフォルダ動的取得・`\d_` 繰り上げ割当・直下ファイル・ネスト検出)。Qt 非依存
- ✅ 中央ペイン: ダミー廃止、実フォルダ表示。事件タブ/サブフォルダボタンを実フォルダから動的構築
- ✅ ネストフォルダをファイル一覧に「フォルダ行」表示、ダブルクリックで descend、パンくずで戻る (§15 ADR-3)
- ✅ `core/inbox_watcher.py` — Inbox 監視対象の実読込 + QFileSystemWatcher 自動更新。PDF/画像のみフィルタ
- ✅ 左 Inbox: 実ファイル表示 (Name + 出所列)、出所フィルタタブ、F5 手動更新、ステータスバー実件数
- ✅ `infra/kfile_db.py` — kfile.db (settings/ignored_files/drop_history/recent_names/open_tabs)。OS ごとの app data に配置
- ✅ 「無視」機能 — 右クリックで個別除外、表示メニューで再表示・解除 (可逆)
- ✅ `src/ui/preview_pane.py` — QPdfView (PDF) / QPixmap (画像) プレビュー。複数ページはページ送りバー。読込失敗は graceful
- ✅ ファイル選択 → プレビュー連動 (Inbox / 中央 両方から)

### M3 投入 + cross-case Move (2026-05-23 完了)

#### コア (Qt 非依存)
- ✅ `core/file_ops.py` — `inject` (Copy→検証→元削除) / `move` (cross-case) / `rename` / `trash` (send2trash) / `validate_name` (Win 禁則文字) / `resolve_collision` (自動連番 `name (2).ext`)。各操作は `OpResult` (ok/action/src/dst/renamed_to/collided/error) を返す
- ✅ `core/inbox_watcher.py` 拡張 — `InboxSource` dataclass に `cutoff_days` 追加 (Desktop は実 7 日フィルタ)。`list_inbox_files` 切り出し (Qt 非依存)
- ✅ `tests/test_file_ops.py` 22 件、`tests/test_inbox_watcher.py` 6 件 — 純関数を網羅

#### infra
- ✅ `infra/kfile_db.py` 拡張 — `record_history` / `add_recent_name` / `recent_names` / `recent_history` API
- ✅ `infra/folder_shortcut.py` — Linux/Mac はシンボリックリンク、Win は PowerShell COM 経由の `.lnk`。事件→他事件 root への集約マーカ用 (`create_folder_shortcut`)
- ✅ `requirements.txt` に `Send2Trash==1.8.3` 追加

#### UI
- ✅ Alt+0〜9 / 右クリック / D&D 投入を `file_ops.inject` に実接続。**rename ダイアログなしの即時投入** (ADR-7)。衝突は自動連番、ステータスバー通知
- ✅ `ui/rename_dialog.py` — Win95 風 frameless ダイアログ、`mode='inject'/'rename'` でラベル + Esc 動作切替。recent_names 候補 combobox、stem 部分のみ選択 (Windows 流儀)。raised 外縁 (QSS)
- ✅ `F2` — 中央 / Inbox のどちらでも単独 rename ダイアログ
- ✅ `Shift+F2` — 事件フォルダ自体の rename (case_code 変更警告つき)
- ✅ `ui/dnd.py` — `text/uri-list` + `application/x-kfile-source` で起点 (inbox / case) を識別
- ✅ Inbox table → サブフォルダボタン D&D 投入 (rename なし、即時)
- ✅ 中央 file table → 別事件タブ D&D Move (同名サブフォルダ自動マッピング、なければ事件 root)
- ✅ `ui/command_strip.py` 改修 — `▶▶` を廃止、**現在事件のサブフォルダに対応した動的 `>1`〜`>0` ボタン群** + `<<` (実 Desktop 戻し) + `✕` (無視) + `↶` (Undo、M4 まで disabled)。区切り線で 3 ブロック
- ✅ ストリップ数字ボタンは Inbox 未選択時 = 閲覧のみ、選択中 = 投入 + そのサブフォルダを開く
- ✅ ストリップ `<<` — 中央選択ファイルを実 OS デスクトップに移動 (ADR-9: round-trip 用)
- ✅ Inbox 監視対象に **実 ~/デスクトップ** を Desktop ラベルで合流 (同名ラベルは同じフィルタタブにマージ、`cutoff_days=7` で古い PDF 自動非表示)
- ✅ CasePane: サブフォルダ列下に **`+ 追加`/`− 削除`** ボタン (新規サブフォルダ作成 / 表示中サブフォルダを OS ごみ箱へ)
- ✅ CasePane: パス行右に **「他事件へ」ボタン** — 開いている他事件タブをメニュー表示 → 選択した事件 root に現事件フォルダのショートカットを置く (ADR-11: AB 集約運用)
- ✅ About ダイアログ: raised 外縁 QSS + 内側 QWidget ラッパ撤去 (border 表示のため)

### M4 Undo + 削除 + 履歴 (2026-05-23 完了)

#### コア
- ✅ `core/undo_ops.py` — `undo_action(row)` で drop_history 1 行を逆実行。inject/move は dst → src を `shutil.move`、rename は dst → src を `rename`、trash はファイル名込みの動線案内メッセージで失敗扱い (Win Recycle Bin に委譲)
- ✅ `tests/test_undo_ops.py` 7 件 — inject/move/rename の成功・dst 欠落・src 衝突・trash 動線案内・未対応 action を網羅

#### infra
- ✅ `infra/kfile_db.py` 拡張 — `last_undoable_entry` / `undoable_count` / `mark_undone` API。**`action != 'trash'` を SQL で除外** (ADR-13)
- ✅ `infra/recycle_bin.py` — `open_recycle_bin()` で OS ネイティブのごみ箱を起動 (Win: `explorer.exe shell:RecycleBinFolder`)

#### UI
- ✅ `Del` / `F8` — 中央 / Inbox のどちらでも選択行を OS ごみ箱へ (`file_ops.trash` + drop_history 記録)。−ボタン (サブフォルダ削除) も同経路に統一
- ✅ `Ctrl+Z` / 編集→元に戻す / `↶` ボタン — 最新の Undoable 履歴 (trash 除く) を逆実行。失敗時はエラーメッセージ、成功時は両ペイン refresh
- ✅ `↶` ボタンと「元に戻す」メニュー、ステータスバー `Undo N 段` の自動連動 (`_record_history` wrapper で必ず refresh)
- ✅ `ui/history_view.py` — F12 投入履歴ビュー (frameless モーダル、最近 200 件、各行に `戻す` ボタン)。trash 行を「戻す」と動線案内メッセージが出る
- ✅ 編集→ごみ箱を開く — Windows ネイティブの Recycle Bin ウインドウを開く動線

### M5 K-SystemZ 連携 + 設定 + セッション復元 (2026-05-23 完了)

#### コア (Qt 非依存)
- ✅ `core/case_repo.py` — `CaseRepo` クラス。`sqlite3.connect(..., uri=True, mode=ro)` で ksystemz.db を RO 接続、`doc_root()` で OS 別パス取得、`search(keyword, active_only)` で cases ⨯ case_persons ⨯ persons を JOIN して検索、`resolve_folder(case_code)` で doc_root 直下を前方一致して実フォルダを返す
- ✅ `core/folder_scanner.py` 拡張 — `FileEntry.is_link` フィールド追加 (Linux symlink / Win .lnk を検出)。`scan_case_folder` で symlink は **左ボタン列のサブフォルダにせず root_files に入れる** (別事件への入口扱い、ADR-16)
- ✅ `tests/test_case_repo.py` 14 件 — RO 接続/active_only フィルタ/keyword 各種 (case_code/姓名/法人名/case_name)/CaseRecord 表示/resolve_folder/書き込み拒否/欠落 db 例外
- ✅ `tests/fixtures/build_mock_ksystemz_db.py` — 引き継ぎ書 v22 スキーマでモック生成 (架空 6 事件 + office_info)。本物の ksystemz.db は Win 機限定で持ち出さない (ADR-14)

#### infra
- ✅ `infra/kfile_db.py` 拡張 — `open_tab_codes()` / `save_open_tabs(codes)` API (セッション復元用)
- ✅ `infra/folder_shortcut.py` 拡張 — `resolve_shortcut(path)` で Linux symlink / Win .lnk のターゲット解決 (Win は PowerShell の COM 経由)

#### UI
- ✅ `ui/open_case_dialog.py` — Win95 風 frameless モーダル。検索ボックス + 「現在進行中のみ」チェック + 結果テーブル (Code / 依頼者 / 種別 / 状態 / 事件名)。Enter / ダブルクリック / 「開く」で accept、Esc / Cancel で reject。`Ctrl+O` で起動
- ✅ `ui/settings_dialog.py` — Inbox 監視先テーブル (ラベル / パス / 古さ制限、+/− 追加削除 + 参照ボタン) + ksystemz.db パス指定 + kfile.db 場所表示 (情報のみ)。OK 押下で kfile.db settings に JSON 保存 + Inbox 監視器再構築 + ksystemz cache 破棄。`ツール→設定…` で起動
- ✅ `case_pane.py` 拡張 — `add_case_tab(path)` (重複は既存タブに切替)、`casePathsChanged` シグナル、`caseShortcutActivated` シグナル (B 内の A symlink ダブルクリック)、`set_doc_root_getter(getter)` (事件ショートカット判定用)、「0 事件フォルダ直下」ビューに symlink を含めるフィルタ
- ✅ `case_pane._load_case_tabs` の起動時自動 load を撤去 (ADR-15) — 初期状態は空タブ、Ctrl+O / セッション復元 / フォルダ D&D 経由で意識的に開く
- ✅ `case_pane`: 事件ショートカット行に `↗` プレフィックス + `.lnk` 拡張子を表示から除去
- ✅ `case_pane._on_table_double_click`: ショートカット行は `_try_activate_case_shortcut` で target を doc_root 直下と照合 → 該当ならタブ切替 (`caseShortcutActivated` 発火)、不該当なら通常 descend にフォールバック
- ✅ `inbox_pane.py` 拡張 — `__init__(sources=...)` で設定ダイアログから渡された監視先を受け取る、`reload_sources(sources)` で動的差し替え
- ✅ `main_window.py` 拡張 — `Ctrl+O` で OpenCaseDialog 起動 + 選択事件のタブ追加、`ツール→設定…` で SettingsDialog 起動、起動時 `_restore_session()` で `open_tabs` 復元、`casePathsChanged` → `_save_open_tabs` で永続化、`dragEnterEvent`/`dragMoveEvent`/`dropEvent` で外部フォルダの D&D を受けて事件タブ追加 (内部 D&D とは `x-kfile-source` MIME で識別)、`caseShortcutActivated` → `add_case_tab` で事件ショートカット動線

#### About 修正
- ✅ Win95 raised 外縁適用 (内側 QWidget ラッパを撤去、QSS border が見えるように)、バージョン表示を M5 に更新

### M5b UX polish (2026-05-24 完了)

β 配布前にユーザー (sk21) と 1 セッション集中で磨き込んだ項目。実機ワーク
フロー (法律実務) でのリズムを保つことを優先。コード行数は増えていない
箇所も多いが、利用者体感は段違いに向上 (M5 完了時 → β 直前)。

#### フォント / 描画
- ✅ **MS Gothic 12pt 埋め込みビットマップを全 widget に強制** (ADR-17): `src/ui/_font_strategy.py`
  に `apply_bitmap_font_strategy(root, point_size=None)` を新設、`QFont.StyleStrategy(PreferBitmap | NoAntialias)`
  を MainWindow + 全ダイアログの widget tree に walking 適用。QSS で
  font-family を指定すると Qt が strategy をリセットするため、表示後に
  Python 側で再付与する必要があった (Qt 既定はベクトル + AA で「滑らかな
  MS Gothic 風」になり、当時の質感が出ない)
- ✅ **QSS フォント宣言を `*` グローバル 1 箇所に集約** — 個別 rule から
  font-family / font-size: 12pt 重複を全削除し継承で表現。例外サイズ (9pt
  ステータスバー / タイトルバーボタン等) のみ残置。font 変更は QSS の 1 箇所だけ
- ✅ **ツールチップも同じ MS Gothic 12pt ビットマップ** (`QToolTip.setFont` +
  QSS の `QToolTip` Win95 風クリーム色)
- ✅ **ダイアログは 9pt + 専用 QSS スコープ** (`#aboutDialog *, #renameDialog *`)
  で本体 12pt と差別化。raised 外縁 2px を尊重するため outer マージン 2px に統一

#### 複数選択 (両テーブル multi-select)
- ✅ Inbox / 中央テーブルを ExtendedSelection モードに (Shift で範囲 / Ctrl で個別)
- ✅ `make_kfile_mime_data(source, paths: Path | list[Path])` で D&D MIME を
  多パス対応に拡張、startDrag は全選択をのせる
- ✅ MainWindow に `_batch_inject(srcs, target_dir, category, suffix)` ヘルパを抽出 —
  4 つの inject / cross-case Move ハンドラを batch ループ化、1 件成功時は
  従来通り個別名、複数成功時は `N ファイル → A 事件 / 1_文書 に投入 (衝突回避 X 件)`
- ✅ Del / 削除ボタン / Alt+0〜9 / ストリップ数字ボタン / 無視 全てが全選択対応

#### D&D 視覚フィードバック
- ✅ `src/ui/dnd.py` に `make_drag_pixmap(names)` 追加 — ドラッグ中にカーソル右下に
  Win95 風黄色付箋でファイル名 (複数なら「先頭名 他 N 件」)
- ✅ drop ターゲットの hover 強調 — drag enter で背景黄色 + 紺色枠、leave / drop で復帰
  (サブフォルダボタン / 中央テーブル)
- ✅ **テーブル全体への drop = 現在表示中フォルダに投入** (孫フォルダ含む) —
  フォルダ行ピンポイント不要、孫階層に降りた状態で投げれば孫に入る

#### キーボード操作
- ✅ **Tab / Shift+Tab で Inbox ↔ 中央ファイル一覧 を往復** (移動先で未選択時は
  先頭行を自動選択 → 即操作開始)
- ✅ **Enter / Return** で選択ファイルを OS 既定アプリ起動 (両テーブル)。
  case_pane では Enter でフォルダ descend / `..` で上 / ショートカットで事件タブ切替 もサポート
- ✅ **F6 雑記録 / F7 一時保管** クイック起動 — `kfile.db` settings (`quick_notes_path`
  / `quick_temp_path`) で各フォルダを設定、ファンクションキーバーが動的に
  enable / label / tooltip 切替、F キー or セルクリックで `add_case_tab(path)` (任意フォルダタブ機構を流用)

#### 右クリックメニュー拡張
- ✅ Inbox: 既定アプリで開く / Explorer で開く / フルパスをコピー (+ 既存の無視トグル)
- ✅ 中央テーブル: 同上 (ファイル) / Explorer で開く (フォルダ)
- ✅ 事件タブ: このタブを閉じる / 他のタブを閉じる / すべて閉じる / Explorer で開く / フルパスをコピー

#### プレビュー固定ヘッダー
- ✅ `preview_pane.py` 上部に `previewInfo` QLabel 常設 — ファイル名 / サイズ /
  更新日時 / 追加情報 (PDF=N ページ, 画像=W×H px) を `/` 区切りで 1 行表示。
  プレビュー本体より目立たないよう本体と同じ 12pt MS Gothic ビットマップ

#### ステータスバー 2 分割
- ✅ 左 = 通常 `showMessage` (移動/投入の動的通知)、右 = 選択ファイルのフルパス
  (`path_status_label`、addPermanentWidget、9pt、sunken 区切り線付き)
- ✅ 複数選択時は右側が `<複数選択>` に切替 (selectionModel.selectionChanged 監視)

#### ウインドウ / レイアウト
- ✅ **ウインドウサイズ永続化** — `closeEvent` で `window_width` / `window_height` /
  `window_maximized` を kfile.db settings に保存、起動時に復元
- ✅ **Inbox 幅 ≒ 中央ファイル名列幅 を完全同期** (ADR-18) — splitter の
  `setStretchFactor` を撤去、`resizeEvent` で `QTimer.singleShot(0)` 経由
  で `_apply_pane_layout` を再計算 (Qt のレイアウトパス後に setSizes 適用)。
  両テーブルとも vertical scrollbar 常時表示で viewport 幅一致
- ✅ プレビュー 3 カラム時も同公式で Inbox = case_table = preview/2 を成立
- ✅ レスポンシブ列幅: 更新列は viewport 余地に応じて 110→0 まで縮み、30px 未満なら自動非表示 (Name 列優先)
- ✅ **タブが多数で見えなくなる問題** を Qt 標準動作 (setUsesScrollButtons=True +
  Expanding=False + setSizePolicy(Expanding, Fixed)) に整理

#### ファイル列 (Name + EXT 分離)
- ✅ Name 列は **stem 表示** (拡張子除去) + 別列 **拡張子** (大文字 `.PDF` `.JPEG`)
- ✅ 列幅: Name (Stretch) / EXT 60 / 更新 110 / サイズ 90
- ✅ 行間に細いグレー線 (`border-bottom: 1px solid #D8D8D8`) で alternating row と併用
- ✅ ソート: 初回のみ既定 (case=Name 昇順 / Inbox=更新降順) を適用、以降は
  sortIndicator を尊重 — KB/MB 切替やリフレッシュで「勝手に既定順に戻らない」(ユーザー要望)
- ✅ プレビュー展開時 (3 カラム) は EXT / 更新 / サイズ を自動非表示 → Name のみ
- ✅ `<DIR>` (フォルダ行サイズ列、`..` 行含む)、フォルダアイコン廃止 (DOS ファイラー風)

#### UI ラベル整理
- ✅ メニューバー: `ﾌｧｲﾙ(F) 編集(E) 表示(V) ﾂｰﾙ(T) ﾍﾙﾌﾟ(H)` (カタカナ語は半角、漢字は維持)
- ✅ 「参照ﾌｫﾙﾀﾞ」 (パンくず・テーブル列ヘッダーは漢字維持)
- ✅ タイトルバー: `K-FILE` のみ (副題撤去)、アプリ名表示は `K-FILE` で統一
  (About のタイトル / ヘルプメニュー も `K-FILE` に統一、内部識別子 `k-file` は維持)
- ✅ パスバーから「事件フォルダ:」プレフィックス削除 → `R060200044 鈴木花子 離婚 › 1_文書` のみ
- ✅ 「他事件へ」ボタン → `↗` アイコンのみ (ツールチップで説明)
- ✅ 中央ストリップの `✕` → 「無視」テキスト、削除ボタンを別途追加 (誤認防止)
- ✅ サブフォルダボタンに hover で末尾省略 (…) — fontMetrics.elidedText、ツールチップでフル名
- ✅ 高さ統一: タイトルバー / メニューバー / ファンクションキー / タブを 12pt が窮屈にならない 18〜22px に揃え、ボタン間に 2px のすき間

#### 孫フォルダへの Inbox D&D
- ✅ `_DragCaseTable` を `DragDropMode.DragDrop` に変更 — 自身からの drag-OUT
  (cross-case Move) + Inbox からの drop-IN を同居
- ✅ `inboxDropToFolderRequested(target_dir: str, src_paths: list[str])` 新シグナル
  → `_on_inbox_drop_to_folder` で `_batch_inject` を呼ぶ
- ✅ 孫フォルダ・曾孫フォルダ等、サブフォルダボタンに割当のない深い階層への
  投入手段 (操作: 親サブに入って、孫に降りて、Inbox から drag drop)

### M5c 本番テスト対応 + polish (2026-05-25 完了)

1 回目 Win 機本番テスト報告 (`/home/sk/デスクトップ/260525k-fileテスト結果.txt`)
を受けた緊急対応セッション。業務凍結級バグ + 設計修正 + 連携技術対応の三本立て。

#### 業務凍結級 (削除/移動/リネーム不能の原因)
- ✅ プレビューファイルロック解放 (ADR-22): `PreviewPane.clear()` で
  `QPdfDocument.close()` を明示。削除/移動/リネーム/F3 閉/ウインドウ非アクティブ
  /Inbox↔参照フォルダ間 focus 切替 で呼ぶ。`eventFilter(FocusIn)` で相手側選択も
  `clearSelection + setCurrentCell(-1,-1)` (ユーザー要望: フォーカスが離れた
  ペインは選択も離れる)
- ✅ タブ氏名抽出 (`_parse_case` 拡張): `R08020011文書フォルダ(田中太郎)売買`
  → ("R08020011", "田中太郎 売買")。半角/全角括弧両対応、旧スペース区切り形式も
  後方互換
- ✅ 単一インスタンス + IPC (M6b、ADR-20): `src/ipc.py` の `IpcServer` /
  `try_send_to_primary`。2 つ目以降は QLocalSocket でパス送信 → 自分は exit、
  primary 側で `add_case_tab` + raise/activateWindow

#### Inbox 設計転換 (ADR-19)
- ✅ ホワイトリスト撤去 → ブラックリスト方式: `INBOX_EXCLUDE_EXTENSIONS = {.tmp,
  .part, .crdownload, .download}` / `INBOX_EXCLUDE_NAMES = {.DS_Store, Thumbs.db,
  desktop.ini}` + ドット隠し (`.k-*` は明示通過)
- ✅ `InboxFile.is_dir` 追加でフォルダも Inbox に出す。`<DIR>` 表示、Alt+0〜9 /
  D&D / 右クリックで事件サブフォルダに丸ごと移動可能
- ✅ `file_ops.inject` にフォルダ分岐 (`shutil.move` 一発、サイズ検証は省略)
- ✅ Inbox フォルダ行ダブルクリックで `openFolderRequested` 発火 →
  `add_case_tab` で事件タブとして開く (M6a 汎用ファイラーと整合)
- ✅ `list_inbox_files` で resolve 済みパス重複を排除 (Desktop 行 2 件並びの
  2 倍表示事故への保険)
- ✅ dev デフォルト整理: Desktop 2 件 → 1 件 (本番テストで両方変えると重複事故)

#### 業務上ストレス
- ✅ 0KB スキャン抑制: `_INCOMPLETE_GRACE_SEC = 5.0`、`InboxWatcher.DEBOUNCE_MS
  = 700` + follow-up timer 5.5 秒後で書き込み完了後の再走査
- ✅ Office 系拡張子追加 (.docx/.xlsx/.pptx/.txt 等) ※ブラックリスト方式に
  転換したので結果として自動的に含まれる
- ✅ 更新列: `%y-%m-%d %H:%M` (西暦下 2 桁 + 月日 + 時分) で Inbox/参照フォルダ
  共通フォーマット、列幅 110 → 130 (初期表示で省略されない)
- ✅ サイズ列: `format_size` から単位文字 (KB/MB) を外し 3 桁カンマ区切り
  (`12,345` / `12.0`)、ヘッダーラベルを `ｻｲｽﾞ (KB)` / `ｻｲｽﾞ (MB)` 動的切替
  (半角カタカナ、KB/MB 切替メニュー追従)
- ✅ ファイル名 tooltip: Inbox / 中央 Name セルにフル名 (拡張子込み) + Inbox は
  出所ラベルも併記
- ✅ テキスト/JSON プレビュー: `.txt/.log/.md/.csv/.tsv/.ini/.cfg/.json/.k-photo`
  を QPlainTextEdit で表示。JSON は indent=2 整形、parse 失敗は生表示、64KB cap、
  UTF-8 → UTF-8 BOM → CP932 → latin-1 文字コードフォールバック

#### K-SystemZ 連携技術対応
- ✅ SQLite `PRAGMA busy_timeout = 5000` を ksystemz.db RO 接続 + kfile.db
  両方に設定 (K-SystemZ 側書込との競合 5 秒待ち)
- ✅ 起動致命例外を `%APPDATA%\k-file\error.log` に追記 (`src/main.py` の
  `_log_startup_error` ヘルパ + `if __name__ == "__main__"` の try/except)
- ✅ PyInstaller `--onedir` 化 (ADR-21): `k-file.spec` を `EXE(exclude_binaries
  =True) + COLLECT()` 構成へ、CI で `Compress-Archive` で `dist/k-file/` を
  `k-file-windows.zip` に固めて artifact / Release に upload

#### テスト
- ✅ 67 件 pass (M5c 追加: 0KB 抑制 / フォルダ inject 2 件 / blacklist 1 件 /
  `InboxFile.is_dir` 1 件 / dedupe 1 件)

### M5d Win 2 回目検証フォロー + cross-case Copy + K-SystemZ 連携詰め (2026-05-26 完了)

2026-05-26 Win 機 dev 実機 (Python 3.14.3 + PySide6 6.11.1) で 2 回目本番テスト相当を
実施した結果、M5c 残バグの修正と新機能要望を消化した一日。コミット 4 本
(`86ec399` / `b2375f5` / `01b7499` 系)。

#### F2 リネーム周りの根治 (ADR-23 + ADR-22 補足)
- ✅ **QBuffer 経由 PDF 読込み**: `QPdfDocument.load(path)` を直接呼ぶと Win 上で
  PDFium が `close()` 後もファイルハンドルを保持し、F2 → OK 時に
  「別のプロセスが実行中です」エラーで rename 失敗する事象が残っていた。
  `preview_pane.py::_show_pdf` を「`p.read_bytes()` → `QByteArray` → `QBuffer` →
  `pdf_doc.load(buffer)`」に変更 → Qt 側はファイルハンドルを保持しない。
  `read_bytes()` 完了時点で OS のファイルハンドルは閉じるので、以降ファイルは
  外部から自由に rename/delete/move 可能 (ADR-23)
- ✅ **`_internal_modal_count` フラグ**: `MainWindow` 起動時に `int = 0` を仕込み、
  `_on_rename_in_case` / `_on_rename_in_inbox` の `dlg.exec()` を try/finally で
  囲んで増減。`changeEvent` の `ActivationChange` ハンドラがこのカウンタを見て、
  > 0 の時は `preview_pane.clear()` を skip → 「プレビューを見ながらのリネーム」
  を実現。**外部アプリ切替時の release は維持** (ADR-22 不変)

#### 選択ドリフト修正 (ADR-24)
- ✅ Inbox / CasePane の `_populate` で「rebuild 前に選択 path 集合を保存
  (`_collect_selected_paths`) → rebuild + sort 完了後に同 path を再選択
  (`_restore_selection_by_paths`)」する処理を追加
- ✅ multi-select 対応。currentIndex を先に動かしてから select を一括適用する
  ことで、`itemSelectionChanged` 経由のプレビュー連動が新しい currentRow を
  見るよう順序を保証 (選択 vs プレビュー食い違い対策)。Inbox auto refresh、
  rename refresh、KB/MB 切替などすべての populate 経路で恩恵あり

#### cross-case Copy 動線 (ADR-25)
- ✅ **`file_ops.copy`** 新設: `shutil.copy2` (ファイル) / `shutil.copytree`
  (フォルダ) ベース。衝突自動連番、`validate_name` 流用、`OpResult` 返却で
  既存 inject / move / rename / trash と同じ責務分離
- ✅ **`undo_ops` に "copy" 対応**: Ctrl+Z で dst を `send2trash` で OS ごみ箱
  へ送るのみ (src は手付かず)。永久削除回避の保険
- ✅ **A 案: Ctrl+D&D = cross-case Copy**: 事件タブへの D&D = Move を維持しつつ、
  Ctrl 押下中の D&D を Qt の `proposedAction == CopyAction` で判定して Copy に
  分岐。CasePane に `caseTabDropCopyRequested` シグナル、`_DropTabBar.dropEvent`
  で proposedAction 読取
- ✅ **B 案: 右クリック「他事件へコピー / 移動 → サブフォルダ明示」**: 中央
  ファイル右クリックメニュー末尾に動的サブメニュー (他事件タブ一覧 → そのサブ
  フォルダ一覧 + 「0 事件フォルダ直下」)。multi-select 対応、`scan_case_folder`
  で各事件のサブフォルダを動的取得、`caseExplicitCrossCaseRequested(op,
  target_dir, src_paths)` シグナルで MainWindow に通知
- ✅ **MainWindow 共通ヘルパ `_do_cross_case_op`**: `op` ("copy"|"move") +
  `target_case_root` + `target_dir_resolver: Callable[[Path], Path]` +
  `src_paths` を受ける Strategy パターン。D&D 経路は `_automap_resolver`
  (同名サブフォルダ自動マッピング)、明示経路は固定 `lambda _src: target_dir`
  で resolver を渡し分け。Move/Copy / 自動・明示 の 4 経路を 1 つのループで賄う
- ✅ ステータスバー通知文言は op によって自動切替 (「コピー」「移動」、「→」「を」)

#### K-SystemZ サブアプリ拡張子対応 (.kphoto / .kevi)
- ✅ 実拡張子は **`.kphoto`** (K-photo) と **`.kevi`** (K-evi 証拠説明書スタンプ)
  と判明 (ハイフン無し、`.k-photo` は HANDOVER 上の仮称だった)
- ✅ Inbox はブラックリスト方式のため通常ファイル名 (`evidence_2026.kphoto`
  等) は既存実装で問題なく表示。検証コードで visible=True を確認済
- ✅ `inbox_watcher._is_visible_in_inbox` の dotfile 例外を `.k-` 始まり →
  **`.k` 始まり** に緩和。将来 K-SystemZ が dotfile 形式の設定ファイルを
  採用しても自動対応 (`.kphoto-config` 等)
- ✅ `preview_pane._JSON_EXTS` に `.kphoto` / `.kevi` を追加。JSON 整形プレビュー
  (indent=2、64KB cap、UTF-8/CP932/latin-1 フォールバック) が効く。
  `.k-photo` も後方互換で残置

#### K-SystemZ 側の追従対応 (k-file 側変更不要、確認のみ)
- ✅ `_is_kfile_running()` + psutil 依存撤去 (ADR-20 IPC 前提) — K-SystemZ 側は
  毎回 `subprocess.Popen([kfile_exe, *paths])` で OK、ウインドウは k-file 側 IPC
  が集約。返信書 `X:\K-system\k-systemz向け_k-file連携状況_260526.md` 参照
- ✅ `--onedir` 配布対応マニュアル更新 (「k-file.exe だけを別フォルダにコピー禁止」
  注意書き含む)
- ✅ サブアプリ JSON は絶対パス記憶なし設計と判明 (Blob → ブラウザ a.download、
  読込は input + FileReader)。k-file でリネーム / 移動 / 削除しても K-SystemZ
  サブアプリ側に不具合発生せず

#### 2 回目検証で「問題なし」と確認した項目
- ✅ `.kphoto` / `.kevi` プレビュー (上記対応で JSON 整形表示)
- ✅ デスクトップフォルダの Inbox → 事件サブフォルダ移動 (ADR-19 ブラックリスト
  + フォルダ inject で対応済)
- ✅ K-SystemZ から「フォルダを開く」連打 → タブが増えるだけで **ウインドウは
  1 つに集約** (ADR-20 単一インスタンス + IPC)
- ✅ 日本語フォルダ名 (㈱、㊗、機種依存文字) のパス解決
- ✅ case_code 前方一致衝突 (R060200042 vs R0602000420 のような並走) — 実環境で
  問題なし

#### 配布物との対応
- DL 用 zip artifact は CI が main push トリガで毎回再ビルド
- 最新コミット `01b7499` 時点での CI artifact 名: `k-file-windows.zip` (49 MB、
  90 日保持)
- ユーザー差し替え手順: `C:\Users\sk21l\Desktop\k-file-windows\` フォルダごと
  削除 → 新 zip 展開で同名フォルダ再作成。設定は `%APPDATA%\k-file\kfile.db`
  に残るので引き継ぎ自動

#### テスト
- ✅ 67 件 pass (M5d で構造変更 = テスト追加なし。新規 `file_ops.copy` /
  `undo_ops._undo_copy` / 選択保持ヘルパ / 共通 cross-case ヘルパ にテスト追加
  すれば 70+ に増やせる、後続セッションでの課題)

### M5e β タグ準備 polish + 自動アップデート機構 案② (2026-05-27 完了)

β 配布前の最終 polish と、M6c 自動アップデート機構の案② 実装。`v0.1.0-beta.1`
タグ切りまで完了。詳細 §15 ADR-26〜28。

#### 主要点

- ✅ **自動アップデート機構 案② 実装 (ADR-27)**:
  - `src/__version__.py` 新設 (`VERSION = "0.1.0-beta.1"`)、`app.setApplicationVersion(VERSION)` 設定
  - `src/core/version.py` — SemVer ライク比較 (`compare_versions` / `is_newer`、
    dev < alpha < beta < rc < stable、23 unit test)
  - `src/core/updater.py` — GitHub Releases API (`urllib`) + zip asset 選択 +
    `default_updates_dir()` + `write_updater_batch()` + `install_dir_from_exe()`
    (12 unit test、`urllib.request.urlopen` を `unittest.mock.patch` で差し替え)
  - `src/ui/update_banner.py` — `UpdateBanner` (status bar 常駐) + `UpdateManager`
    (QThread で check → QNetworkAccessManager で DL → `subprocess.Popen` で
    updater detached 起動 → `self._main_window.close()`)
  - `src/ui/settings_dialog.py` — 「自動アップデート」セクションに
    「起動時にアップデートを確認する」QCheckBox (DB key
    `auto_update_check_enabled`)
  - `src/ui/main_window.py` — `update_banner` を status bar に
    `addPermanentWidget`、起動 1.5 秒後に `update_manager.check_async()`
  - updater バッチ (Win cmd.exe): `tasklist` で k-file.exe 消滅待ち (最大 30 秒)
    → `ren` で旧フォルダを `.old` 化 → PowerShell `Expand-Archive` で zip 展開 →
    `start ""` で新版起動 → `rmdir /S /Q` で `.old` 削除。CP932 encoding + CRLF
- ✅ **`v0.1.0-beta.1` タグ切り (1ff5e87)**: CI 成功で GitHub Releases に
  prerelease として `k-file-windows.zip` upload 済。これ以降の `v0.1.0-beta.X`
  タグで自動アップデート機構が初発火する
- ✅ **ファイル名 絞込検索 (Ctrl+F、ADR-26)**:
  - 中央ペイン breadcrumb 行右端に 🔍 アイコン (常時表示、checkable QPushButton)
  - クリック or Ctrl+F で QLineEdit (max-width 180px) がインライン展開、自動フォーカス
  - Esc で解除 + 折り畳み、サブフォルダ/タブ切替で自動クリア
  - 空白区切り AND 検索 (大小無視 部分一致)。`受領 田中` で「田中受領書.pdf」
    「受領書(田中).pdf」両方ヒット。拡張子も検索対象 (`pdf` で絞れる)
  - 件数表示「N / M 件」をフィルタ中だけ入力欄右に表示
- ✅ **defensive preview clear の撤回 (ADR-28)**:
  - `MainWindow.changeEvent` の `ActivationChange` 時 `preview_pane.clear()` 撤去
    (ウインドウ外クリックでも preview 維持、ADR-23 で file lock 不要)
  - `MainWindow._toggle_preview` の F3 close 側 `preview_pane.clear()` 撤去
    (F3 再表示で前ファイル即表示)
  - `_internal_modal_count` 連動コード (init / increment / decrement / changeEvent
    での skip) を削除 (用途消失)
  - rename/inject/delete/`<<` 直前の `preview_pane.clear()` は維持 (操作後の
    preview 切替準備として有用)
- ✅ **選択追従 + プレビュー連動 修正**:
  - `_restore_selection_by_paths` を bool 返却化、マッチ 0 件で `clearSelection`
    を呼んで旧 row index に残った selected フラグを除去
  - `_populate` 末尾に「全部消えたら同 row index 隣接行を選択」フォールバック
    (両ペイン)。`prev_current_row` を rebuild 前に保存しておき、復元に失敗したら
    `_select_adjacent_row(prev_current_row)` で隣接行を選択
  - `select_path_in_table` / `select_path` を `setCurrentCell` から
    `_restore_selection_by_paths({str(path)})` に統一 (= ADR-24 と同じ
    `setCurrentIndex(NoUpdate)` → `select(ClearAndSelect|Rows)` パターン)。
    「点線囲いのみ・濃紺なし」事故の根治
  - `_on_selection` (inbox) / `_on_table_selection` (case) で **選択 0 件なら必ず
    `fileSelected.emit("")` 発火**。`clearSelection` 後の currentRow に残った
    stale path がプレビューに戻る事故を防ぐ
- ✅ **Inbox→事件投入後の focus 設計検討と決着**:
  - 当初の問いは「Inbox の隣ファイルではなく**移動先 case pane の移動ファイル
    そのもの**に focus が追従してほしい」 → `case_pane.focus_on_destination()` を
    実装、view 切替 + select + setFocus 順序を `_apply_pane_layout` 〜
    `setFocus` 〜 `_restore_selection_by_paths` の順 (= eventFilter による
    inbox.clearSelection を間に挟むことで preview を正しく更新)
  - **再度のユーザー検証で方針転換**: 実際使うと Inbox を連続でさばく workflow が
    高頻度 → 毎回 case pane に focus が飛ぶと Tab で戻す手間が大きい →
    `focus_on_destination` 撤去、`_populate` フォールバック (= Inbox 隣ファイル
    自動選択) のみで運用
- ✅ **Name 列幅同期の補強 (ADR-18 補強)**:
  - `case_pane.subfoldersChanged` シグナル → `_apply_pane_layout` 直接接続
    (refresh_current_view の都度発火するので、リネーム/移動後に再計算が走る)
  - `inbox_pane.inboxChanged` → `_on_inbox_changed` 経由で `_apply_pane_layout`
    を呼ぶよう追加
  - リネーム/操作で table viewport が微妙にずれるケースの保険

#### テスト
- ✅ 102 件 pass (67 + version 23 + updater 12)。後続課題: M5e の UI 追加分
  (UpdateBanner / 検索フィルタ / 選択 fallback) は手動検証のみ、ヘッドレス
  unit テストを追加するなら別セッションで対応

#### 配布
- ✅ `v0.1.0-beta.1` prerelease in GitHub Releases、CI artifact
  `k-file-windows.zip` 添付済
- ユーザー差し替え (β.1 初回): Win 機で zip DL → 展開 → 起動
- ユーザー差し替え (β.2 以降): 起動済 k-file の通知バナーから 1 クリック → 自動 DL
  → 確認 → 再起動で完了

---

## 8. 次にやること

### M5f フリーズ根治 Phase 1 完了 (2026-05-29) → 実機様子見 → 残れば Phase 2

β.1 配布後、ユーザー業務並走で「**ファイルをクリックした時 / 移動・リネームした
直後にアプリが固まり、強制終了せざるを得ない**」フリーズが頻発と報告。調査の結果、
症状は「見た目は普通だが無反応」= **メインスレッドが同期 I/O でブロック**される
典型 (例外クラッシュではない。`error.log` は `SystemExit:0` のみで crash 痕跡なし)。

**根本原因** (詳細 §15 ADR-29):
- 事件フォルダは **Dropbox をレジストリで X ドライブにマウント**して X: 経由参照。
  Dropbox の「オンラインのみ (placeholder)」ファイルは **read した時に** hydrate
  完了まで長時間ブロックする (stat だけなら比較的速い)。
- preview_pane が PDF/画像/テキストの read+デコードを**メインスレッドで同期実行**
  していた = ファイルをクリックする度に最高頻度で X: read。これが主犯。
- Inbox は全てローカルなので無傷。「事件 (X:) 側操作でだけ固まる」非対称と一致。

**Phase 1 (完了・push 済 commit `5a46013`)**: preview の読込を `QThreadPool` worker
へ全面的に逃がした (ADR-29)。stat/read/QImage デコードは worker、main は結果から
GUI 構築のみ。seq 採番で連打 stale 破棄、150ms 超で「読込中...」表示。テスト
`tests/test_preview.py` 10 件追加 (全 112 件 green)。CI 成功 = artifact
`k-file-windows` (48MB)。

#### 次セッションでやる優先順

1. **Phase 1 の実機検証** (ユーザーが様子見中) ← まず最優先
   - artifact zip を DL → 差し替え → 業務で使う (今回はタグなし push のため
     **Release は作られず自動アップデート通知は出ない。手動 DL 差し替え**)
   - ✅ 確認: ファイルクリック → プレビューで**固まらなくなったか** (Phase 1 の本命)
   - △ 確認: **移動・リネーム直後の固まり**が軽くなったか / まだ残るか
2. **Phase 2 (残った場合): 事件フォルダ走査の非同期化**
   - `core/folder_scanner.scan_case_folder` / `list_folder` を worker へ。呼び出し点:
     `case_pane._load_case` (タブ切替)、`_browse`/`_show_current`、`refresh_current_view`
     (move/rename/inject/delete 後)、右クリック `_build_case_submenu`。
   - case_pane.py (1804 行・最複雑) のナビ非同期化は高リスク (self._scan セット→
     ボタン再構築→browse の順序依存、走査中クリック競合)。preview と同じ seq-guard
     パターンで。安全な前哨として `scan_case_folder` の per-subfolder カウントを
     `iterdir()+is_file/is_dir` (entry 毎 2 stat) → `os.scandir()` (dirent キャッシュ)
     に変える純関数最適化も有効 (要 folder_scanner テスト追加、現状未整備)。
3. **Phase 3 (任意の掃除)**: IPC の同期待ち (`ipc.py` の `waitForReadyRead(500)` +
   `waitForDisconnected(200)`、K-SystemZ 連打で累積) の非同期化 + `main.py:148` の
   `except BaseException` が正常終了 (`SystemExit:0`) まで error.log に書く副次バグ修正。

### M5e 完了 (2026-05-27) → `v0.1.0-beta.1` 切り済 → Win β 検証 + 業務並走

M5e で β 配布前の polish + 自動アップデート機構 案② 実装、`v0.1.0-beta.1` を
2026-05-27 にタグ切り。CI 成功で Releases に prerelease + `k-file-windows.zip`
upload 済。**ここから先は Win 機での β 業務並走テスト** に移行。

#### 次セッションでやる優先順

1. **Win β.1 検証 (= 業務並走の入口)** ← まず最優先
   - Win 機で zip DL → 展開 → 起動 → 業務並走で 1〜2 週間使う
   - **特に未 Win 検証の項目** (M5e で入った変更を実機で確認すべき):
     - ウインドウ外クリックで preview が消えないこと (ADR-28 で撤回した
       defensive clear がファイルロックを再発させないか)
     - F3 close → 再 F3 で前ファイル即表示 (同上)
     - Ctrl+F 絞込検索 が日本語ファイル名で動くこと
     - 選択追従系 (rename/move/delete 後の隣接行 + プレビュー) が違和感なく動くこと
     - Name 列幅同期がリネーム/移動操作で崩れないこと
   - 自動アップデート機構自体は β.2 を出すまで実発火しない (= 今回は無動作確認のみ)
2. **β.1 で問題が出れば β.2 → 自動アップデート初回実発火確認**:
   - β.1 で残バグや要望が出る → 直す → `VERSION = "0.1.0-beta.2"` で再タグ切り
   - β.1 .exe が稼働中なら、起動時通知バナー → 「更新...」 → 自動 DL → 再起動 → β.2
     という**自動アップデート機構の本番初動作確認**になる
3. **β → v1.0 stable**: 1〜2 週間の業務並走で大きい問題が出なければバージョン上げ

### β タグの切り方 (覚え書き)

1. `src/__version__.py` を `VERSION = "0.1.0-beta.X"` に編集
2. commit + push
3. `git tag -a v0.1.0-beta.X -m "..."` (annotated tag、`v` prefix 必須 CI 条件)
4. `git push origin main --follow-tags`
5. CI (`.github/workflows/build.yml`) が走り、`v*` タグでは Releases に
   prerelease で zip upload される
6. 次回 dev 開始時、必要なら `VERSION = "0.1.0-beta.(X+1)-dev"` に戻す

### 自動アップデート機構の状況 (M5e で実装済の案②)

- 起動 1.5 秒後に裏で `https://api.github.com/repos/windom21-cpu/k-file/releases`
  を 1 リクエスト → 最新 release の zip asset を見て、ローカル version より新しければ
  status bar 左に「🔔 v0.1.0-beta.X が公開されました [更新...] [×]」を表示
- 「更新...」 → 確認 → `QNetworkAccessManager` で zip DL (進捗ダイアログ) →
  `%APPDATA%/k-file/updates/k-file-windows.zip` 保存
- DL 完了 → 確認ダイアログ「今すぐ再起動して適用しますか？」 → updater バッチを
  `%APPDATA%/k-file/updates/apply_update.bat` に書き出し → `subprocess.Popen` で
  detached 起動 → k-file 自身を `close()` で終了
- updater バッチ (`src/core/updater.py::write_updater_batch`):
  1. `tasklist | findstr k-file.exe` で k-file プロセスが消えるまで wait (最大 30 秒)
  2. install_dir (= k-file/) を install_dir.old/ にリネーム
  3. PowerShell `Expand-Archive` で zip を install_dir/ に展開
  4. install_dir/k-file.exe を起動 (start /b で detach)
  5. install_dir.old/ を削除 (失敗しても黙る)
- dev 実行 (= `python -m src.main`、`sys.frozen` 無し) では適用ステップで
  「dev mode では自動適用無効」メッセージを出して終わる (DL までは動く)
- 設定ダイアログ「自動アップデート」セクションで OFF 可能 (DB key
  `auto_update_check_enabled`)

### M5c 完了 (2026-05-25) → 2 回目検証 (2026-05-26 ✅ 完了) → M5d 反映 (済)

M5c で 1 回目 Win 機本番テスト報告 (プレビューロックで削除不能 / Inbox 2 倍表示 /
タブ氏名空 / 単一インスタンス未対応 / 0KB スキャン / Office・JSON プレビュー欠如
等) を一括解消。

2 回目 Win 機検証 (CI run `26435251281` の zip artifact 相当を `python -m src.main`
で dev 実行、PySide6 6.11.1 cp310-abi3) で M5c 全項目検証 → 残バグを M5d で解消
→ ユーザー業務並走で「問題なし」を確認、β タグ準備完了。

### M3/M4/M5 完了 (2026-05-23) → 1 回目 Win 機検証 (済) → M5c 反映 (済)

### dev の足場 (M5 で正式化される仮実装)
- 事件フォルダ: `~/k-file-test-data/事件/` を `case_pane.py` の `_DEV_DOC_ROOT`
  で直読み → M5 で ksystemz.db +「事件を開く」ダイアログに置換
- Inbox 監視対象: `~/k-file-test-data/inbox-{scan,desktop,work}` + 実 `~/デスクトップ`
  を `inbox_pane.py` の `_DEV_INBOX_SOURCES` で直指定 → 設定ダイアログ +
  kfile.db settings に置換 (本番は scan/Desktop/作業 をユーザーがパス選択)
- テストデータは `~/k-file-test-data/` に合成 (ネスト 3 階層・欠番サブ
  フォルダ・実 PDF/画像入り)。リポジトリには含めない (`.gitignore`)

### M5 で実装する範囲

**ksystemz.db は持ち出さず、引き継ぎ書スキーマからモックを生成して Linux で実装する**
(ADR-14)。本物の K-SystemZ コードや実 DB は Win 機にしかなく、業務データを
含むため持ち出し不可。引き継ぎ書 (`~/ダウンロード/AI引き継ぎ_詳細版_v22.md` /
`AI引き継ぎ_セッション_20260521.md`) にスキーマと API ロジックが完全に記載
されているので、それを元にモック DB と実装を Linux で完成、Win 機で実 DB
に対して検証、というワークフローで進める。

#### Phase A (Linux 本機): モック生成
- `tests/fixtures/build_mock_ksystemz_db.py` — 引き継ぎ書のスキーマで
  `~/k-file-test-data/ksystemz.db` を生成:
  - `office_info` (id=1): `doc_root_path = ~/k-file-test-data/事件`
  - `cases` 10 件: `case_code = R060200042..R060200051` (既存テストデータと整合)
  - `case_persons` + `persons`: 各事件に依頼者 1 人 (架空の名前)

#### Phase B (Linux 本機): 実装
- `core/case_repo.py` — sqlite3 `mode=ro` 接続 + 事件検索 (cases ← case_persons
  ← persons の join、case_code/case_name/依頼者名で AND/OR フィルタ) +
  `case_code` 前方一致での実フォルダ解決
- `ui/open_case_dialog.py` — Ctrl+O で開くモーダル (Win95 風 frameless)。
  検索ボックス + 一覧 + 「開く」ボタン。選択した事件を case_pane のタブに追加
- `ui/settings_dialog.py` — Inbox 監視先 (パス + cutoff_days を可変リストで)、
  ksystemz.db パス、kfile.db の場所表示 (情報のみ)。`kfile.db.settings` に保存
- `case_pane.py` 改修 — `_DEV_DOC_ROOT` 廃止、`case_repo` 経由で事件パス取得
- セッション復元 — 起動時に `open_tabs` テーブルから前回タブを再オープン
- フォルダ D&D で事件タブ追加 — メインウインドウへの drop を受けて case_pane へ
- 単体テスト — `case_repo` の検索/解決をモック db で網羅

#### Phase C (Win 機): 実 DB 検証 (1 回目 ✅ 2026-05-25 / 2 回目 ← 次にやること)

**1 回目 (2026-05-25)** の検出事項は M5c で全て反映済:
- 削除/移動/リネーム不能 (PDF プレビューロック) → ADR-22
- タブ氏名表示が空 (実環境の命名規則対応漏れ) → `_parse_case` 拡張
- K-SystemZ から呼ぶたびウインドウ増殖 → ADR-20 (M6b 単一インスタンス)
- 0KB スキャン表示 → 5 秒猶予 + debounce
- Office/メモ帳ファイルが Inbox に出ない → ホワイトリスト撤去 (ADR-19)
- `.k-photo` 等サブアプリ JSON 非表示 → ブラックリスト方式 + プレビュー対応
- フォーカス周りの選択残留 → Tab/click で相手選択クリア
- Desktop 2 件設定で 2 倍表示事故 → dev デフォルト整理 + dedupe 保険

**2 回目 (✅ 2026-05-26)**: Win 機 dev 実行 (`.venv\Scripts\python.exe -m src.main`、
Python 3.14.3 + PySide6 6.11.1 cp310-abi3) で検証。検出事項は M5d で全て反映済:
- F2 リネームが「別のプロセスが実行中です」で失敗 (M5c QPdfDocument.close 単独
  ではハンドル残留) → ADR-23 QBuffer 経由読込みに切替で根治
- F2 ダイアログ開いた瞬間に preview が消える → ADR-22 補足 `_internal_modal_count`
  フラグで自前 modal を判別、preview 維持
- リネーム後・Inbox auto refresh 後に「選択ファイル ≠ プレビュー」または
  「意図と違うファイルが移動」 → ADR-24 path 集合保存・復元で根治
- 事件タブ間で **Copy 動線が無い** → ADR-25 Ctrl+D&D + 右クリックの 2 系統追加
- K-SystemZ サブアプリ拡張子 `.k-photo` が誤称、実際は `.kphoto`/`.kevi`
  (ハイフン無し) → dotfile 例外を `.k` に緩和、プレビュー JSON 対象に追加

**問題なしと確認できた項目** (β タグ前提クリア):
- `.kphoto`/`.kevi` プレビュー (上記対応で動作確認)
- デスクトップフォルダの Inbox → 事件サブフォルダ移動
- K-SystemZ から連打 → ウインドウ単一性 (ADR-20 IPC)
- 日本語フォルダ名 (㈱、㊗、機種依存文字) のパス解決
- case_code 前方一致衝突
- Win .lnk 解決 (PowerShell COM 経由)

**並行作業** (K-SystemZ 側): 2026-05-26 にユーザー連絡で `_is_kfile_running()`
撤去 + psutil 依存削除完了 (返信書 `X:\K-system\k-systemz向け_k-file連携状況_260526.md`)。
K-SystemZ 側は毎回 `subprocess.Popen([kfile_exe, *paths])` を呼ぶだけで OK、
ウインドウ集約は k-file 側 IPC が担う。

### 着手前メモ
- Win .exe ビルドで QtPdf モジュール/プラグインの同梱を確認 (`k-file.spec` / CI)
- `core/` のテストは file_ops / undo_ops / inbox_watcher は緑、`folder_scanner` 未整備
- `case_pane.py` から `_DEV_DOC_ROOT` を外す際、現在の動的サブフォルダ走査 +
  ネスト降下ロジックはそのまま流用可

---

## 9. データモデル / 永続化

### 読み取り専用ソース (K-SystemZ)
- `ksystemz.db` の `cases` テーブル: `case_code`、`case_name`、`status`、`case_type`、`folder_path` 等を参照
- `ksystemz.db` の `office_info` テーブル: `doc_root_path` (Win 用) / `doc_root_path_mac` (Mac 用) を参照
- `sqlite3.connect("file:" + path + "?mode=ro", uri=True)` で接続。Dropbox 同期下のため絶対に書き込まない。

### k-file 専用 DB (kfile.db) の配置
- Linux: `~/.config/k-file/kfile.db`
- Windows: `%APPDATA%\k-file\kfile.db`
- Mac: `~/Library/Application Support/k-file/kfile.db`
- **ローカル配置厳守** — Dropbox 同期下に置かない (機械ごとに独立した履歴)

### kfile.db テーブル
| テーブル | 用途 |
|---|---|
| `drop_history` | 投入・rename・削除・cross-case 移動の全履歴 (Undo 用): id, action ('inject'/'rename'/'delete'/'move'), src_path, dst_path, case_code, category, renamed_to, original_name, status, executed_at, thumb_cache_path |
| `recent_names` | 最近使った名前 (rename 候補): name, last_used_at, use_count |
| `ignored_files` | Inbox 表示から除外したファイル: src_path, ignored_at |
| `open_tabs` | セッション復元用 (前回開いていた事件タブ): case_code, tab_order, last_opened_at |
| `settings` | Inbox 監視対象パス、ksystemz.db パス、フィルタ設定、ソート順など (key/value) |

### ファイル実体方針
- 独自フォーマットを作らない。実ファイルそのものを Copy / Move / 削除のみ。
- 「最悪 Explorer で扱える状態」を常に維持。
- **Inbox → 事件**: Copy → 検証 → 元削除 (途中失敗時は元が残るため安全)。
- **事件 → 別事件 (cross-case D&D)**: Move (`shutil.move`)。Dropbox の 30 日履歴 + 自前 Undo が保険。
- **削除 (Del)**: `send2trash` で OS ごみ箱へ。drop_history に経路記録。Undo は OS ごみ箱からの復元を試行 (失敗時はユーザーに通知)。
- **衝突回避**: dst に同名ファイルがあれば自動連番 (`name (2).ext`、`name (3).ext`、...)。ステータスバーで通知。
- Undo: drop_history を遡り逆操作を実行。アクション別の逆操作を実装 (inject ↔ 元位置に戻す / rename ↔ 旧名に戻す / delete ↔ ごみ箱から復元 / move ↔ 逆方向 move)。

---

## 10. ファイル構成 (予定)

```
k-file/
├── src/
│   ├── main.py            # entry
│   ├── ui/                # PySide6 widget 群
│   ├── core/              # ドメインロジック (Qt 非依存)
│   └── infra/             # 永続化・OS 連携
├── resources/
│   └── style/win95.qss    # Win95 QSS
├── tests/
├── docs/                  # ノウハウ集
├── .github/workflows/     # CI
└── HANDOVER.md            # 本ファイル
```

---

## 11. 環境セットアップ

### Linux 本機 (Ubuntu 24.04 想定、開発用)
```bash
# 初回のみ: apt で python3-venv / python3-pip を入れる (Ubuntu 24.04 ではデフォルト未導入)
sudo apt install -y python3-venv python3-pip

# クローン + venv + 依存インストール
cd ~/デスクトップ/k-file
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 起動
python -m src.main
```

注意:
- Python 3.12 を使う (k-systemz の Mac venv と揃え、CI も 3.12)
- `requirements.txt` は `==` でピン留め (PySide6==6.11.1, pyinstaller==6.20.0)
- Linux には MS UI Gothic が標準でない → 代替フォントで表示される。実 UI 確認は Win 機で実施

### Win 機 (配布先 / 業務機)
1. CI で生成された `k-file.exe` を GitHub Actions の artifact または Releases から DL
2. ダブルクリックで起動 (PyInstaller --onefile のため初回展開で数秒)
3. インストーラ不要、単一 .exe で動く

### 開発用 Git 設定 (claude セッション後、ユーザ側で 1 回だけ)
```bash
git config --global user.name "windom21-cpu"
git config --global user.email "279377893+windom21-cpu@users.noreply.github.com"
```
(初回 commit は環境変数で渡したため、以降のために設定推奨)

---

## 12. リポジトリ・配布インフラ

- **URL**: https://github.com/windom21-cpu/k-file
- **可視性**: public (CI 分数無制限のため。業務データは含まれず、コードのみのため公開可)
- **配布方針**: 単一リポ + GitHub Releases に直接 upload (k-pdf3 のような separate releases repo は採用しない、当面)
- **CI トリガ** (`.github/workflows/build.yml`):
  - `main` ブランチへの push → .exe を 90 日 artifact 保存 (Actions タブから DL 可)
  - `v*` タグ push → Release 作成 + .exe upload (β は prerelease)
  - 手動実行 (`workflow_dispatch`) も可
- **β / stable 区別**: v0.x.0-beta.N → prerelease、v1.0.0+ → stable

---

## 13. K-PDF3 からの継承と破棄

**継承**:
- 協働スタイル全般
- レトロ UI 最優先方針
- HANDOVER 運用ルール (明示依頼時のみ更新)
- マイルストーン制バージョン運用
- 本機 (Linux) ↔ Win 機の往復ワークフロー
- CI race 教訓 (publish は 1 OS から、`docs/CI-CD.md` 参照)

**破棄 / 不適用**:
- mupdf / qpdf / Sumatra / Adobe 連携 (PDF 専用、k-file には不要)
- Electron autoUpdater (PySide6 にはネイティブ等価物なし、当面手動 DL)
- 98.css (Web 用、PySide6 には QSS で別途実装)

---

## 14. AI セッション交代時の注意

- 新セッション開始時、まず `CLAUDE.md` → 本 HANDOVER.md → `docs/COLLABORATION.md` の順
- HANDOVER.md は **明示依頼時のみ更新**
- 過去の決定を覆す前に、ユーザーに「なぜそうしたか」を確認

---

## 15. 既知の制約 / ADR 状況

### ADR-1: サブフォルダボタンは「左クリック＝閲覧 / Alt・右クリック＝投入」(2026-05-22)
- **決定**: サブフォルダボタンの左クリックは閲覧専用 (ファイルを動かさない)。投入は Alt+0〜9 / 右クリックメニュー / D&D。
- **理由**: 「クリック＝即投入 (Inbox 選択中)」だと、仕分け作業中 (＝ Inbox でファイル選択中が常態) にサブフォルダの中身を見ようとした瞬間に誤投入が起きる。閲覧と投入を入力方法で分離して解決。
- §6 の Alt 仕様 (選択中なら投入 / 未選択なら閲覧) は維持。未定義だった「クリック時の挙動」を「閲覧専用」に確定。

### ADR-2: フォルダの OS 既定ハンドラは乗っ取らない (2026-05-22)
- **要望**: 「フォルダを開くと原則 k-file で開く」(Explorer とは両立、アンインストールで元通り)。
- **決定**: Windows の `Directory\shell\open` verb 乗っ取りはしない。理由: (a) フォルダはファイル種別ではなく per-type の既定アプリ機構が無い → 乗っ取りは全文脈 all-or-nothing で「両立」と矛盾、(b) Explorer 内ダブルクリックは verb を経由しない内部移動で結局効かない文脈が残る、(c) グローバル verb 改変は壊れやすく Windows Update 耐性も低い。
- **代替 (採用)**: ①任意フォルダを k-file のタブで開けるようにする (k-file 内ダブルクリック→タブ)。②事件フォルダの親 (doc_root) を k-file タブで開けば配下は全部 k-file 内で扱える。③K-SystemZ の「フォルダを開く」を `k-file.exe "path"` 呼び出しに変更。④右クリック「k-file で開く」。これらは OS 無改変・アンインストールで完全可逆。
- **保留**: 「Explorer 内ダブルクリック → k-file」の literal 実現は、やるとしても M6 で Win 実機実験 → 上級者向け自己責任トグル止まり。製品既定には組み込まない。

### ADR-3: ネストフォルダはファイル一覧の「フォルダ行」で表示 (2026-05-22)
- **経緯**: M2 で当初「階層タブ」(横タブ帯) を実装したが、子フォルダが多い (年度フォルダ 12 個等) と横タブが破綻する。
- **決定**: 子フォルダをファイル一覧に「行」として表示 (先頭にまとめ・サイズ欄「フォルダ」)。ダブルクリックで中へ、パンくずで戻る。
- **理由**: 縦一覧はスクロールで何個でも捌ける。Explorer 同様の直感。ツリービューではない (常に 1 階層のフラット一覧 + ドリルダウン) ため禁止事項に抵触しない。

### ADR-4: 列ヘッダー左クリック=ソート / 右クリック=列メタ操作 (2026-05-23)
- **経緯**: サイズ列で「KB ↔ MB 切替」のリンクをヘッダーに置きたかったが、左クリック (= ソート) と同時に切替が起きて UX 上混乱した。
- **決定**: 列ヘッダーの**左クリックはソート専用**、**右クリックは列のメタ操作 (KB/MB 切替、将来の他フォーマット切替等)** に分離。サイズ列のヘッダーラベルは「サイズ」のみ (現単位は値側に出る)。
- **理由**: ソートと表示フォーマット切替は役割が違う (ユーザー指摘)。同じヘッダーに混在させると、片方を意図しただけでもう片方が動いてしまう。Win 標準のヘッダー操作とも整合 (Explorer のヘッダー右クリックは「列の表示/非表示」メニュー、k-file ではそこを単位切替に使う)。
- **両ペイン独立**: Inbox と参照フォルダの単位は別々に切替可 (混在許容)。連動が望ましければ後で MainWindow 経由で共通状態化する余地あり。

### ADR-5: ペイン幅は動的計算で「視覚均等」、splitter handle=0 で固定配置 (2026-05-23)
- **経緯**: 中央ペインに左サブフォルダボタン列 (固定 ~140px) があるため、`splitter.setSizes` を素朴に 1:1 にすると「Inbox とファイル一覧の見た目」が約 20% 不均衡になる。手動で毎回 splitter を動かさせるのも UX が悪い。
- **決定**: `MainWindow._apply_pane_layout` で `inbox = (total - strip_width - case_left_offset - handle) / 2` を毎回計算し、「Inbox 幅 ≒ 中央ファイル一覧幅」が常に成立するよう設定。`splitter.setHandleWidth(0)` で手動 drag を無効化 (固定レイアウト) し、副次的に Inbox 右辺と CasePane 左辺の sunken 縁を「ペインの暗 2px + 中央ストリップの明 1px」で対称化する余地が生まれる。
- **理由**: 法律事務の実機は 1920×1080 / 1600×900 等まちまち。固定比率では一つに合わせると別で破綻する。動的計算 + 固定配置で全環境で同じ見た目を保証。F3 トグル (2 カラム ↔ 3 カラム) でも再計算される。

### ADR-6: Inbox と参照フォルダの間に「中央コマンドストリップ」(2026-05-23)
- **経緯**: マウス派ユーザーのために、頻用操作 (投入 / 無視 / Undo) のボタンを置く場所が欲しかった。
- **決定**: Inbox と参照フォルダの間に縦バー (幅 28px、`src/ui/command_strip.py`) を置き、`▶▶` 投入 / `✕` 無視 / `↶` Undo を縦中央に配置。Norton Commander / Total Commander の中央コマンド列に倣う設計。
- **後続**: M3 で `▶▶` 1 個 → サブフォルダ対応の動的 `>1`〜`>0` 群に拡張 (ADR-8)。

### ADR-7: 投入は即実行 / rename ダイアログは F2 のみ (2026-05-23)
- **経緯**: M3 初版では Alt+0〜9 / D&D / `>>` ボタンすべてで rename ダイアログ (`Esc=元名のまま投入` / `Enter=入力名`) を出していたが、マウス派/キー派ともに「ダイアログが邪魔、移動は素早く実行したい」という反応。
- **決定**: **投入・移動系はすべて即時実行** (Alt+0〜9 / 右クリックメニュー / D&D / ストリップ数字ボタン)。衝突時は自動連番 + ステータスバー通知のみ。rename したい時は **F2 で別途リネーム** (Windows 標準動線)。
- **理由**: 投入とリネームは別概念。投入の中で rename を要求すると思考が止まる。Windows Explorer 流儀 (Ctrl+X → Ctrl+V は即実行、F2 で rename) と整合。

### ADR-8: 中央ストリップ = 動的 `>1`〜`>0` ボタン群 (2026-05-23)
- **経緯**: `▶▶` 1 個では「どのサブフォルダに投入したか視覚化されない」。マウス派は事件ごとに変わるサブフォルダ群に対応した投入ボタンが欲しい。
- **決定**: ストリップに **現在事件のサブフォルダ alt_key に対応した `>1`〜`>9` + `>0` (事件フォルダ直下)** を動的に配置。1 クリック = 投入 + そのフォルダを開く (Inbox 未選択時は閲覧のみ)。`>` の向きで「Inbox から右へ移動」を視覚化。
- **連動**: 事件タブ切替・サブフォルダ +/− でストリップが自動再構築 (`CasePane.subfoldersChanged` → `MainWindow._sync_strip_targets`)。

### ADR-9: `<<` = 実 OS デスクトップへ戻す (2026-05-23)
- **経緯**: 中央から Inbox 方向の逆動線が欲しい (誤投入の戻し / 一旦保留して別事件に運ぶ)。
- **検討**: (a) k-file 管理の「保留」フォルダ案、(b) 既存 Inbox 監視先のどれかへ戻す案、(c) 実 Desktop へ戻す案、(d) cross-case Move のみで対応する案。
- **決定**: **(c) 実 OS デスクトップへ送る**。理由: 実 Desktop は OS 管理で消えない (k-file 管理の独自フォルダは k-file が消えると不安)。実 Desktop を Inbox 監視対象に追加すれば round-trip も成立。
- **実装**: ストリップ `<<` ボタンで `file_ops.move(src, ~/デスクトップ)` 実行 + history 記録。Inbox 監視に実 Desktop を追加 (同名 "Desktop" ラベルで合流、`cutoff_days=7` で古いファイル抑制)。

### ADR-10: フォルダ動線ボタンはパス行右に集約 (2026-05-23)
- **決定**: 事件フォルダ単位の操作 (シェル系) は **パス行の右** に。サブフォルダ単位の操作 (構成系) は **サブフォルダ列の下** に。
- **配置**:
  - パス行右: 「他事件へ」(ショートカット作成、AB 集約用)
  - サブフォルダ列下: `+ 追加` / `− 削除`
- **理由**: 操作対象 (事件全体 vs サブフォルダ単位) と空間的対応を一致させる。`+ -` は左列のサブフォルダ群の延長、シェル系は事件のパス表示の延長。

### ADR-11: 他事件への集約は直接ショートカット配置 (2026-05-23)
- **経緯**: 夫婦事件 (AB) のような関連事件で、文書を A に集約し B には A への入口だけ残す運用がある。当初は「事件 → デスクトップ shortcut → Inbox → 他事件 root へ D&D」を想定したが、Inbox はフォルダリンクを拾わないため不成立。
- **決定**: パス行に **「他事件へ」ボタン** を追加。クリックで他事件タブのメニュー → 選択で **現事件 root のショートカット (Win: .lnk / Linux: symlink) を直接 target 事件 root に作成**。デスクトップ経由不要。
- **理由**: 集約マーカは「事件間の関係」を表すもので、デスクトップ経由は中間ステップが多すぎる。k-file 内で完結する直接動線が業務ループに乗る。

### ADR-12: Inbox ソースごとに `cutoff_days` フィルタ (2026-05-23)
- **経緯**: Desktop を Inbox 監視に入れると過去の蓄積 (PDF 数十件) が Inbox に並んで邪魔。
- **決定**: `InboxSource` dataclass に `cutoff_days: int | None` を追加。指定がある時は「現在時刻から N 日より古い更新日時」のファイルを除外。scan/作業 は `None` (全件)、Desktop は `7` 日。
- **将来**: M5 設定ダイアログでユーザーがソースごとに編集可能にする。

### ADR-13: trash の Undo は OS Recycle Bin に委譲 (2026-05-23)
- **経緯**: Del → OS ごみ箱 (`send2trash`) は OS 標準の安全動線だが、自動復元が OS 依存で fragile。Win では `Shell.Application` COM が locale 依存 (動詞名 `Restore` vs `元に戻す`) で誤動作リスクあり。
- **決定**:
  1. `Ctrl+Z` は **trash エントリをスキップ** (`db.last_undoable_entry` の SQL で `action != 'trash'`)
  2. 直近 trash の前にあった inject/move/rename が Undo 対象になる
  3. trash 復元は **Windows ネイティブの Recycle Bin 右クリック「元に戻す」** に委譲
  4. k-file は動線を提供: Del のステータスメッセージで案内 + 編集メニュー「ごみ箱を開く」(`explorer.exe shell:RecycleBinFolder`) で 1 クリックで起動
  5. F12 履歴ビューの trash 行「戻す」ボタンは具体的な動線メッセージ (ファイル名 + 編集メニュー案内)
- **理由**: PowerShell COM 経由の自動復元は locale 依存で誤上書きリスクあり。Win ユーザーは Recycle Bin の右クリック「元に戻す」に慣れているため、それに委譲する方が安全かつ直感的。

### ADR-15: 起動時の事件タブ自動 load を撤去 (2026-05-23)
- **経緯**: M2 dev では `case_pane._load_case_tabs` が `_DEV_DOC_ROOT` 直下の事件フォルダを全件自動 load していた。M5 で ksystemz.db + 設定 + セッション復元が揃ったため、自動 load は意味を失った (むしろ ksystemz と無関係なフォルダまで開いてしまう)。
- **決定**: 起動時は **タブを空で開始**。事件タブは以下のいずれか経由で追加する:
  1. **セッション復元** — 前回 `open_tabs` に保存された事件を順次 add_case_tab (case_repo.resolve_folder 経由)
  2. **Ctrl+O「事件を開く」ダイアログ** — ユーザーが意識的に選択
  3. **フォルダ D&D** — k-file ウインドウへの drop で 1 件以上のフォルダを事件タブとして追加
- **理由**: 業務フロー上「どの事件を扱うか」を最初に決めるのが自然。空タブから始まる方が「Ctrl+O で開いて作業 → 終わったらタブを閉じる」というリズムに合う。dev 用フォールバック (`_DEV_DOC_ROOT` 全件 load) は撤去。
- **副作用**: 初回起動は完全な空状態。Linux dev でも `Ctrl+O` (モック ksystemz.db に対して) でアクセスする。

### ADR-16: 事件ショートカットはダブルクリックでタブ切替 (descend しない) (2026-05-23)
- **経緯**: ADR-11 で「他事件へ」ボタンが B 事件 root に A のショートカット (Linux symlink / Win .lnk) を作る挙動を入れたが、k-file 内でこのショートカットをダブルクリックすると B のタブ context のまま A の中身が表示され、パスバーが「事件フォルダ: B... > A事件」になって不自然 (A は B のサブフォルダではない)。
- **決定**: 事件 root 直下のショートカットがダブルクリックされた時:
  1. `resolve_shortcut(path)` で target を解決 (Linux: `Path.resolve()`、Win: PowerShell COM 経由)
  2. target が ksystemz の `doc_root` 直下なら **caseShortcutActivated** シグナルを発火 → MainWindow が `add_case_tab(target)` で **A のタブに切替** (なければ新タブ追加)
  3. doc_root 直下でなければフォールバック (Linux symlink-to-dir なら通常 descend、Win .lnk なら何もしない)
- **視覚的目印**: 事件ショートカット行は `↗` プレフィックスを表示、Win .lnk は `.lnk` 拡張子を表示から省略
- **scan_case_folder 改修**: symlink/.lnk は **左ボタン列の `dirs` には入れず `root_files` に入れる** (事件ショートカットはカテゴリ分類ではなく「別事件への入口」として「0 事件フォルダ直下」ビューに表示する方が意味論的に正しい)
- **物理的なファイルはそのまま** (Explorer/Nautilus でもダブルクリックして開ける)。k-file 内だけ「事件タブ切替」と再解釈する。

### ADR-14: K-SystemZ 連携はモック DB ベースで Linux 実装 (2026-05-23)
- **経緯**: K-SystemZ 本体 (FastAPI/React/SQLite) と実 ksystemz.db は Win 機にあり、業務データを含むため Linux 本機に持ち出せない。だが K-SystemZ 引き継ぎ書 (`~/ダウンロード/AI引き継ぎ_*.md`) には完全なスキーマと API ロジックが記載されており、Linux 上で参照可能。
- **決定**: M5 K-SystemZ 連携は **引き継ぎ書スキーマからモック ksystemz.db を生成して Linux で実装** → CI で .exe ビルド → Win 機で実 DB に対して検証 → エッジケース修正、というワークフローで進める (HANDOVER §8 Phase A/B/C 参照)。
- **守るべき**: モック DB は完全にフィクション (架空の依頼者名 / case_code R060200042..)、リポジトリには `ksystemz.db` を一切含めない。本物の DB は Win 機側のみで運用。
- **Phase C (Win 機検証) で発見されたエッジケース** は Win 機側で修正 push → 本機 pull、または本機で再現可能なら本機で修正。

### ADR-17: MS Gothic は埋め込みビットマップ + AA オフを全 widget に強制 (2026-05-24)
- **経緯**: Qt は標準で TrueType ベクトル + アンチエイリアスで描画するため、
  fontconfig 側で `embeddedbitmap=true` を指定していても無視され、「滑らかな
  MS Gothic 風」になって当時の Win95/98 質感が出ない。QSS 側で `font-family`
  を指定すると Qt が QFont の `StyleStrategy` をリセットするため、`QApplication.setFont`
  だけでは継承されない。
- **決定**: ヘルパ `src/ui/_font_strategy.py::apply_bitmap_font_strategy(root, point_size=None)`
  を新設し、MainWindow + 全ダイアログ (About / Settings / OpenCase / Rename /
  History) で **QSS 適用後の widget tree を walking** して `QFont.StyleStrategy(PreferBitmap | NoAntialias)`
  を再付与。`QToolTip.setFont()` でもツールチップに同戦略を適用。
- **副次効果**: QSS の `font-family` 指定はもはや 1 箇所 (`*` グローバル) に集約可能になった
  (個別 rule は font-size のみ例外指定。`font-family` を書くとそこから下は再び strategy リセット)。
- **新規ダイアログを追加する時** は `apply_bitmap_font_strategy(self)` を `__init__` 末尾で呼ぶこと。
  ダイアログ 9pt なら `apply_bitmap_font_strategy(self, point_size=9)`。
- **動的に widget を再生成する場所** (事件タブ切替に伴う `case_pane._rebuild_subfolder_buttons()`
  / `command_strip.set_subfolder_targets()` 等) でも、新規 widget には QSS の
  `font-family` が再適用されて strategy が失われるため、生成直後に
  `apply_bitmap_font_strategy(self)` を呼ぶこと。これを忘れると「最初は
  ビットマップ MS Gothic、タブ切替したら滑らかなベクトル」というちぐはぐが発生する。

### ADR-19: Inbox は「監視先フォルダの中身をそのまま見せる」(2026-05-25)
- **経緯**: 初期設計では Inbox は `INBOX_EXTENSIONS = {.pdf, .jpg, ..}` のホワイトリスト方式で PDF + 画像のみ表示していた。本番テスト (2026-05-25) で「Word/メモ帳保存ファイルが拾えない」「`.k-photo` 等 k-systemz サブアプリ生成 JSON が見えないと業務にならない」「デスクトップに作った作業フォルダを事件サブフォルダに運びたい」要望が同時発生。ホワイトリストを拡張し続けても未知の業務拡張子が必ず取りこぼされる。
- **決定**: ホワイトリスト撤去 → **ブラックリスト方式** に転換 (`INBOX_EXCLUDE_EXTENSIONS = {.tmp, .part, ..}`, `INBOX_EXCLUDE_NAMES = {Thumbs.db, .DS_Store, desktop.ini}`)。ドット隠しファイルも原則隠すが `.k-*` 系は k-systemz 連携ファイルなので **明示的に通す**。**フォルダも Inbox に出す** (`InboxFile.is_dir` 追加、サイズ列 `<DIR>` 表示)。
- **副次**: `file_ops.inject` をフォルダ対応に拡張 (`shutil.move` 一発、サイズ検証は省略 = N ファイル byte-by-byte 検証は重く UX 劣化、複合機書き込みタイミング問題もファイル限定)。Inbox フォルダ行ダブルクリックで `add_case_tab` 経由で事件タブとして開く (M6a 汎用ファイラーと整合)。
- **理由**: 業務の現実 (法律実務家がデスクトップ作業フォルダ + サブアプリ JSON + Office ファイル を扱う) に Inbox を寄せる方が「k-file 内で完結」の理念に近い。ノイズ (`Thumbs.db` 等) はブラックリストで除外、ドット隠しは原則オフ + `.k-*` だけ例外で実用性と清潔さを両立。

### ADR-20: 単一インスタンス + IPC (M6b、2026-05-25)
- **経緯**: K-SystemZ から「フォルダを開く」を呼ぶたびに `subprocess.Popen(["k-file.exe", path])` で **別ウインドウが生まれる** → 業務的に使い物にならない (1 回目本番テスト報告)。
- **検討**: (a) K-SystemZ 側で `psutil` でプロセス重複検出 (実装済だが「呼ばない」だけで集約はできない)、(b) k-file 側で `QSharedMemory` + 単純なロックファイル (パス送信ができない)、(c) **`QLocalServer` / `QLocalSocket` で IPC** (送信できる)。
- **決定**: (c) を採用。`src/ipc.py` に `IpcServer` / `try_send_to_primary` を実装。secondary プロセスは起動時に primary に CLI 引数 (フォルダパス群) を改行区切り UTF-8 で送って exit。primary は受信後 `add_case_tab` でタブ追加 + ウインドウを raise/activateWindow。
- **副次**: K-SystemZ 側の「k-file.exe プロセス重複検出」は M6b 完了後 撤去可能 (連携設計の依頼事項)。
- **理由**: Qt 標準で Win/Linux/Mac 透過。Win では名前付きパイプ、Unix では `/tmp` ソケット。プロトコルキーは `k-file-instance-v1` で将来 schema 変更時に旧 server と隔離。

### ADR-21: PyInstaller `--onedir` + zip 配布 (2026-05-25)
- **経緯**: `--onefile` は起動毎に `%TEMP%` への展開コスト (3〜10 秒) があり、K-SystemZ から繰り返し起動する運用では業務リズムを壊す。
- **決定**: `k-file.spec` を `EXE(exclude_binaries=True) + COLLECT()` 構成に切替。CI で `dist/k-file/` フォルダ全体を `Compress-Archive` で zip 化、artifact / Release に `k-file-windows.zip` として upload。ユーザーは zip を任意の場所 (例: `C:\Apps\k-file\`) に展開し、中の `k-file.exe` を実行。
- **副次**: 配布物の運用が「単一 .exe 配布」→「フォルダごと配布」に変わる。配布ファイル数は増えるが、Win 業界の標準的な配置 (Program Files 風) なので問題なし。インストーラ (Inno Setup) が欲しくなれば後で別途追加可能。
- **理由**: 起動コスト改善 (3〜10 秒 → 1 秒程度) は業務並走の体感に直結。`--onefile` の唯一の利点 (単一ファイル配布) は K-SystemZ 連携で `office_info.kfile_exe_path` を 1 行設定するだけなので失っても痛くない。

### ADR-22: プレビューファイルロック解放を「操作前 / 状態遷移時」に分散 (2026-05-25)
- **経緯**: `QPdfDocument.load(path)` は Win 上で **ファイルハンドルを保持し続ける** ため、PDF を選択した状態のままだと send2trash / shutil.move / `Path.rename` が「使用中」エラーで失敗する。1 回目本番テストで「選択ファイルが削除/移動/リネームできない (自分が自分を掴んでいる)」として最も致命的な業務凍結級バグ。
- **決定**: `PreviewPane.clear()` で `QPdfDocument.close()` を明示呼出。以下の状態遷移時に必ず呼ぶ:
  1. 削除 / 移動 (inject/cross-case Move/`<<`) / リネーム 操作の直前
  2. F3 でプレビューを隠す時 (`_toggle_preview`)
  3. ウインドウが非アクティブになった瞬間 (`changeEvent`, `ActivationChange` → `!isActiveWindow()`)
  4. Inbox ↔ 中央テーブル の focus 切替 (Tab / マウスクリック、`eventFilter` で `FocusIn` を捕捉)
- **副次**: Inbox ↔ 中央テーブル間の focus 移動で相手側選択を `clearSelection` + `setCurrentCell(-1, -1)` する設計と一体 (= フォーカスが離れたペインは選択も離れる、ユーザー要望)。
- **理由**: 「常時 close」だとプレビュー継続が破綻するし、「ユーザー操作ごとに毎回 close」だとリスト操作のレスポンスが落ちる。状態遷移の境界 (操作直前 / 隠す瞬間 / フォーカス離脱) だけで close すれば「見ている間はロック、離れた瞬間に解放」という Win Explorer に近い直感的な振舞いになる。

### ADR-18: Inbox 幅 ≒ 中央ファイル名列幅 を resize の度に強制計算 (2026-05-24)
- **経緯**: 旧コードでは splitter に `setStretchFactor(0,1)(1,2)(2,2)` を設定して
  あったため、プレビュー非表示時にその 2/5 分が中央に流れ、Inbox が 1/5 のまま
  になって「Name 列の幅が全然違う」状態が発生していた。
- **決定**: stretch factor を全削除し、`MainWindow.resizeEvent` で `QTimer.singleShot(0, _apply_pane_layout)`
  → Qt のレイアウトパス後に `setSizes` を実行する方式に統一。`_CASE_LEFT_OFFSET=148`
  (= 3 outer margin + 2 border + 140 btn_container fixed + 2 spacing + 2 border + 3 outer margin - 4 Inbox 側 ロス) を反映。
- **必須前提**: `btn_container.setFixedWidth(140)` で固定幅化、両テーブルに
  `setVerticalScrollBarPolicy(ScrollBarAlwaysOn)` で viewport 幅を完全一致。
- **3 カラムモード時** も同公式で `inbox = (usable - offset)/4` を採用 → preview は 2*inbox 幅。
- **教訓** (反省): 当初「フォントレンダリング差」を疑って font metrics 計測まで
  走ったが、本当の原因は **splitter の stretch factor + Qt のレイアウトタイミング**
  だった。ユーザーが先に「splitter サイズ不揃いでは」と指摘していたが私が拾えなかった。
  「直接コストの低い仮説」から検証する順序を守ること。

### ADR-23: PDF プレビューは QBuffer 経由で in-memory 読込 (ファイルパス直 load しない) (2026-05-26)
- **経緯**: M5c 時点で `PreviewPane.clear()` → `QPdfDocument.close()` + `setDocument(None)`
  → 再付与 で Win のファイルロック対策を入れたが、Win 2 回目検証で F2 リネーム時に
  「別のプロセスが実行中です」エラーが残ることが判明。原因は **PDFium が Win 上で
  `close()` 後もファイルハンドル (Direct2D 経由含む) を保持し続けるケース**。
- **検討**: (a) `setDocument(None)` をより強く / processEvents で押し出す
  (b) bytes に読んでから `QBuffer` 経由で load する (c) リトライ + sleep。
- **決定**: **(b) QBuffer 経由 in-memory 読込**。`_show_pdf` で `Path.read_bytes()`
  → `QByteArray` → `QBuffer` (parent=self) → `pdf_doc.load(buffer)`。`read_bytes()`
  完了時点で Python 側のファイルハンドルは閉じ、Qt 側もハンドルではなくバッファを
  読むだけになる。`_release_pdf` ではバッファと QByteArray の Python 参照を None
  に落とすだけで完全解放できる。
- **理由**: Qt にファイルハンドル自体を持たせない方が、Win 上の挙動が原理的に
  予測可能になる (タイミング依存・OS バージョン依存のハンドル残留が起こらない)。
  メモリ使用量は PDF サイズ分増えるが、法律実務 PDF (~50MB 想定) では問題なし。
- **付随**: `preview_pane.py` に `self._pdf_data: QByteArray | None` /
  `self._pdf_buffer: QBuffer | None` を寿命管理用に追加。次回 `_show_pdf` 冒頭
  で `_release_pdf` を呼んで旧バッファ解放 → 新規読込みのフロー。

### ADR-24: テーブル refresh 時の選択は path で復元 (currentIndex 先 → select 後) (2026-05-26)
- **経緯**: Inbox の `QFileSystemWatcher` 経由 auto refresh、rename 後の
  `refresh_current_view()`、KB/MB 切替などで `_populate()` が呼ばれる。素朴に
  `setRowCount` + `setItem` で rebuild すると、同じ行 index が別ファイルを指す
  状態になり、ユーザーが「選択した A.pdf を移動する」つもりが B.pdf を動かして
  しまう事故が発生 (Win 2 回目検証で sk21 が遭遇)。
- **決定**: 両ペイン (Inbox / CasePane) の `_populate` 冒頭で
  `_collect_selected_paths()` → set[str] で選択中ファイルの絶対パスを保存。
  rebuild + sort 完了後に `_restore_selection_by_paths(prev_paths)` で同じ
  path を持つ行を探して再選択する。multi-select 対応。
- **詳細**: `_restore_selection_by_paths` は (i) まず
  `selectionModel.setCurrentIndex(.., NoUpdate)` で **currentIndex を先に
  動かす** → (ii) `QItemSelection` を組み立てて `select(.., ClearAndSelect|Rows)`
  で一括適用する。この順序で行うことで、`itemSelectionChanged` → `_on_table_selection`
  → `fileSelected.emit` が走るタイミングで `currentRow` がすでに新しい行を指して
  いる状態になり、プレビューが「選択行と一致したファイル」を表示する。
- **理由**: 順序を逆にすると、selectionChanged が古い currentRow で発火 → 別
  ファイルがプレビューに出る現象が発生 (Win 2 回目検証で一度遭遇、ADR-24 で
  順序を確定)。
- **キー埋込み**: Inbox は `setData(Qt.ItemDataRole.UserRole, str(path))` で
  Name セルに path を埋め込み、CasePane は `_NameItem.path` 属性を使う。
  ソート後でも一意に識別できる。

### ADR-25: cross-case Copy 動線は Ctrl+D&D + 右クリック明示の 2 系統 (2026-05-26)
- **経緯**: M5c までは事件 A → 事件 B にファイルをコピーする動線が存在せず、
  D&D も Move 一択だった。ユーザー要望: 「事件タブ内ファイルから別事件タブの
  別フォルダへファイルを移行 (コピー) できる動線が欲しい」。
- **検討案** (本ドキュメント 2026-05-26 セッション中で提示):
  - A. Ctrl+D&D = Copy (Win Explorer 標準、最少変更)
  - B. 右クリック →「他事件へコピー / 移動 → サブフォルダ明示」(発見性・精度)
  - C. ドラッグ中の他タブ hover で auto-activate → サブへ drop
  - D. 既存 D&D に「コピー/移動 + サブフォルダ選択」ダイアログを後置
- **決定**: **A + B 併設**。
  - **A (Ctrl+D&D)**: 既存の D&D = Move を維持しつつ、Ctrl 押下中の D&D を
    `e.proposedAction() == CopyAction` で判定して Copy に分岐 (Qt の startDrag
    で `MoveAction | CopyAction` を許可しているため自動的に効く)。落とし先は
    既存と同じ「同名サブフォルダ自動マッピング」で素早く実行。
  - **B (右クリックメニュー)**: 中央ファイル右クリック末尾に「他事件へコピー…」
    「他事件へ移動…」サブメニュー → 他事件タブ一覧 → サブフォルダ一覧 (含む
    「0 事件フォルダ直下」) → 明示指定して実行。落とし先サブフォルダを具体
    指定したい場合に使う。
- **共通実装**: MainWindow に `_do_cross_case_op(op, target_case_root,
  target_dir_resolver: Callable[[Path], Path], src_paths)` ヘルパを抽出。
  `op` ("copy"|"move") と `target_dir_resolver` を渡し分けることで、D&D 経路
  (`_automap_resolver` で同名マッピング closure) と明示経路 (`lambda _src:
  target_dir` で固定) を 1 つのループで賄う Strategy パターン。
- **付随**: `file_ops.copy` 新設 (`shutil.copy2` / `copytree`、衝突自動連番)、
  `undo_ops` に "copy" 対応 (Ctrl+Z で dst を OS ごみ箱へ送るのみ、src は手付かず)。
- **理由**: A は素早さ (ADR-7 と整合)、B は精度 (落とし先サブフォルダ具体指定)。
  両者は競合せず併設可能で、ユーザーの作業文脈に応じて使い分けられる。差分
  更新 (案 C/D) は実装複雑度に対して得るものが少ないと判断。

### ADR-26: ファイル名 絞込検索は常時アイコン + Ctrl+F で展開 + 空白区切り AND (2026-05-27)
- **経緯**: 事件フォルダ内に 100〜200 件の PDF が並ぶケースで、目的ファイルを
  名前で素早く絞り込みたいというユーザー要望。
- **検討案**:
  - A. 常時表示の QLineEdit (場所食い、Win95 風には合うが scan/file 行を圧迫)
  - B. Ctrl+F のみで表示する slide-down バー (発見性に欠ける)
  - C. **常時 🔍 アイコン + クリック or Ctrl+F で展開** (発見性・場所節約の両立)
- **決定**: C。中央ペイン breadcrumb 行の右端に虫眼鏡アイコン (`🔍`) を常時表示、
  クリック or Ctrl+F で同じ行に QLineEdit がインライン展開 (max-width 180px)。
  Esc で解除 + 折り畳み。`..` 行は常に表示。
- **照合方法**: **空白区切り AND の部分一致 (大小無視)**。`受領 田中` で
  「田中受領書.pdf」と「受領書(田中).pdf」両方ヒット。日本語の漢字検索は `.lower()`
  no-op で問題なく動く。`pdf` で拡張子フィルタも可 (= 拡張子も検索対象)。
- **件数表示**: フィルタ中だけ「N / M 件」を入力欄の右隣ラベルに出す。
- **クリア戦略**: サブフォルダ切替 / 事件タブ切替で**自動クリア** (混乱防止)。
  rename/inject/delete でリフレッシュされても**フィルタは継続** (= 作業中の絞込は維持)。
- **Inbox 側は実装しない**: 中央ペイン (事件サブフォルダ内) の方が「200 件並ぶ」
  シーンが多い。Inbox は元々 cutoff_days で日付絞り済で、検索の必要性が低い。

### ADR-27: 自動アップデート機構は案② (起動時通知 + 自動 DL + バッチ適用 + 再起動) (2026-05-27)
- **経緯**: HANDOVER §6 M6c で 4 案 (①通知のみ / ②自動 DL / ③差分更新 / ④WinGet)
  を比較。当初は **案① (~1 日実装、リスクほぼゼロ)** を推奨していたが、ユーザー
  反応「自分で DL + 古いの消すのがだるい」を受けて案②に格上げ。差分更新 (案③)
  は法律実務系で「アップデート途中で起動不能」リスクが許容できないため依然却下。
- **決定**: **案② 実装**。フロー:
  1. 起動 1.5 秒後に `QThread` で `find_newer_release()` (`urllib` で GitHub
     Releases API → ローカル VERSION と比較)
  2. 新版あれば status bar に `UpdateBanner` を表示
  3. 「更新...」 → `QMessageBox.question` → `QNetworkAccessManager` で zip DL
     (進捗ダイアログ、キャンセル可)
  4. DL 完了 → 再度 `QMessageBox.question` → updater バッチ生成 →
     `subprocess.Popen(..., DETACHED_PROCESS)` で detached 起動 → `self.close()`
  5. updater バッチ (`tasklist` で k-file.exe 消滅待ち → `ren` で旧フォルダを
     `.old` 化 → PowerShell `Expand-Archive` で zip 展開 → `start ""` で新版起動 →
     `rmdir /S /Q` で `.old` 削除)
- **実装の要 / 落とし穴**:
  - **install_dir 判定**: `getattr(sys, "frozen", False)` で PyInstaller 配布版を
    判定し、`Path(sys.executable).parent` を install_dir とする。dev 実行
    (`python -m src.main`) では None で適用ステップに進まない (DL 完了メッセージ
    のみ)。
  - **バッチエンコーディング**: cmd.exe は CP932/SJIS が安全。UTF-8 BOM 付では
    動かないことがある。`batch_path.write_text(..., encoding="cp932")` 必須。
  - **CRLF 改行**: cmd.exe バッチは CRLF。`"\r\n".join(...)` で生成。
  - **GitHub Releases asset の redirect**: `RedirectPolicyAttribute` を
    `NoLessSafeRedirectPolicy` に設定しないと S3 系の redirect で 302 のまま止まる。
  - **キャンセル時の handling**: `QNetworkReply.NetworkError.OperationCanceledError`
    だけは黙って return (エラー dialog を出さない)。
  - **`%APPDATA%` の取得**: `os.environ.get("APPDATA")`。Win 以外では
    `~/.config/k-file/updates/` にフォールバック (dev 実行用)。
- **API パス**: `/releases` (全 release リスト) を使う。`/releases/latest` だと
  prerelease がスキップされて β.X 同士の更新通知が出ないため。先頭 (= published_at
  降順) の zip asset 付き release を採用、ローカル VERSION と `is_newer` で比較。
- **バージョン比較 (`src/core/version.py`)**: SemVer ライク。`dev < alpha < beta <
  rc < stable`。"dev" は特例で alpha より下に位置 (`_pre_key` で `(-1, 0, "")`)。
  これで開発中ビルド (`VERSION = "0.1.0-dev"`) も β タグで「更新あり」検知が走る。
- **検証 hooks**: `tests/test_updater.py` で `urllib.request.urlopen` を
  `unittest.mock.patch` で差し替え、API 通信なしで全フロー (パース・選択・
  バージョン比較・バッチ生成) を unit test。Win 側 updater バッチの実動作確認は
  β.2 を切った時の自動アップデート初動が事実上の本番テスト。
- **理由**: 案① と比べて実装工数 +1 セッション程度で、ユーザー手間が劇的に減る
  (DL + 古いの削除 + 新版起動が 1 クリック化)。案③ の差分更新リスクを避けつつ、
  実用的な UX を確保。

### ADR-28: ADR-22 の defensive preview clear を ADR-23 後に撤回 (2026-05-27)
- **経緯**: ADR-22 (M5c、2026-05-25) で PDF プレビューのファイルロック対策として、
  `changeEvent` (ウインドウ非アクティブ)、F3 close、操作前 (rename/inject/delete)、
  ペイン focus 切替 など複数箇所で `preview_pane.clear()` を呼ぶ defensive
  クリアを入れた。ADR-23 (M5d、2026-05-26) で根本対策 (QBuffer 経由 in-memory
  読込み) を入れたことで、表示中もファイルロックが発生しない構造になった。
  しかし defensive clear はそのまま残っており、**ユーザーがウインドウ外を
  クリックする度にプレビューが消える** という UX の劣化が顕在化。
- **判断材料**:
  - ADR-23 で `read_bytes()` 完了時に OS ファイルハンドルは閉じている (PDFium も
    QBuffer 経由なのでファイルを掴まない)
  - 画像 `QPixmap(str(p))` は load 完了時に handle close
  - text/JSON は Python `read_text` で同上
  - → preview 表示中もファイルは常時 free
- **決定**: 以下 2 箇所の `preview_pane.clear()` を撤去:
  - `MainWindow.changeEvent` の `ActivationChange` (= 非アクティブ化) 時
  - `MainWindow._toggle_preview` の閉じる側 (= F3 で隠す時)
  - 連動で `_internal_modal_count` (rename modal 中の clear スキップ用カウンタ)
    も用途消失で削除。
- **残す clear()**: rename/inject/delete/cross-case/<<デスクトップ などの**操作直前**
  は引き続き呼ぶ。これは「ファイルロック解放」目的ではなく「操作後の preview を
  新しいパスに切り替える前のリセット」目的。ペイン Tab 切替時の
  `_focus_inbox_table` / `_focus_case_table` も意図的に維持 (= 操作 pane が変わったら
  preview もリセット)。
- **理由**: ADR-23 を信頼することで、業務操作の最中にプレビューが「ちらつかず・
  消えず」見え続ける状態にする (ユーザーが別アプリを参照しながら k-file の
  プレビューを横目で見るような workflow に必要)。
- **リスク**: 理論上は ADR-23 が file lock 解放を完全に担保しているはずだが、
  万一 PDFium の lazy load などで未知の handle 残留があれば、ウインドウ外
  クリック中に Explorer から rename/delete を試みると失敗する。Win β 検証で
  実機確認。再発したら片方だけ clear() を戻す段階的フォールバック可能。

### ADR-29: プレビュー読込はメインスレッドでなく QThreadPool worker で行う (2026-05-29)
- **経緯**: β.1 業務並走で「ファイルをクリックすると / 移動・リネーム直後に
  アプリが固まり強制終了せざるを得ない」フリーズが頻発と報告。症状は「見た目は
  普通だが無反応」= メインスレッドが同期 I/O でブロックされる典型 (`error.log` に
  crash 痕跡なし、`SystemExit:0` のみ = 純粋なハング)。
- **環境前提 (原因の鍵)**: 事件フォルダは **Dropbox をレジストリで X ドライブに
  マウント**して X: 経由でアクセスしている (Inbox は全てローカル)。Dropbox の
  「オンラインのみ (placeholder)」ファイルは、**`stat` (サイズ/更新日) では中身を
  DL せず比較的速い**が、**`read` (実体読込) した瞬間に hydrate が走り数十秒〜
  長時間ブロック**する。「事件 (X:) 側操作でだけ固まり、Inbox は無傷」という
  観測された非対称はこれで説明できる。
- **主因の特定**: `preview_pane` が PDF (`read_bytes`)、画像 (`QPixmap(str(p))`)、
  テキスト/JSON (`read_text`) の **読込 + デコードをメインスレッドで同期実行**して
  いた。プレビューは「ファイルをクリックする度」に発火 = 最高頻度の X: read。
  移動・リネーム直後の固まりも、`refresh_current_view` → 選択復元 → `fileSelected`
  → preview が対象を同期 read、が引き金。
- **決定 (Phase 1)**: preview の読込を `QThreadPool` + `QRunnable` worker に逃がす。
  - `_load_preview(path, seq)` = worker 側純 I/O 関数。stat / read_bytes /
    `QImage` デコードを全てバックグラウンドで実行 (`QImage` は GUI 非依存なので
    worker 可。`QPixmap` は main 専用なので結果を main で `QPixmap.fromImage`)。
  - `show_file` は seq を採番して worker を起動するだけ。結果は `_on_loaded` で
    受け、**seq が最新の時だけ描画** (クリック連打で古い読込が後から上書きするのを
    破棄)。
  - 旧 `_show_pdf/_show_image/_show_text/_show_json` → `_render_pdf/_render_image/
    _render_text` に再編 (worker 結果から GUI 構築するだけ、I/O なし)。ADR-23
    (QBuffer 経由 PDF) は維持。`_update_info` は worker が stat 済みの size/mtime を
    受け取り main で再 stat しない。
  - 読込が **150ms を超えた時だけ「読込中...」表示** (QTimer)。ローカル即時読込では
    出ないのでチラつかない。**確認ダイアログは追加しない** (規約遵守、モーダルに
    しない)。
- **理由**: 業務凍結級バグであり機能追加より優先 (CLAUDE.md)。メインスレッドから
  X: の重い read を完全に除けば、Dropbox が固まってもアプリは応答し続ける。
- **残作業 (Phase 2/3)**: 事件フォルダ走査 (`scan_case_folder`/`list_folder`) は
  まだメインスレッド同期。stat 主体で placeholder でも比較的速いため Phase 1 より
  優先度は下がるが、移動・リネーム後の固まりが実機で残るなら非同期化する (§8 参照)。
  IPC 同期待ちと main.py の SystemExit 誤ログは Phase 3 の掃除候補。
- **テスト**: `tests/test_preview.py` 10 件 (worker `_load_preview` の種別判定 /
  読込 / cp932 フォールバック / 切詰め / 破損画像エラー)。全 112 件 green。
- **リスク**: worker と main のスレッド分離で Qt オブジェクト所有権の境界を誤ると
  クラッシュしうる (QImage=worker / QPixmap・QPdfDocument=main を厳守)。連打時の
  seq 破棄が正しく効くかは実機のクリック連打で確認。

---

## 16. ライセンス

PySide6 は LGPL。商用配布で問題ないが、Qt 自体を改変・静的リンクする場合は注意。
本アプリの配布形態 (PyInstaller --onefile) は動的リンク相当として LGPL 上問題なし。
