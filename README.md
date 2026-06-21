# k-file

Python + PySide6 製の Windows 業務アプリ (.exe 配布)。

詳細は `HANDOVER.md` と `docs/` を参照。新規セッションは `CLAUDE.md` から。

## 開発
```bash
python -m venv .venv
source .venv/bin/activate   # Win: .venv\Scripts\activate
pip install -r requirements.txt
python -m src.main
```

## ビルド (Win)
GitHub Actions が `windows-latest` runner で PyInstaller を回す。詳細は `docs/CI-CD.md`。

## 配布
GitHub Releases で配布。初回はインストーラ (`k-file-setup.exe` / Inno Setup、ユーザー領域・管理者権限不要)、
以降は **起動時の自動アップデート** (新版検知 → 1 クリック DL → SHA256 照合 → 再起動で反映)。
