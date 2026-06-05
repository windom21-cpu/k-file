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
import stat as _stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QObject,
    QPointF,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.pane_header import PaneHeader

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff"}

# テキストプレビュー対象 (生 JSON / 各種ログ / メモ 等)。
# k-systemz サブアプリの保存形式も JSON ベースなので整形プレビューする:
#  - K-photo:  `.kphoto`
#  - K-evi:    `.kevi`
# 旧 `.k-photo` (ハイフン入り) は後方互換で残す (2026-05-26 K-SystemZ 連携確認)。
_TEXT_EXTS = {".txt", ".log", ".md", ".csv", ".tsv", ".ini", ".cfg"}
_JSON_EXTS = {".json", ".kphoto", ".kevi", ".k-photo"}

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


@dataclass
class _LoadResult:
    """worker スレッドが読み終えた結果を main スレッドへ渡す struct。

    GUI 構築 (QPdfDocument.load / QPixmap.fromImage / setPlainText) は main 専用な
    ので、ここには「読み終えた生データ + stat 情報 + どの種別か」だけを載せる。
    `seq` は show_file 採番の通し番号で、main 側で stale (= もっと新しい選択が来た)
    を捨てるのに使う。
    """

    seq: int
    path: Path
    kind: str            # 'pdf'|'image'|'text'|'json'|'unsupported'|'missing'|'error'
    size: int = 0
    mtime: float = 0.0
    ext: str = ""
    pdf_bytes: bytes | None = None
    image: QImage | None = None
    text: str | None = None
    truncated: bool = False
    error: str = ""


def _load_preview(path: Path, seq: int) -> _LoadResult:
    """worker スレッド側の実 I/O。X:(Dropbox) 上のファイルは stat/read が
    hydrate 完了まで長時間ブロックしうるため、必ず別スレッドから呼ぶこと。

    Qt 非依存ではない (QImage を使う) が、QImage は GUI 非依存オブジェクトなので
    worker スレッドで生成して問題ない (main では QPixmap.fromImage に渡すだけ)。
    """
    try:
        st = path.stat()
    except OSError:
        return _LoadResult(seq, path, "missing")
    if not _stat.S_ISREG(st.st_mode):
        return _LoadResult(seq, path, "missing")
    size, mtime = st.st_size, st.st_mtime
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            data = path.read_bytes()
            return _LoadResult(
                seq, path, "pdf", size, mtime, ext, pdf_bytes=data
            )
        if ext in _IMAGE_EXTS:
            img = QImage(str(path))
            if img.isNull():
                return _LoadResult(
                    seq, path, "error", size, mtime, ext,
                    error="画像を読み込めません",
                )
            return _LoadResult(seq, path, "image", size, mtime, ext, image=img)
        if ext in _JSON_EXTS:
            text, trunc = _read_text_with_fallback(path)
            return _LoadResult(
                seq, path, "json", size, mtime, ext,
                text=text, truncated=trunc,
            )
        if ext in _TEXT_EXTS:
            text, trunc = _read_text_with_fallback(path)
            return _LoadResult(
                seq, path, "text", size, mtime, ext,
                text=text, truncated=trunc,
            )
        return _LoadResult(seq, path, "unsupported", size, mtime, ext)
    except OSError as e:
        return _LoadResult(
            seq, path, "error", size, mtime, ext, error=str(e)
        )


class _PreviewSignals(QObject):
    done = Signal(object)   # _LoadResult


class _PreviewWorker(QRunnable):
    """1 回分のプレビュー読込を QThreadPool で走らせる runnable。"""

    def __init__(self, path: Path, seq: int) -> None:
        super().__init__()
        self.signals = _PreviewSignals()
        self._path = path
        self._seq = seq

    def run(self) -> None:   # noqa: N802 (Qt override)
        self.signals.done.emit(_load_preview(self._path, self._seq))


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
        self._info_full = ""   # 省略前のフル文字列 (resize で再 elide するため保持)
        self._info_label = QLabel("")
        self._info_label.setObjectName("previewInfo")
        # 横方向は Ignored: 長いファイル名でもラベルが「自分の幅」を主張しない。
        # これをしないと折返し無し QLabel の minimumSizeHint = 全文幅 となり、
        # プレビューペインの最小幅がファイル名の長さぶん膨らみ、splitter が
        # プレビューを広げて INBOX だけを極端に狭くしてしまう (2026-06-05 修正)。
        self._info_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
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

        # ── 非同期読込 (X:=Dropbox の同期 I/O で UI が固まるのを防ぐ) ──
        # ファイル選択のたびに seq を採番し、worker スレッドで stat+read を実行。
        # 結果が返った時に seq が最新でなければ捨てる (クリック連打で古い読込が
        # 後から上書きするのを防止)。pool は 2 並列までに制限。
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._req_seq = 0
        # 読込が 150ms 以上かかる時だけ「読込中...」を出す (ローカルの即時読込で
        # チラつかせないため)。結果が早く返れば stop でキャンセルされる。
        self._loading_timer = QTimer(self)
        self._loading_timer.setSingleShot(True)
        self._loading_timer.setInterval(150)
        self._loading_timer.timeout.connect(self._show_loading)

    def _set_info_text(self, text: str) -> None:
        """上部情報行のテキストを設定 (幅に合わせて右省略表示する)。

        フル文字列は _info_full に保持し、resizeEvent で再 elide する。
        """
        self._info_full = text
        self._elide_info()

    def _elide_info(self) -> None:
        """保持中のフル文字列を現在のラベル幅に合わせて右省略する。"""
        fm = self._info_label.fontMetrics()
        avail = self._info_label.width() - 8   # padding 0 4px ぶんを控除
        if avail <= 0 or not self._info_full:
            # まだ幅が確定していない (表示前) 等はフルのまま (clip は Qt 任せ)
            self._info_label.setText(self._info_full)
            return
        self._info_label.setText(
            fm.elidedText(self._info_full, Qt.TextElideMode.ElideRight, avail)
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._elide_info()

    def _build_pdf_page(self) -> QWidget:
        """QPdfView + 下端のページ送りバーをまとめた PDF 表示ウィジェット。"""
        self._pdf_doc = QPdfDocument(self)
        # ファイルパス直 load だと Win 上で PDFium がファイルハンドルを保持
        # し続け、close() しても rename/delete が「使用中」エラーで失敗する
        # (2026-05-26)。bytes を一旦読んで QBuffer 経由で load することで
        # Qt 側にファイルハンドルを持たせない方針に変更。バッファと bytes の
        # 寿命を self で管理 (load 完了後も lazy 解析のため参照を保つ必要)。
        self._pdf_data: QByteArray | None = None
        self._pdf_buffer: QBuffer | None = None
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
        """選択されたファイルをプレビュー表示する。空文字なら未選択表示。

        実 I/O (stat / read / 画像デコード) は worker スレッドへ逃がす。X: 上の
        Dropbox ファイルは hydrate に時間がかかり、ここで同期 read すると UI が
        固まる (= フリーズの主因, 2026-05-29) ため。読込完了は `_on_loaded` で
        受け、その時点で最新の選択 (seq 一致) の時だけ描画する。
        """
        # 新しい選択 → seq を進める。これで in-flight の古い worker 結果は捨てられる。
        self._req_seq += 1
        seq = self._req_seq
        if not path:
            self._loading_timer.stop()
            self.clear()
            return
        # 読込が長引く時だけ「読込中...」を出す (タイマーで遅延)。現在の表示は
        # 結果が返るまで残す (ローカル即時読込でのチラつき防止)。
        self._loading_timer.start()
        worker = _PreviewWorker(Path(path), seq)
        worker.signals.done.connect(self._on_loaded)
        self._pool.start(worker)

    def _show_loading(self) -> None:
        """読込が 150ms を超えた時に呼ばれる (タイマー)。"""
        self._show_message("読込中...")

    def _on_loaded(self, result: object) -> None:
        """worker スレッドから読込結果を受けて描画する (main スレッド)。"""
        if not isinstance(result, _LoadResult):
            return
        if result.seq != self._req_seq:
            return  # もっと新しい選択が来ている → 破棄
        self._loading_timer.stop()
        p = result.path
        kind = result.kind
        if kind == "missing":
            self.clear()
            self._show_message("ファイルが見つかりません")
            return
        if kind == "error":
            self._release_pdf()
            self._image_view.set_image(QPixmap())
            self._text_view.clear()
            self._update_info(p, extra="読込失敗", size=result.size,
                              mtime=result.mtime)
            self._show_message(f"読み込めません\n{p.name}\n{result.error}")
            return
        if kind == "pdf":
            self._render_pdf(result)
        elif kind == "image":
            self._release_pdf()
            self._render_image(result)
        elif kind in ("json", "text"):
            self._release_pdf()
            self._image_view.set_image(QPixmap())
            self._render_text(result)
        else:   # unsupported
            self._release_pdf()
            self._image_view.set_image(QPixmap())
            self._text_view.clear()
            self._update_info(p, extra="", size=result.size, mtime=result.mtime)
            self._show_message(f"プレビュー対象外のファイル\n({result.ext})")

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
        self._set_info_text("")
        self._info_label.setToolTip("")
        self._show_message("ファイルを選択するとプレビュー表示")

    def _release_pdf(self) -> None:
        """QPdfDocument を閉じて in-memory バッファも解放する。

        PDF は QBuffer 経由の in-memory bytes として load しているため、Qt 側は
        ファイルハンドルを保持していない (`_show_pdf` 冒頭で `p.read_bytes()`
        を完了した時点で OS のファイルハンドルは閉じている)。close() は表示
        状態を Null に戻し、buffer/bytes 参照を捨ててメモリを解放するために呼ぶ。
        """
        try:
            if self._pdf_doc.status() != QPdfDocument.Status.Null:
                self._pdf_doc.close()
        except RuntimeError:
            pass  # 既に解放されている等
        if self._pdf_buffer is not None:
            try:
                self._pdf_buffer.close()
            except RuntimeError:
                pass
            self._pdf_buffer = None
        self._pdf_data = None

    def _update_info(
        self,
        p: Path,
        extra: str = "",
        *,
        size: int | None = None,
        mtime: float | None = None,
    ) -> None:
        """上部固定ヘッダーをファイル情報で更新。
        extra に PDF ページ数等の追加情報を渡せる。

        size / mtime は worker が stat 済みの値を渡すと、ここで再度 X:(Dropbox)
        に stat しに行かずに済む (= main スレッドをブロックしない)。未指定時のみ
        フォールバックで p.stat() する。
        """
        try:
            if size is None or mtime is None:
                st = p.stat()
                size = st.st_size
                mtime = st.st_mtime
            size_kb = size // 1024
            size_text = (
                f"{size_kb}KB" if size_kb < 1024
                else f"{size / (1024 * 1024):.1f}MB"
            )
            mtime_text = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            parts = [p.name, size_text, mtime_text]
            if extra:
                parts.append(extra)
            self._set_info_text("/".join(parts))
            self._info_label.setToolTip(str(p))
        except OSError:
            self._set_info_text(p.name)
            self._info_label.setToolTip(str(p))

    def _render_pdf(self, result: _LoadResult) -> None:
        """worker が読んだ PDF bytes を QBuffer 経由で load する (main スレッド)。

        QPdfDocument に直接ファイルパスを渡すと Win の PDFium がハンドルを
        保持し続け、close() 後も rename/delete が「使用中」で失敗する
        (2026-05-25 本番テスト) → bytes 読込み + QBuffer 経由で Qt にハンドル
        を持たせない (ADR-23)。bytes の read は worker スレッドで完了済みなので、
        ここでファイルハンドルを掴むことは無い。
        """
        p = result.path
        # 旧バッファがあれば先に解放 (PDF 連続表示時のメモリリーク防止)
        self._release_pdf()
        # QByteArray と QBuffer は self で寿命管理 (Qt の lazy 解析が参照を保つため)
        self._pdf_data = QByteArray(result.pdf_bytes)
        self._pdf_buffer = QBuffer(self._pdf_data, self)
        self._pdf_buffer.open(QBuffer.OpenModeFlag.ReadOnly)
        self._pdf_doc.load(self._pdf_buffer)
        if self._pdf_doc.status() == QPdfDocument.Status.Ready:
            total = self._pdf_doc.pageCount()
            self._update_info(
                p, extra=f"{total} ページ" if total > 0 else "",
                size=result.size, mtime=result.mtime,
            )
            self._update_page_bar()
            self._stack.setCurrentWidget(self._pdf_container)
        else:
            self._update_info(p, extra="読込失敗", size=result.size,
                              mtime=result.mtime)
            self._show_message(f"PDF を読み込めません\n{p.name}")

    def _render_image(self, result: _LoadResult) -> None:
        """worker がデコードした QImage を QPixmap にして表示 (main スレッド)。"""
        p = result.path
        pm = QPixmap.fromImage(result.image)
        if pm.isNull():
            self._update_info(p, extra="読込失敗", size=result.size,
                              mtime=result.mtime)
            self._show_message(f"画像を読み込めません\n{p.name}")
            return
        extra = f"{pm.width()}×{pm.height()}px"
        self._update_info(p, extra=extra, size=result.size, mtime=result.mtime)
        self._image_view.set_image(pm)
        self._stack.setCurrentWidget(self._image_view)

    def _render_text(self, result: _LoadResult) -> None:
        """worker が読んだテキスト/JSON を表示 (main スレッド)。

        JSON (_JSON_EXTS) は indent=2 で整形。切詰め or parse 失敗時は生表示
        (corrupt JSON 等の状況を温存)。json.loads は 64KB 上限の CPU 処理なので
        main スレッドで実行して問題ない。
        """
        p = result.path
        text = result.text or ""
        truncated = result.truncated
        if result.kind == "json" and not truncated:
            try:
                obj = json.loads(text)
                text = json.dumps(obj, ensure_ascii=False, indent=2)
                extra = "JSON 整形済"
            except ValueError:
                extra = "JSON parse 失敗 (生表示)"
        elif truncated:
            extra = "切詰め表示"
        else:
            extra = f"{len(text):,} 文字"
        self._update_info(p, extra=extra, size=result.size, mtime=result.mtime)
        self._text_view.setPlainText(text)
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
