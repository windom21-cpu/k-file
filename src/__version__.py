"""k-file の単一バージョン定義。

タグ切る時はここを更新 → commit → `v{VERSION}` のタグを切る → CI が
GitHub Release を作成 + zip upload。

例: β を切る時は VERSION = "0.1.0-beta.1" にしてから `git tag v0.1.0-beta.1`。
"""

VERSION = "0.1.0-beta.3"
