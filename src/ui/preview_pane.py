"""右 プレビューペイン (PDF: QPdfView / 画像: QPixmap / テキスト: QPlainTextEdit)

ファイル選択時に show_file(path) が呼ばれ、拡張子に応じて切り替え:
- PDF (.pdf) → QPdfView (複数ページのページ送りバー付)
- 画像 → QPixmap で拡縮表示
- テキスト/JSON (.txt/.json/.k-photo 等) → QPlainTextEdit。JSON は indent=2 整形
- それ以外 → 「対象外」メッセージ

QStackedWidget で [メッセージ / PDF / 画像 / テキスト] を切り替える。
大きいテキストは先頭 64KB のみ表示 (法律実務で何 MB のテキストはまず無いが保険)。
文字コードは UTF-8 → CP932 → latin-1 の順にフォールバック。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.pane_header import PaneHeader

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff"}

# テキストプレビュー対象 (生 JSON / 各種ログ / メモ 等)。
# .k-photo (k-systemz サブアプリの JSON 一時保存) も対象。
_TEXT_EXTS = {".txt", ".log", ".md", ".csv", ".tsv", ".ini", ".cfg"}
_JSON_EXTS = {".json", ".k-photo"}

# 大きいファイルを開いた時の保護: 先頭 N バイトのみ読む
_TEXT_PREVIEW_CAP = 64 * 1024


def _read_text_with_fallback(p: Path, cap: int = _TEXT_PREVIEW_CAP) -> tuple[str, bool]:
    """ファイルを bytes で読んで UTF-8 → CP932 → latin-1 の順で decode。

    返り値: (テキスト, 切詰めしたか)。切詰めした場合は末尾を `…` で示す。
    """
    raw = p.read_bytes()
    truncated = False
    if len(raw) > cap:
        raw = raw[:cap]
        truncated = True
    for enc in ("utf-8", "utf-8-sig", "cp932", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        # ここに来ることはほぼ無い (latin-1 は任意の byte を受け入れる)
        text = raw.decode("latin-1", errors="replace")
    if truncated:
        text += "\n\n…(以降省略)…"
    return text, truncated


class _ImageView(QLabel):
    """画像をペインに収まるよう縦横比維持で拡縮表示する QLabel。"""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("previewImage")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._src: QPixmap | None = None

    def set_image(self, pixmap: QPixmap) -> None:
        self._src = pixmap
        self._rescale()

    def _rescale(self) -> None:
        if self._src is None or self._src.isNull():
            self.clear()
            return
        self.setPixmap(
            self._src.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._rescale()
        super().resizeEvent(event)


class PreviewPane(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(PaneHeader("プレビュー"))

        # 現在見ているファイルの情報を 1 行で常時表示 (業務で「これ何だっけ」防止)
        self._info_label = QLabel("")
        self._info_label.setObjectName("previewInfo")
        self._info_label.setStyleSheet(
            "QLabel#previewInfo {"
            "  background-color: #FFFFFF;"
            "  border-top: 1px solid #808080;"
            "  border-left: 1px solid #808080;"
            "  border-right: 1px solid #FFFFFF;"
            "  border-bottom: 1px solid #FFFFFF;"
            "  padding: 0 4px;"
            "  min-height: 22px;"
            "  font-size: 12pt;"
            "}"
        )
        outer.addWidget(self._info_label)

        self._stack = QStackedWidget()

        # [0] メッセージ (未選択 / 対象外 / 読込失敗)
        self._message = QLabel("ファイルを選択するとプレビュー表示")
        self._message.setObjectName("previewPlaceholder")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._stack.addWidget(self._message)

        # [1] PDF (QPdfView + ページ送りバー)
        self._stack.addWidget(self._build_pdf_page())

        # [2] 画像
        self._image_view = _ImageView()
        self._stack.addWidget(self._image_view)

        # [3] テキスト / JSON (.txt/.json/.k-photo 等)
        self._text_view = QPlainTextEdit()
        self._text_view.setObjectName("previewText")
        self._text_view.setReadOnly(True)
        self._text_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # 等幅で読みやすいよう既定フォントを上書き (本体の MS Gothic 12pt 戦略は
        # main.py 起動後に apply_bitmap_font_strategy で再付与される)
        self._stack.addWidget(self._text_view)

        outer.addWidget(self._stack, stretch=1)

    def _build_pdf_page(self) -> QWidget:
        """QPdfView + 下端のページ送りバーをまとめた PDF 表示ウィジェット。"""
        self._pdf_doc = QPdfDocument(self)
        self._pdf_view = QPdfView()
        self._pdf_view.setObjectName("previewPdf")
        self._pdf_view.setDocument(self._pdf_doc)
        self._pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self._pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._navigator = self._pdf_view.pageNavigator()
        self._navigator.currentPageChanged.connect(
            lambda _page: self._update_page_bar()
        )

        # ページ送りバー (複数ページ PDF のみ表示)
        self._page_bar = QWidget()
        self._page_bar.setObjectName("pageBar")
        self._page_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar = QHBoxLayout(self._page_bar)
        bar.setContentsMargins(2, 1, 2, 1)
        bar.setSpacing(3)
        bar.addStretch(1)
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setObjectName("pageNavBtn")
        self._prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._prev_btn.clicked.connect(self._prev_page)
        bar.addWidget(self._prev_btn)
        self._page_label = QLabel("1 / 1")
        self._page_label.setObjectName("pageLabel")
        bar.addWidget(self._page_label)
        self._next_btn = QPushButton("▶")
        self._next_btn.setObjectName("pageNavBtn")
        self._next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._next_btn.clicked.connect(self._next_page)
        bar.addWidget(self._next_btn)
        bar.addStretch(1)
        self._page_bar.setVisible(False)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._pdf_view, stretch=1)
        lay.addWidget(self._page_bar)
        self._pdf_container = container
        return container

    def show_file(self, path: str) -> None:
        """選択されたファイルをプレビュー表示する。空文字なら未選択表示。"""
        if not path:
            self.clear()
            return
        p = Path(path)
        if not p.is_file():
            self.clear()
            self._show_message("ファイルが見つかりません")
            return
        ext = p.suffix.lower()
        if ext == ".pdf":
            self._show_pdf(p)
        elif ext in _IMAGE_EXTS:
            # 直前に PDF を見ていた場合は document を解放してからでないと
            # Win 側でファイルロックが残るため、必ず close() を挟む
            self._release_pdf()
            self._show_image(p)
        elif ext in _JSON_EXTS:
            self._release_pdf()
            self._image_view.set_image(QPixmap())
            self._show_json(p)
        elif ext in _TEXT_EXTS:
            self._release_pdf()
            self._image_view.set_image(QPixmap())
            self._show_text(p)
        else:
            self._release_pdf()
            self._image_view.set_image(QPixmap())
            self._text_view.clear()
            self._update_info(p, extra="")
            self._show_message(f"プレビュー対象外のファイル\n({ext})")

    def clear(self) -> None:
        """プレビューを完全に閉じる: PDF document を解放してファイルロックを外し、
        画像 pixmap も破棄して、上部情報行とメッセージを初期状態に戻す。

        Win では QPdfDocument が load 後ファイルハンドルを保持し続けるため、
        削除/移動/リネーム前に必ずこれを呼ぶこと (呼ばないと「自分が掴んでいる」
        エラーになる)。F3 で隠す時・ウインドウ非アクティブ時にも呼ぶ。
        """
        self._release_pdf()
        self._image_view.set_image(QPixmap())
        self._text_view.clear()
        self._info_label.setText("")
        self._info_label.setToolTip("")
        self._show_message("ファイルを選択するとプレビュー表示")

    def _release_pdf(self) -> None:
        """QPdfDocument を確実に閉じてファイルハンドルを解放する。"""
        try:
            if self._pdf_doc.status() != QPdfDocument.Status.Null:
                self._pdf_doc.close()
        except RuntimeError:
            pass  # 既に解放されている等

    def _update_info(self, p: Path, extra: str = "") -> None:
        """上部固定ヘッダーをファイル情報で更新。
        extra に PDF ページ数等の追加情報を渡せる。"""
        try:
            st = p.stat()
            size_kb = st.st_size // 1024
            size_text = (
                f"{size_kb}KB" if size_kb < 1024
                else f"{st.st_size / (1024 * 1024):.1f}MB"
            )
            mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            parts = [p.name, size_text, mtime]
            if extra:
                parts.append(extra)
            self._info_label.setText("/".join(parts))
            self._info_label.setToolTip(str(p))
        except OSError:
            self._info_label.setText(p.name)
            self._info_label.setToolTip(str(p))

    def _show_pdf(self, p: Path) -> None:
        self._pdf_doc.load(str(p))
        if self._pdf_doc.status() == QPdfDocument.Status.Ready:
            total = self._pdf_doc.pageCount()
            self._update_info(p, extra=f"{total} ページ" if total > 0 else "")
            self._update_page_bar()
            self._stack.setCurrentWidget(self._pdf_container)
        else:
            self._update_info(p, extra="読込失敗")
            self._show_message(f"PDF を読み込めません\n{p.name}")

    def _show_image(self, p: Path) -> None:
        pm = QPixmap(str(p))
        if pm.isNull():
            self._update_info(p, extra="読込失敗")
            self._show_message(f"画像を読み込めません\n{p.name}")
            return
        extra = f"{pm.width()}×{pm.height()}px"
        self._update_info(p, extra=extra)
        self._image_view.set_image(pm)
        self._stack.setCurrentWidget(self._image_view)

    def _show_text(self, p: Path) -> None:
        """テキスト (.txt/.log/.md/.csv 等) を QPlainTextEdit に表示。"""
        try:
            text, truncated = _read_text_with_fallback(p)
        except OSError as e:
            self._update_info(p, extra="読込失敗")
            self._show_message(f"テキストを読み込めません\n{p.name}\n{e}")
            return
        extra = "切詰め表示" if truncated else f"{len(text):,} 文字"
        self._update_info(p, extra=extra)
        self._text_view.setPlainText(text)
        self._stack.setCurrentWidget(self._text_view)

    def _show_json(self, p: Path) -> None:
        """JSON (.json/.k-photo) は indent=2 で整形して表示。
        パースに失敗したら生テキストとして表示 (corrupt JSON 等の状況を温存)。"""
        try:
            raw, truncated = _read_text_with_fallback(p)
        except OSError as e:
            self._update_info(p, extra="読込失敗")
            self._show_message(f"JSON を読み込めません\n{p.name}\n{e}")
            return
        # 切詰めしたら JSON として parse できないので raw 表示にフォールバック
        if truncated:
            self._update_info(p, extra="切詰め表示")
            self._text_view.setPlainText(raw)
            self._stack.setCurrentWidget(self._text_view)
            return
        try:
            obj = json.loads(raw)
            formatted = json.dumps(obj, ensure_ascii=False, indent=2)
            extra = "JSON 整形済"
        except ValueError:
            formatted = raw
            extra = "JSON parse 失敗 (生表示)"
        self._update_info(p, extra=extra)
        self._text_view.setPlainText(formatted)
        self._stack.setCurrentWidget(self._text_view)

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message)

    # ───────── ページ送り ─────────

    def _update_page_bar(self) -> None:
        """現在ページ・総ページ数に合わせてページ送りバーを更新する。"""
        total = self._pdf_doc.pageCount()
        page = self._navigator.currentPage()
        self._page_bar.setVisible(total > 1)
        self._page_label.setText(f"{page + 1} / {total}")
        self._prev_btn.setEnabled(page > 0)
        self._next_btn.setEnabled(page < total - 1)

    def _prev_page(self) -> None:
        page = self._navigator.currentPage()
        if page > 0:
            self._navigator.jump(page - 1, QPointF(), 0)

    def _next_page(self) -> None:
        page = self._navigator.currentPage()
        if page < self._pdf_doc.pageCount() - 1:
            self._navigator.jump(page + 1, QPointF(), 0)
