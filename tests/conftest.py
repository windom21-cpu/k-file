"""pytest 共有セットアップ。

QWidget を使うテスト (test_resize_grips など) は widget 対応の QApplication を
必要とする。一方 test_preview は QImage 用に QGuiApplication を作る。Qt は
アプリケーションオブジェクトを 1 つしか持てず、先に QGuiApplication (基底クラス)
が出来てしまうと後から QApplication (派生クラス) を作れず、QWidget 生成時に
クラッシュする。

そこで collection の最初 (conftest はテストモジュールより先に import される) に
QApplication を 1 つだけ用意しておく。QApplication は QGuiApplication の
サブクラスなので、以降の QGuiApplication.instance() / QApplication.instance() は
いずれもこの widget 対応アプリを返し、衝突しなくなる。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

# セッション全体で共有する唯一の QApplication。参照を保持して GC を防ぐ。
_app = QApplication.instance() or QApplication([])
