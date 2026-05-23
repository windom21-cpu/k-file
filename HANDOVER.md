# k-file 引き継ぎドキュメント

このファイルは AI セッション間でプロジェクトの現状を引き継ぐための master document。
**ユーザー明示依頼時のみ更新する。マイルストーン完了の都度自動更新しない。**

---

## 現状サマリ
- 現在地: **M2 補強 (UI 詰め 2) 完了 (2026-05-23)。次は M3 投入 + cross-case 移動**
- スタック: Python + PySide6、PyInstaller で .exe 配布
- UI 方針: Windows95/98 風 (MS UI Gothic / 灰色 / beveled / 高密度業務アプリ感)
- リポジトリ: https://github.com/windom21-cpu/k-file (public)
- 配布: GitHub Releases (単一リポへ直 upload)

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
- **M3 投入 + cross-case 移動**: Alt+0〜9 投入 (Copy → 検証 → 元削除)、**F2 = rename ダイアログ (Windows 標準)** + 最近使った名前、衝突自動連番、cross-case D&D Move、ステータスバー反映
- **M4 Undo + 削除 + 履歴**: Ctrl+Z Undo (最低 10 段)、Del で OS ごみ箱 + 履歴記録、F12 投入履歴ビュー (サムネ付)、各行から個別 Undo
- **M5 K-SystemZ 連携**: 「事件を開く」ダイアログ (Ctrl+O) で ksystemz.db RO 検索、複数事件タブ同時開き、セッション復元、フォルダ D&D で事件タブ追加 → β タグ開始
- **M6 配布**: コマンドライン引数 `k-file.exe "path"` 対応、Explorer 右クリック「k-file で開く」シェル拡張、任意フォルダをタブで開く汎用ファイラー化 (事件フォルダ以外も可)、PyInstaller .exe + GitHub Actions ビルド、Win 機で業務並走 → v1.0 stable
  - ※フォルダ既定ハンドラの OS 乗っ取りは行わない (§15 ADR-2)。literal な「Explorer ダブルクリック→k-file」は、やるとしても Win 実機実験 → 上級者向け自己責任トグル止まり

### 確定したショートカット体系 / サブフォルダ操作 (原仕様の F1〜F6 から変更済)
- **サブフォルダボタン 左クリック**: そのサブフォルダの中身を表示 (閲覧のみ・ファイルは動かさない)
- **Alt+0〜9**: 選択中の Inbox ファイルを投入 (0=事件フォルダ直下 / 1〜9=サブフォルダ先頭 9 個)。Inbox 未選択時は閲覧のみ
- **サブフォルダボタン 右クリック**: 投入メニュー (D&D 以外のマウス投入手段)
- **F2**: ファイル/フォルダ名変更 (Windows 標準) — M3 実装予定
- **Shift+F2**: 事件フォルダ自体の rename ダイアログ (滅多に使わない用途、case_code 変更時は警告)
- **F3**: プレビュー開閉トグル (1:1 二カラム ↔ 1:2:2 三カラム、初期は二カラム)
- **F5**: Inbox 更新 (Windows 標準)
- **F12**: 投入履歴ビュー — M4 実装予定
- **Ctrl+O**: 事件を開くダイアログ — M5 実装予定
- **Ctrl+Z**: Undo — M4 実装予定
- **Ctrl+Q**: 終了
- 下部ファンクションキーバー (DOS ファイラー風) に F1〜F12 を全 12 枠表示、未実装は薄色グレー

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

---

## 8. 次にやること

### M2 完了 (2026-05-22) → M3 へ

M2 で実ファイル接続・プレビューまで完了。アプリは実フォルダ/実ファイルを
読み・表示・プレビューできる (まだ読み取り専用、ファイルは動かさない)。

### M2 dev の足場 (M5 で正式化する仮実装)
- 事件フォルダ: `~/k-file-test-data/事件/` を `case_pane.py` の `_DEV_DOC_ROOT`
  で直読み → M5 で ksystemz.db +「事件を開く」ダイアログに置換
- Inbox 監視対象: `~/k-file-test-data/inbox-{scan,desktop,work}` を
  `inbox_pane.py` の `_DEV_INBOX_SOURCES` で直指定 → 設定ダイアログ +
  kfile.db settings に置換
- テストデータは `~/k-file-test-data/` に合成 (ネスト 3 階層・欠番サブ
  フォルダ・実 PDF/画像入り)。リポジトリには含めない

### M3 で実装する範囲
- `core/file_ops.py` — Inbox→サブフォルダ投入 (Copy→検証→元削除)、
  cross-case Move、衝突自動連番、send2trash 削除
- Alt+0〜9 / 右クリック / D&D の投入を実処理に接続 (現状はダミーメッセージ)
- F2 = rename ダイアログ + recent_names (kfile.db) 候補表示
- drop_history (kfile.db) への記録
- 更新日時フィルタ + 設定ダイアログ (ツール→設定) もこの辺りで

### 着手前メモ
- Win .exe ビルドで QtPdf モジュール/プラグインの同梱を確認 (`k-file.spec` / CI)
- `core/` のユニットテスト未整備 (folder_scanner 等は Qt 非依存でテスト可能)

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
- **将来拡張**: 削除・Inbox 更新・選択ファイル情報など、頻度高い操作はここに追加していく。strip 自体は QSS で「自前枠」を持ち、隣接ペインの sunken 縁と組み合わせて視覚的に区切る (ADR-5 と連動)。

---

## 16. ライセンス

PySide6 は LGPL。商用配布で問題ないが、Qt 自体を改変・静的リンクする場合は注意。
本アプリの配布形態 (PyInstaller --onefile) は動的リンク相当として LGPL 上問題なし。
