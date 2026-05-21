# UI 原則 — Windows95/98 風業務アプリ

PySide6 で Win95/98 風レトロ業務アプリ感を実現する。
**この方針からは絶対に外れない**。モダン Flat / マテリアル / Tailwind 風が便利そうに見えても採用しない。

## 必須要素

| 要素 | 仕様 |
|---|---|
| フォント | **MS UI Gothic** (Win 機標準、無ければ MS Gothic) |
| フォントサイズ | 9pt 基本 (12px 相当)、見出し 10-11pt |
| 背景色 | `#C0C0C0` (Win95 灰色) |
| 文字色 | `#000000` |
| ボタン | beveled (上左白 / 下右黒の 2 段 border) |
| 枠 | inset / outset の凹凸境界 |
| 余白 | 最小限 (padding 2-4px、margin 0 がベース) |
| 角 | 直角 (border-radius 禁止) |
| 影 | ドロップシャドウ禁止 (Win95 はフラット 2D) |

## PySide6 / QSS での実装

### 1. グローバル QSS テンプレ
`resources/style/win95.qss` の出発点:

```css
* {
    font-family: "MS UI Gothic", "MS Gothic", "sans-serif";
    font-size: 9pt;
    color: #000000;
}

QMainWindow, QDialog, QWidget {
    background-color: #C0C0C0;
}

QPushButton {
    background-color: #C0C0C0;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    padding: 2px 8px;
    min-width: 60px;
    min-height: 22px;
}
QPushButton:pressed {
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
}
QPushButton:disabled {
    color: #808080;
}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: #FFFFFF;
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    padding: 1px 3px;
}

QMenuBar {
    background-color: #C0C0C0;
    border-bottom: 1px solid #808080;
}
QMenuBar::item {
    padding: 2px 8px;
}
QMenuBar::item:selected {
    background-color: #000080;
    color: #FFFFFF;
}

QMenu {
    background-color: #C0C0C0;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
}
QMenu::item:selected {
    background-color: #000080;
    color: #FFFFFF;
}

QStatusBar {
    background-color: #C0C0C0;
    border-top: 1px solid #808080;
}

QGroupBox {
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    margin-top: 8px;
    padding-top: 4px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 6px;
    padding: 0 3px;
    background-color: #C0C0C0;
}
```

### 2. 適用方法
```python
# src/main.py
from PySide6.QtWidgets import QApplication
from pathlib import Path

app = QApplication([])
qss_path = Path(__file__).parent.parent / "resources" / "style" / "win95.qss"
app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
```

### 3. Qt の組み込みスタイルを「Windows」に固定
```python
app.setStyle("Windows")   # "Fusion" や "windowsvista" を避ける
```
これだけでもかなり Win95 寄りになる (QSS と組み合わせ)。

### 4. アイコン
- Win95 風 16x16 / 24x24 ピクセル絵風 (滑らかにしない、anti-alias 弱め)
- フリー素材: https://win98icons.alexmeub.com/ などから流用検討
- 自前で描くなら GIMP で `index 16 色` モード推奨

## 高情報密度の作り方

### 余白を絞る
- `QVBoxLayout / QHBoxLayout` の `setContentsMargins(2, 2, 2, 2)` 基本
- `setSpacing(2)` 基本
- Qt Designer 既定の 6px は広すぎる、必ず縮める

### ツールバー / メニュー / ステータスバーを必ず持つ
- 業務アプリ感は「上にメニュー / その下にツールバー / 下にステータス」の 3 段構成から
- ツールバーアイコンは 16x16 + 24x24 の混在 OK、ただしテーマは統一
- ステータスバーには常に情報を表示 (空にしない)

### グリッド配置
- 並ぶフォーム要素は `QGridLayout` で揃える
- ラベル右寄せ + 入力左寄せでカラム整列

### キーボード操作を必ず想定
- Alt+key でメニューアクセス (`&File` 表記、Qt が自動的に F に下線)
- Tab 順を意識
- ショートカット (`Ctrl+S` 等) は QAction で

## アンチパターン (やってはいけない)

- ❌ `border-radius: 8px` 等の角丸
- ❌ `box-shadow` 系の影
- ❌ Material 風の高さ表現 (elevation)
- ❌ Hamburger menu / Drawer / FAB
- ❌ アイコンだけのボタン (テキストラベル併記が業務向き)
- ❌ アニメーション (Win95 にはほぼ無い、必要なら一瞬で)
- ❌ 半透明 / blur
- ❌ ダークモード (業務 PC は明るい蛍光灯下で使う前提)

## k-pdf3 (Electron + 98.css) からの教訓
- 98.css は `<input type=radio>` を `opacity:0; position:fixed` で隠して `::before` で絵を描いている
- PySide6 + QSS には同じ罠は無いが、QSS で擬似要素は限定的 → ネイティブ widget の見た目を尊重して subclass で塗り直すパターンが安全
- 「label に overflow: hidden を付けたら絵が消える」みたいな事故は QSS でも起こりうる、QSS が効かない時は `objectName` 経由で `#id` セレクタを使う
