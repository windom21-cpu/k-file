# k-file 引き継ぎ書 (K-SystemZ 側 開発 AI 向け)

最終更新: 2026-05-24 / k-file v0.1.x (M5 完了 + M6a CLI 引数対応、β タグ前)

---

## 0. このドキュメントについて

### 想定読者
あなた = **K-SystemZ の開発を担当する AI**。

K-SystemZ はユーザー (sk21.lawyer@gmail.com、法律実務家) が Win 機ローカルで
開発している事件管理システム (FastAPI + React + SQLite)。あなたはそこで
動いている開発 AI として、ユーザーが進めている **k-file 連携** に必要な
K-SystemZ 側の改修を担当する。

### このドキュメントの目的
ユーザーは k-file (Python + PySide6 製の Win .exe 案件ドキュメント作業台、
ユーザーが本機 Linux 側で開発中) を K-SystemZ から起動できるよう、
**設定にトグルを置いて「フォルダを開く」挙動を Explorer ↔ k-file で切替** したい。

その上で **しばらく k-file を実運用 → フィードバック収集** という流れ。

そのため、

- **k-file とは何か** (あなたは初見と仮定)
- **K-SystemZ との関係** (現状とユーザーの移行計画)
- **K-SystemZ 側で実装してほしいこと** (具体的にどう書くか)
- **k-file 側の現状の制約** (CLI 引数未対応 等)
- **GitHub に関する事柄** (K-SystemZ は GitHub を使わない前提)

を全部この 1 ドキュメントで自己完結させた。**この 1 ファイルだけで作業を進められる**
ことを目標にしている。

### 前提制約
- あなたは k-file 本体ソースには **直接アクセスできない** (GitHub 経由が必要だが、
  K-SystemZ プロジェクトは Git/GitHub を使わない)
- あなたが行う変更は **K-SystemZ 側のみ**
- k-file 側に必要な変更があれば、**ユーザー経由で本機 (Linux) 側の k-file AI に伝言** する

---

## 1. k-file とは何か

### 概要
- **ユーザー自作の法律実務向け 2/3 ペイン型ファイラー** (案件ドキュメント作業台)
- Python 3.12 + PySide6 (LGPL) で実装、PyInstaller --onefile で **Windows .exe** 配布
- UI: **Windows 95/98 風業務アプリ** (MS UI Gothic / 灰色 #C0C0C0 / beveled / 高密度)
- ローカル完結: 独自ファイル形式なし、すべて実ファイルに対する Copy/Move/削除
- 完全に **ユーザー個人 + AI 協働開発** のクローズドプロジェクト (姉妹アプリ k-pdf3 と同じ流れ)

### 設計思想 (キーワード)
- **「紙の机・事件棚・未処理トレー」のデジタル再構築** — Explorer を置き換えはしない、
  だが「案件文脈の中では Explorer を開かなくて済む」状態を作る
- **アクティブな事件タブ = 閲覧 + 投入先** (一体化) — 投入先を別に持たない設計で
  操作最速 (タブ切替 = 投入先切替)
- **確認ダイアログ追加禁止** — 誤投入は「可視化 + 回復」(タブ強調表示 + 投入履歴 +
  Ctrl+Z) で担保
- **削除は OS ごみ箱 + 自前履歴ハイブリッド** — Del キーで OS ごみ箱に送り、
  drop_history に経路を記録、復元は Win Recycle Bin 右クリック「元に戻す」
- **6 分類スキーマ** (`1_文書 / 2_発信 / 3_受信 / 4_資料 / 5_申立書類 /
  6_訟務資料`) は事務所標準、Alt+1〜6 で投入

### 主要 UI
```
┌─ 自作タイトルバー (Win95 風: 紺地白文字) ────────────────────────────┐
├─ メニュー (ファイル / 編集 / 表示 / ツール / ヘルプ) ─────────────────┤
├─ 事件タブ: [山田]  [㈱A商事]  [鈴木花子]  +  [全事件…] ────────────┤
├──────────┬───────────────────────────────────┬───────────────┤
│          │ R060200042 山田太郎 損害賠償       │                │
│  Inbox   │ ─────────────────────────────     │                │
│          │ [1_文書][2_発信][▶3_受信(5)◀]     │   プレビュー    │
│ 全/scan  │ [4_資料][5_申立][6_訟務(12)]      │   (PDF / 画像) │
│ /Desk/作業│                                   │                │
│ ──────── │ ──────────────────────────        │                │
│ • a.pdf  │ Name     更新     サイズ          │                │
│ • b.pdf  │ • 受領書  5-20   2.3MB ← 選択中   │                │
│ • c.pdf  │ • 連絡書  5-19   1.1MB            │                │
├──────────┴───────────────────────────────────┴───────────────┤
│ ステータスバー / F キーバー (F1..F12)                          │
└──────────────────────────────────────────────────────────────┘
```

- 左 = **Inbox** (scan / Desktop / 作業 など監視対象フォルダの未整理ファイル一覧)
- 中央 = **事件タブ + サブフォルダボタン + ファイル一覧** (案件ごとの作業空間)
- 中央左の細い縦バー = **コマンドストリップ** (`>1`〜`>0` 動的ボタン、`<<`、`✕`、`↶`)
- 右 = **プレビュー** (PDF/画像)
- 下 = **ステータスバー + F キーバー** (DOS ファイラー風)

### 主要操作 (キー / マウス両対応)
| 操作 | 方法 |
|---|---|
| Inbox → サブフォルダ投入 | `Alt+0〜9` / 右クリック / ストリップ `>N` / D&D |
| 投入時の rename | **なし** (即時実行、リネームしたければ F2 で別途) |
| 名前変更 | `F2` (Inbox / 中央 どちらでも) |
| 削除 | `Del` / `F8` → OS ごみ箱 |
| Undo (inject/move/rename) | `Ctrl+Z` (trash は Recycle Bin 右クリックで戻す) |
| 投入履歴 | `F12` (各行から個別 Undo) |
| 事件を開く | `Ctrl+O` (ksystemz.db を検索) |
| プレビュー開閉 | `F3` (2 カラム ↔ 3 カラム) |
| Inbox 更新 | `F5` |
| クロス事件 Move | 中央ファイル行を別事件タブへ D&D |
| 事件 → Desktop へ戻し | ストリップ `<<` (一時保留に出す) |
| 他事件にショートカット | パス行「他事件へ」ボタン (AB 集約用) |

---

## 2. k-file と K-SystemZ の関係 (現状の確定事項)

### 2.1 データフロー
```
   ┌────────────────────┐  RO (mode=ro)   ┌──────────────────┐
   │  K-SystemZ           │ ───────────→ │  k-file           │
   │   ksystemz.db        │                │  (Win .exe)      │
   │   (Dropbox 同期下)   │                │                  │
   └────────────────────┘                └──────────────────┘
            │
            └─ k-file は **書き込まない** (Dropbox 同期で他機と競合するため絶対禁止)

   ┌────────────────────┐
   │  k-file 専用 DB     │
   │  %APPDATA%\k-file\  │ ← k-file 自身の状態 (投入履歴・無視・open_tabs・設定)
   │  kfile.db            │   **ローカル限定** (Dropbox 同期下に置かない)
   └────────────────────┘
```

### 2.2 k-file が ksystemz.db から読むテーブル

#### `office_info` (id=1 固定)
```sql
SELECT doc_root_path, doc_root_path_mac FROM office_info WHERE id = 1;
```
- `doc_root_path`: Win 用文書ルート (例: `X:\事件\`)
- `doc_root_path_mac`: Mac 用 (Linux dev では Mac 値を流用)

#### `cases` (主要列)
- `id`, `case_code`, `case_name`, `case_type`, `status`, `folder_path`, `is_deleted`
- k-file は `case_code` / `case_name` / `case_type` / `status` を表示・検索に使う
- `folder_path` は **使わない** (K-SystemZ open-folder API と同じく `doc_root_path` 配下の
  prefix 検索で解決するため)

#### `case_persons` + `persons`
```sql
SELECT
    c.case_code, c.case_name, c.case_type, c.status,
    COALESCE(
        CASE WHEN p.corp_name != '' THEN p.corp_name
             ELSE COALESCE(p.last_name, '') || COALESCE(p.first_name, '') END,
        ''
    ) AS client_display
FROM cases c
LEFT JOIN case_persons cp
    ON cp.case_id = c.id AND cp.role = '依頼者' AND cp.role_order = 1
LEFT JOIN persons p
    ON p.id = cp.person_id AND p.is_deleted = 0
WHERE c.is_deleted = 0
  AND c.status NOT IN ('不受任', '諸件', '終了')   -- active_only=True 時
  AND c.case_type != '顧問'                       -- active_only=True 時
ORDER BY c.case_code DESC;
```
- 主たる依頼者 = `case_persons.role='依頼者' AND role_order=1` (K-SystemZ と同じ)
- 検索: `case_code` / `case_name` / `last_name` / `first_name` / `corp_name` で LIKE

### 2.3 case_code → 実フォルダ解決
- K-SystemZ の `GET /api/cases/{id}/open-folder` と **完全に同じロジック**
- `doc_root_path` 直下を `{case_code}*` で前方一致検索 (例: `R060200042` → `R060200042 山田太郎 損害賠償`)
- ヒットしなければ未解決 (k-file 側でステータスバーに通知)

### 2.4 **K-SystemZ 側の改修は (現状) 不要**
- k-file は K-SystemZ の API を呼ばない (DB を直接読む)
- 既存の `cases` / `case_persons` / `persons` / `office_info` テーブル定義に変更不要
- ユーザーが Win 機で K-SystemZ を起動・編集している間も k-file は RO 参照だけ
  なので競合しない

---

## 3. ユーザーの移行計画 (今回あなたに作業を依頼している背景)

### 3.1 ゴール
K-SystemZ の「フォルダを開く」操作の出口を **Explorer ↔ k-file で切替** できるようにし、
**k-file 側に切り替えて日常業務で運用 → フィードバック収集** → k-file 側で改善
→ 安定したら標準動線として定着、というフェーズに入りたい。

### 3.2 切替トグルを置く理由
- いきなり k-file 専用にすると、k-file がバグった時に業務が止まる
- いつでも Explorer に戻れる安全弁を設定 UI に置く
- 個人運用 → 事務所全体への段階展開を想定

### 3.3 既存の伏線
K-SystemZ 引き継ぎ書 v22 にあるとおり、`office_info` テーブルには既に
**`folder_open_mode TEXT DEFAULT 'explorer'`** カラムが追加されている (v22 追加、
互換用、現在未使用)。これは **今回の k-file 切替トグルを見越して** 用意されたもの
なので、今回の実装で活用してほしい。

---

## 4. K-SystemZ 側で実装してほしいこと

### 4.1 DB スキーマ拡張 (`office_info` に 1 列追加)
```sql
ALTER TABLE office_info ADD COLUMN kfile_exe_path TEXT DEFAULT '';
```
- k-file.exe の置き場所をユーザーが指定するため
- 既定空 → `shutil.which("k-file")` で PATH から検索フォールバック (4.3 参照)
- `init_db.py` または migration スクリプトに追記 (既存 v22 のパターンに倣う)

### 4.2 設定 UI: 「フォルダ挙動」セクション
- 既存設定ページ (`/settings`) に追加
- レイアウト案 (タイル UI 方針に合わせる):
```
┌─ フォルダ挙動 ─────────────────────────────────────────────┐
│  「フォルダを開く」をどのアプリで処理するか:                 │
│    ◉ Explorer (従来)                                        │
│    ○ k-file (案件ドキュメント作業台)                        │
│                                                              │
│  k-file.exe の場所 (k-file モード時のみ):                  │
│    [                              ] [参照...]              │
│    ※ 空欄なら PATH から自動検索                            │
│                                                              │
│  ℹ️ k-file は Inbox 仕分け・複数事件タブ・投入履歴 Undo・   │
│     クロス事件 Move などが使えます。Explorer に戻すには    │
│     上のトグルを切替てください。                           │
└────────────────────────────────────────────────────────────┘
```
- 値: `folder_open_mode` カラムに `'explorer'` または `'kfile'` を保存
- バリデーション: `'kfile'` 選択時 + パス空欄 + PATH に k-file なし → 警告表示
  (保存はさせるが「k-file が見つからないので Explorer にフォールバックします」と注記)
- 既定: `'explorer'` (既存ユーザー影響ゼロ)

### 4.3 バックエンド: open-folder API の routing 改修
`backend/cases.py` の `GET /api/cases/{case_id}/open-folder` を拡張:

```python
import os
import subprocess
import sys
import shutil
from pathlib import Path
from fastapi import HTTPException

@router.get("/api/cases/{case_id}/open-folder")
def open_folder(case_id: int):
    # ── 既存ロジック: doc_root + case_code で実フォルダを引く ──
    folder = resolve_case_folder_by_prefix(case_id)
    if folder is None or not folder.is_dir():
        raise HTTPException(404, "事件フォルダが見つかりません")

    office = get_office_info()
    mode = (office.folder_open_mode or "explorer").lower()

    if mode == "kfile":
        # k-file.exe のパスを解決
        kfile_exe = office.kfile_exe_path or ""
        if not kfile_exe:
            kfile_exe = shutil.which("k-file") or ""

        if kfile_exe and Path(kfile_exe).is_file():
            try:
                # k-file は M6a 以降 CLI 引数対応: 渡した folder を事件タブとして
                # 即時オープン (フォーカスは last argument)。
                subprocess.Popen(
                    [kfile_exe, str(folder)],
                    shell=False,
                )
                return {"opened_with": "kfile", "path": str(folder)}
            except OSError as e:
                # k-file 起動失敗 → Explorer フォールバック (業務止めない)
                # ログには残す
                print(f"[open_folder] k-file 起動失敗: {e}, Explorer にフォールバック")

    # mode == "explorer" or k-file 起動失敗
    if sys.platform == "win32":
        os.startfile(str(folder))
    else:
        # Mac (開発機) — 既存 K-SystemZ ロジックに合わせる
        subprocess.Popen(["open", str(folder)])
    return {"opened_with": "explorer", "path": str(folder)}
```

### 4.4 フロントエンド: 設定ページのコンポーネント
- `frontend/src/pages/Settings.jsx` 等の office_info 編集セクションに追加
- 既存タイル UI / 別ページ遷移方式 に揃える (ユーザーはドロップダウンを嫌う)
- 「保存」ボタン押下で API `PUT /api/office-info` 等に送信

### 4.5 大切なエラーハンドリング
1. **k-file が見つからない (パス未指定 + PATH にもなし)**:
   → 即 Explorer フォールバック + ログ "k-file パス未解決、Explorer で開きます"
2. **k-file の subprocess.Popen が失敗 (Permission denied 等)**:
   → 即 Explorer フォールバック + ログ
3. **設定 UI の保存時**:
   → `'kfile'` 選択 + パス検証失敗の場合は警告表示するが保存は許可
     (ユーザーが k-file を後でインストールするケースを許容)

**業務を止めないことが最優先**。k-file 連携は便利機能、Explorer はライフライン。

---

## 5. k-file 側の現状の制約 (実装時に必ず知っておくべきこと)

### 5.1 コマンドライン引数: **対応済** (M6a / 2026-05-24)

- `k-file.exe "C:\path\to\folder"` で **そのフォルダを事件タブとして即時オープン**
- 複数引数 OK: `k-file.exe "<folder1>" "<folder2>" ...` で順次タブ追加、最後の引数がアクティブ
- セッション復元 (前回 `open_tabs`) **の後** に CLI 引数を追加するので、前回タブ +
  新しく開いたタブが両方並ぶ
- 既に開いている事件と同じパスが CLI から来た場合 → 重複タブを作らず既存タブにフォーカス
- ファイル/存在しないパス/空文字列の引数は黙って無視 (落ちない)
- **非事件フォルダ (任意のディレクトリ) も開ける** — 6 分類サブフォルダがなくても、
  発見されたサブフォルダがそのままボタン列に出る (汎用ファイラー化、ADR-15)

#### K-SystemZ から呼ぶときの典型
```python
import subprocess
# 事件 A のフォルダ (案件ドキュメントの実体パス) を渡す
subprocess.Popen(
    [kfile_exe_path, str(case_folder)],
    shell=False,
)
```
- ボタン押下 → k-file 起動 → 事件 A タブが自動で前面に出る (二度手間なし)
- k-file が既に動いていれば? → 5.2 参照

### 5.2 単一インスタンス保証: **未対応** (M6b で予定)

- k-file は同時に複数インスタンス起動可能 (排他ロックなし)
- K-SystemZ から複数事件のボタンを連打すると複数の k-file が立ち上がる
- 同じファイルを 2 インスタンスから編集すると競合の恐れあり

#### この制約下での K-SystemZ 側挙動 (重要)
- 1 件目のボタン → k-file 起動 (CLI 引数で事件 A タブが開く) ← OK
- 2 件目のボタン → **もう 1 つの k-file が起動する** (事件 B タブが開く) ← 2 ウインドウ並ぶ
- ユーザーは「k-file が既に立ち上がっていることに気づかず、Explorer のごとく
  毎回起動」しがち

#### 暫定対応 (推奨)
K-SystemZ 側で「すでに k-file プロセスが起動中なら新規起動せず案内」のチェックを
入れる:
```python
import psutil
def is_kfile_running() -> bool:
    for p in psutil.process_iter(['name']):
        try:
            if p.info['name'] and p.info['name'].lower() == 'k-file.exe':
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

# open_folder ハンドラ内で:
if mode == "kfile" and is_kfile_running():
    return {
        "opened_with": "kfile_already_running",
        "path": str(folder),
        "message": (
            "k-file は既に起動中です。既存ウインドウで Ctrl+O から "
            "事件を開いてください。"
        ),
    }
```
- フロントエンドは toast / モーダル等でユーザーに通知
- 「強制的にもう 1 つ起動するか?」の選択肢を出してもよい (上級者向け)
- k-file 側の単一インスタンス + IPC (= 既存 k-file に「タブ追加して」と指示) は
  **M6b で実装予定**。実装されたら CLI 引数を渡すだけで自動的に既存ウインドウに
  ぶら下がるようになる → K-SystemZ 側のチェックロジックは不要に

### 5.3 k-file の設定は k-file 側で完結
- k-file 自身の設定 (Inbox 監視先、ksystemz.db パス、kfile.db の場所、open_tabs)
  はすべて `%APPDATA%\k-file\kfile.db` に保存
- **K-SystemZ 側はこれらに触らない**
- ただし重要: **K-SystemZ で `ksystemz.db` のパスが変わったら**、
  ユーザーは k-file 側の「ツール→設定…」で新パスを再設定する必要あり
  (連携自動化はしていない、ユーザーマニュアル運用)

### 5.4 k-file の動作要件
- Windows 10/11 (windows-latest GitHub Actions でビルド)
- 32-bit/64-bit: 64-bit
- インストール不要 (PyInstaller --onefile)、任意のフォルダに `k-file.exe` を置いて実行
- 推奨: `C:\Users\<user>\k-file\k-file.exe` 等の固定パスに置いて、
  K-SystemZ の設定でそのパスを指定

---

## 6. GitHub 関連 (K-SystemZ は GitHub を使わないため、ユーザー経由で知る情報)

### 6.1 k-file のリポジトリ
- URL: **https://github.com/windom21-cpu/k-file** (public)
- ユーザー: `windom21-cpu`
- メイン分岐: `main`
- ライセンス: 未設定 (個人プロジェクト、PySide6 は LGPL なのでそれに準じる)

### 6.2 リポジトリ内の主要ドキュメント
- ルート `HANDOVER.md` — k-file 本体の master 引き継ぎ書 (§0〜§16、ADR-1〜16)
- `docs/COLLABORATION.md` — 協働スタイル (素人前提・先回り提案・趣旨読み取り)
- `docs/UI-PRINCIPLES.md` — Win95/98 風 UI の PySide6 実装原則
- `docs/WORKFLOW.md` — 本機 ↔ Win 機の往復ループと事故ポイント
- `docs/CI-CD.md` — GitHub Actions で PyInstaller .exe ビルド
- `docs/VERSION-BUMPING.md` — マイルストーン制 alpha/beta/stable 運用
- `docs/HANDOVER-FOR-KSYSTEMZ.md` ← **あなたが読んでいるこのファイル**

### 6.3 ビルド & 配布 (k-file 側の仕組み)
- CI: GitHub Actions (`.github/workflows/build.yml`)
  - `main` への push → Windows .exe ビルド → Actions タブ artifact `k-file-windows` に 90 日保持
  - `v*` タグ push → GitHub Releases に upload (β は prerelease)
  - 手動実行 (workflow_dispatch) も可
- 配布: GitHub Releases (単一リポへ直 upload、separate releases リポは使わない)
- ユーザーは Releases (or Actions タブ) から `k-file.exe` (約 50 MB、--onefile) を DL

### 6.4 K-SystemZ は GitHub を使わない (重要な制約)
- K-SystemZ プロジェクトは Win 機ローカル開発、Git/GitHub 経由しない
- このため:
  - **あなた (K-SystemZ AI) は k-file のソースコードに直接アクセスできない**
  - **k-file の更新情報はユーザーが手動で持ってくる** (新機能・バグ修正)
  - **K-SystemZ 側のフィードバックはユーザーが手動で k-file 側 AI に伝える**
- → これに対処するため、このドキュメントは **k-file 側の現状を網羅** している。
  細部が必要な時はユーザーに「k-file の HANDOVER.md の §X を見せて」と頼む。

### 6.5 k-file の最新 .exe を入手する方法 (ユーザー向け、参考)
- 方法 1: GitHub Releases タブ → 最新リリースの `k-file.exe` を DL (β タグ以降)
- 方法 2: GitHub Actions タブ → 最新の successful run → Artifacts `k-file-windows` を DL
- どちらも単一 .exe、インストール不要、任意フォルダに置いて実行
- 更新: 新 .exe を上書きコピーするだけ (設定・履歴は `%APPDATA%\k-file\kfile.db` に
  残るので失わない)

### 6.6 k-file への要望/バグ報告のルート
```
ユーザー (Win 機で k-file 使用中)
   ↓ 不具合発見・要望
ユーザー (本機 Linux で k-file 開発)
   ↓ 修正・push
GitHub Actions (CI ビルド)
   ↓ artifact 生成
ユーザー (Win 機で新 .exe DL)
   ↓ 上書きコピー
新 k-file で再試行
```
- **あなたは k-file の修正をしない**。「k-file のここで困った」はユーザーに伝言してもらう。
- 一方、K-SystemZ 側で受け止められる問題 (例: 開発 AI 側で対応可能なフォルダ命名規則
  変更) は K-SystemZ 側で対応する。

---

## 7. 守ってほしいこと (再強調)

1. **k-file 側のソースには手を触れない** (アクセス手段がないし、独立したアプリ)
2. **`ksystemz.db` は K-SystemZ の管轄**。k-file は RO 参照だけ
3. **`folder_open_mode` の既定は `'explorer'`** (既存ユーザー影響ゼロ)
4. **Explorer フォールバックを必ず実装** (k-file 起動失敗時に業務止めない)
5. **K-SystemZ DB スキーマの破壊的変更は事前通知**:
   - `case_code` 形式変更
   - `office_info.doc_root_path` の意味論変更
   - `case_persons.role` ラベル変更 (現在 `'依頼者'` を使っている)
   - `cases.is_deleted` / `persons.is_deleted` フラグの意味変更
   などは、変更前に **ユーザー経由で k-file 側 AI に「次のアップデートで XX が変わる」と
   伝言** してほしい (連絡は人手の往復になるので「変更後に気づく」では遅い)
6. **ユーザー手元の業務データの取り扱い**:
   - K-SystemZ プロジェクトのコード本体は外部 (GitHub 等) に出さない
   - 実 ksystemz.db は外部に出さない
   - 業務データ (事件名・依頼者名) は AI 間でやり取りする際もマスクする

---

## 8. テスト & フィードバック収集

### 8.1 切替前の最小動作確認 (K-SystemZ 側で実装後)
1. `folder_open_mode='explorer'` (既定) で従来動作維持の確認
2. `folder_open_mode='kfile'` + 正しい `kfile_exe_path` で k-file が起動することの確認
3. `folder_open_mode='kfile'` + 不正パス で Explorer にフォールバックすることの確認
4. `is_kfile_running()` チェック実装の場合: 2 重起動回避の確認
5. `folder_open_mode='kfile'` で k-file 未インストール (PATH にもなし) のフォールバック確認

### 8.2 運用フェーズで集めるべきフィードバック (ユーザー視点)
| 観点 | 具体的に見る | 改善先 |
|---|---|---|
| 起動速度 | Explorer と比較して耐えられるか | k-file 側 (起動最適化) |
| 多重起動 | 複数 k-file が立つ混乱 | k-file M6b (単一インスタンス + IPC) |
| 落ちる/反応しない | バグ報告 (何をした時、何が起きた) | k-file 側 (バグ修正) |
| AB 集約運用 | 「他事件へ」+ ショートカットダブルクリックでタブ切替 | 業務フローに乗るかの検証 |
| Inbox の使い勝手 | 6 分類が業務カテゴリと合うか | UX 改善議論 |
| 削除・Undo | OS ごみ箱経由の戻し動線が直感的か | UI 改善議論 |

### 8.3 フィードバックの戻し方
- ユーザーが本機 (Linux) の k-file 側 AI に **直接** 伝える
- あなた (K-SystemZ AI) からは: ユーザーが「k-file 側に伝えてほしい」と言ったら、
  「では k-file 側にこの内容を伝えてください」と返す程度で OK
- K-SystemZ 側で対応すべきフィードバック (例: K-SystemZ の DB スキーマ修正で
  k-file の動作が改善するケース) は K-SystemZ で対応 → 次回 K-SystemZ アップデートで反映

---

## 9. このドキュメントの位置付けとメンテナンス

### 配置
`docs/HANDOVER-FOR-KSYSTEMZ.md` (k-file リポジトリ内)

### 配布方法
ユーザーが本ファイルをコピーして K-SystemZ 側 AI に渡す
(最初の 1 ファイル単独配布を想定。**自己完結性が重要**)

### 更新タイミング
- k-file 側で `folder_open_mode` 連携の前提が変わったら → ユーザー経由で更新依頼
- k-file の M6 (CLI 引数 / 単一インスタンス) が実装されたら → 「5. 制約」セクション更新
- DB スキーマ拡張 (例: ksystemz.db 側 cases に列追加) があったら → 「2.2 読むテーブル」更新

### 参照優先順位
1. **このドキュメント** (`docs/HANDOVER-FOR-KSYSTEMZ.md`) — まずここを読む
2. k-file 本体の `HANDOVER.md` — 細部が必要な時のみ。ユーザーから抜粋を貰う
3. `docs/COLLABORATION.md` — 協働スタイル参考 (k-file 側 AI 向けだが共通する部分あり)

---

## 10. 連絡先・関連プロジェクト

- **ユーザー**: sk21.lawyer@gmail.com (法律実務家、Win/Linux 両機を運用)
- **k-file プロジェクト**: https://github.com/windom21-cpu/k-file
- **k-file 本体引き継ぎ書**: `HANDOVER.md` (リポジトリルート、ユーザーから抜粋を渡してもらう)
- **K-SystemZ 引き継ぎ書** (Win 機側 = あなたの足下): K-SystemZ プロジェクト内の
  `AI引き継ぎ_詳細版_v22.md` / `AI引き継ぎ_セッション_*.md` を参照
- **姉妹アプリ k-pdf3**: Electron + mupdf-wasm の PDF 業務アプリ (本機 ↔ Win 機ワークフローの確立元)

---

## 付録 A: 実装チェックリスト (K-SystemZ 側 AI 用)

着手前に、ユーザーと以下を確認:

- [ ] `office_info.kfile_exe_path TEXT DEFAULT ''` 列追加 (migration スクリプト) で OK か
- [ ] 設定ページに「フォルダ挙動」セクション追加位置 (既存タイル UI のどこか) で OK か
- [ ] `folder_open_mode` の値は `'explorer'` / `'kfile'` のリテラル 2 種で OK か (将来 'finder' 追加余地)
- [ ] バックエンドの `open_folder` ハンドラ拡張位置 (`backend/cases.py`) の特定
- [ ] 2 重起動チェック (`is_kfile_running` ヘルパ) を入れるか
- [ ] フォールバック動作のログ出力先 (既存ログハンドラに合わせる)

実装後、ユーザーと一緒に:
- [ ] 設定 UI から `'kfile'` に切替 → 業務事件 1 件のフォルダ開く → k-file 起動 OK
- [ ] 設定 UI から `'explorer'` に戻す → Explorer 起動 OK
- [ ] `kfile_exe_path` に不正パス入力 → Explorer フォールバック OK
- [ ] k-file 起動中に再度押下 → 2 重起動回避メッセージ OK (実装した場合)
- [ ] 業務 5〜10 件で 1 週間運用 → フィードバック収集
- [ ] フィードバックに基づいて K-SystemZ 側 / k-file 側 で対応分担

---

以上。質問があれば、まずこのドキュメント内で解決できないかを確認してから、
ユーザー経由で k-file 側 AI に問い合わせてください。
