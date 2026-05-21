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
