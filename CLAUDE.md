# k-file プロジェクト

Python + PySide6 で .exe 配布する業務用デスクトップアプリ。
Windows95/98 風レトロ UI (MS UI Gothic / 灰色基調 / beveled / 高密度) を最優先する。

## ユーザー前提
- ユーザーは法律実務家 (sk21.lawyer@gmail.com)、プログラミングは素人前提。
- メイン機は Linux (Ubuntu Wayland)、配布動作確認は Win 機。
- 作業フロー: 本機 (Linux) で実装 → GitHub push → CI で .exe ビルド → Win 機で DL/試用 → Win 機でも修正 push → 本機 pull → 続行。

## このリポジトリの構成
- `HANDOVER.md` — master document。AI セッション間引き継ぎの一次資料。**ユーザー明示依頼時のみ更新**、β タグ毎に勝手に refresh しない。
- `README.md` — 短い概要のみ。
- `docs/` — ノウハウ集 (k-pdf3 から転用)。新セッションは以下の順で読む:
  1. `docs/COLLABORATION.md` — 協働スタイル (最優先)
  2. `docs/UI-PRINCIPLES.md` — Win95/98 風 UI を PySide6 で実現する原則
  3. `docs/WORKFLOW.md` — 本機 ↔ Win 機の往復ループと事故ポイント
  4. `docs/CI-CD.md` — GitHub Actions で PyInstaller .exe ビルド
  5. `docs/VERSION-BUMPING.md` — マイルストーン制 alpha/beta/stable 運用

## やってはいけないこと
- HANDOVER.md を勝手に更新しない。
- レトロ UI 方針を曲げない (モダン Web 風に流れない)。
- 「素人にも分かる」を素人化と取り違えない: 説明は分かりやすく、実装は妥協しない。
- 機能追加より「業務凍結級バグの修正」を優先 (β 配布後)。

## 関連
- 姉妹アプリ k-pdf3 (Electron + mupdf-wasm)。配布フェーズの知見は `docs/` 各ファイルに圧縮済。
