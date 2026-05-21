# k-file 引き継ぎドキュメント

このファイルは AI セッション間でプロジェクトの現状を引き継ぐための master document。
**ユーザー明示依頼時のみ更新する。マイルストーン完了の都度自動更新しない。**

---

## 現状サマリ
- 現在地: **構想 / 初期セットアップ段階**
- スタック: Python + PySide6、PyInstaller で .exe 配布
- UI 方針: Windows95/98 風 (MS UI Gothic / 灰色 / beveled / 高密度業務アプリ感)
- リポジトリ: 未作成 (GitHub windom21-cpu/k-file を予定)
- 配布: GitHub Releases (k-pdf3 と同じ二重リポ案も検討余地)

---

## 0. このドキュメントの読み方

最低限読む順:
1. このページ冒頭 (現状サマリ)
2. §1 プロジェクトの全体像
3. §2 設計思想と禁止事項
4. §3 協働方針 → `docs/COLLABORATION.md` も
5. §6 開発ロードマップ / マイルストーン
6. §8 次にやること

---

## 1. プロジェクトの全体像

### 何を作るか
**案件ドキュメント作業台** — 法律実務に特化した **2/3 ペイン型ファイラー**。
未整理 PDF・画像・FAX 結果・スキャン文書 (Inbox 側) と複数の事件フォルダ (出ていく側) を横並びで一体表示し、Inbox から事件サブフォルダへの投入を最速で行う。同時に各事件フォルダタブは小型ファイラーとして機能し、ファイルの閲覧・既定アプリで開く・名前変更・削除・事件をまたぐ移動など **通常のファイル操作も完備** する。

「紙の机・事件棚・未処理トレー」をデジタル上で再構築する。Explorer の代替を目指すわけではないが、**案件文脈の中では Explorer を開かなくても済む** 状態を維持する。

### 想定運用
- 日常的に scan / Desktop / 作業フォルダに集積される未整理ファイルを、**統合 Inbox** で一覧
- 進行中の事件 (5〜15 件程度) を **タブで同時に開いておく** — 各事件フォルダは小型ファイラー
- Inbox から事件のサブフォルダ (`1_文書 / 2_発信 / 3_受信 / 4_資料 / 5_申立書類 / 6_訟務資料`) へ **F1〜F6 または D&D で投入** (rename ダイアログ → Enter 確定)
- 事件をまたぐ移動・事件内での整理・既定アプリで開く等もこのツール内で完結

事件フォルダ自体は既存事件管理システム **K-SystemZ** が管理しており、本ツールはこれを **読み取り専用で参照** する (詳細 §4)。本ツールは事件管理そのものは行わない。

### 何を作らないか
- 汎用ファイラー (任意フォルダの閲覧は対象外、事件フォルダおよび Inbox 監視対象のみ)
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
- **6 分類は基本スキーマ**。事件フォルダ内のサブフォルダを **実フォルダから動的読み取り** し、`\d_.*` パターンの先頭 6 個を F1〜F6 に**順に繰り上げ割当** (欠番があれば次のものが上がる)。7 個目以降は F なしの追加タブとして表示。
- **事件フォルダの中身はサブフォルダタブ + フラット一覧** で表示 (ツリー禁止、200 ファイル/事件規模で見にくいため)。サブフォルダタブには件数バッジを付ける。
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
- ツリービューでの事件フォルダ表示 (常に「サブフォルダタブ + フラット一覧」)
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
├─ メニューバー (ファイル / 編集 / 表示 / ヘルプ) ─────────────────────────┤
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
| Inbox → サブフォルダ投入 | Inbox で選択 → F1〜F6 (rename ダイアログ → Enter 確定 / Esc で元名のまま投入) |
| Inbox → 任意サブフォルダ | D&D、または Inbox で選択 → サブフォルダ行で Enter |
| 既定アプリで開く | ファイルでダブルクリック / Enter |
| 名前変更 | F2 |
| 削除 | Del (確認なし、OS ごみ箱 + 自前履歴) |
| 別事件タブへ移動 | D&D = Move (Dropbox 30 日履歴 + 自前 Undo が保険) |
| Undo | Ctrl+Z |
| 投入履歴 (サムネ付) | F12 |
| 事件を開く (ダイアログ) | Ctrl+O |
| フォルダ D&D で事件タブ追加 | k-file ウインドウへフォルダを D&D |

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
- `core/folder_scanner.py` — 事件フォルダ内のサブフォルダ動的取得 + `\d_.*` パターンの先頭 6 個を F1〜F6 に繰り上げ割当
- `infra/kfile_db.py` — k-file 専用 SQLite (kfile.db) ラッパー
- `ui/title_bar.py` — Win95 風自作タイトルバー (Frameless + 自前)
- `ui/main_window.py` — メインウインドウ全体組立
- `ui/inbox_pane.py` — 左 Inbox ペイン (出所フィルタ + 統合一覧)
- `ui/case_pane.py` — 中央事件フォルダペイン (サブフォルダタブ + フラット一覧)
- `ui/preview_pane.py` — 右プレビューペイン
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

- **M1 スケルトン**: PySide6 起動 + Win95 QSS + **自作タイトルバー** + 事件タブ (アクティブ強調) + **3 ペイン (Inbox / 事件フォルダ / プレビュー)** + サブフォルダタブ + フラット一覧 + ステータスバー (全てダミーデータ)
- **M2 実ファイル接続 + プレビュー**: Inbox 監視対象フォルダの実ファイル一覧 (QFileSystemWatcher)、事件フォルダの実ファイル読込 (QFileSystemModel)、PDF/画像プレビュー (QPdfView / QPixmap)、PDF + 画像フィルタ、無視機能、サブフォルダ動的読込 (繰り上げ割当)
- **M3 投入 + cross-case 移動**: F1〜F6 投入 (Copy → 検証 → 元削除)、rename ダイアログ + 最近使った名前、衝突自動連番、cross-case D&D Move、ステータスバー反映
- **M4 Undo + 削除 + 履歴**: Ctrl+Z Undo (最低 10 段)、F2 名前変更、Del で OS ごみ箱 + 履歴記録、F12 投入履歴ビュー (サムネ付)、各行から個別 Undo
- **M5 K-SystemZ 連携**: 「事件を開く」ダイアログ (Ctrl+O) で ksystemz.db RO 検索、複数事件タブ同時開き、セッション復元、フォルダ D&D で事件タブ追加 → β タグ開始
- **M6 配布**: コマンドライン引数 `k-file.exe "path"` 対応、Explorer 右クリック「k-file で開く」シェル拡張、PyInstaller .exe + GitHub Actions ビルド、Win 機で業務並走 → v1.0 stable

---

## 7. 実装済み機能カタログ

(TBD: 完成機能をここに積み増す)

---

## 8. 次にやること

### M1 スケルトン (再構築フェーズ — 2026-05-22 設計変更後)
当初の M1 (投入先巨大表示・3 ペイン Inbox/プレビュー/6 ボタン) は破棄。新設計に組み直し:

1. `resources/style/win95.qss` 拡張 — 自作タイトルバー・事件タブ・サブフォルダタブ用スタイル追加
2. `src/ui/title_bar.py` — Win95 風自作タイトルバー (Frameless + min/max/close + startSystemMove ドラッグ)
3. `src/ui/inbox_pane.py` — 左 Inbox ペイン: 出所フィルタタブ + 統合一覧 (ダミー)
4. `src/ui/case_pane.py` — 中央事件ペイン: パス + サブフォルダタブ (件数バッジ) + フラット一覧 (ダミー)
5. `src/ui/preview_pane.py` — 右プレビューペイン (M2 まではプレースホルダ)
6. `src/ui/main_window.py` 全面書き換え — FramelessWindowHint + タイトルバー + メニュー + 事件タブ + 3 ペイン + ステータスバー
7. Linux 本機で起動確認 (Wayland での frameless + startSystemMove 動作確認)

### M1 完了後
- GitHub リポ作成 (windom21-cpu/k-file)
- PyInstaller spec 起草 + GitHub Actions ワークフロー初稿 (`docs/CI-CD.md`)
- M2 着手 (実ファイル接続 + プレビュー)

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

```bash
# Linux 本機
python3.11 -m venv .venv
source .venv/bin/activate
pip install pyside6 pyinstaller
python -m src.main
```

Win 機側は (TBD: Win 用セットアップ手順を確立次第)。

---

## 12. リポジトリ・配布インフラ

(TBD: k-pdf3 のような二重リポ (release 専用) を採用するか、単一リポで Releases に直接 upload するか決定)

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

(TBD)

---

## 16. ライセンス

PySide6 は LGPL。商用配布で問題ないが、Qt 自体を改変・静的リンクする場合は注意。
本アプリの配布形態 (PyInstaller --onefile) は動的リンク相当として LGPL 上問題なし。
