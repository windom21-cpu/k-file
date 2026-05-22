"""右 プレビューペイン (PDF: QPdfView / 画像: QPixmap)

ファイル選択時に show_file(path) が呼ばれ、拡張子に応じて PDF or 画像を
プレビューする。対象外・読込失敗・未選択はメッセージ表示。
QStackedWidget で [メッセージ / PDF / 画像] を切り替える。

複数ページ PDF はスクロールに加え、下端のページ送りバー (◀ N/総数 ▶) で
ページ移動できる。バーは複数ページのときだけ表示する。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.pane_header import PaneHeader

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff"}


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
            self._show_message("ファイルを選択するとプレビュー表示")
            return
        p = Path(path)
        if not p.is_file():
            self._show_message("ファイルが見つかりません")
            return
        ext = p.suffix.lower()
        if ext == ".pdf":
            self._show_pdf(p)
        elif ext in _IMAGE_EXTS:
            self._show_image(p)
        else:
            self._show_message(f"プレビュー対象外のファイル\n({ext})")

    def _show_pdf(self, p: Path) -> None:
        self._pdf_doc.load(str(p))
        if self._pdf_doc.status() == QPdfDocument.Status.Ready:
            self._update_page_bar()
            self._stack.setCurrentWidget(self._pdf_container)
        else:
            self._show_message(f"PDF を読み込めません\n{p.name}")

    def _show_image(self, p: Path) -> None:
        pm = QPixmap(str(p))
        if pm.isNull():
            self._show_message(f"画像を読み込めません\n{p.name}")
            return
        self._image_view.set_image(pm)
        self._stack.setCurrentWidget(self._image_view)

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
