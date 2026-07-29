# Contributing

IssueやPull Requestを歓迎します。変更前に、機能仕様は
[`docs/specification.md`](docs/specification.md)、実装構造は
[`docs/developer_guide.md`](docs/developer_guide.md)、主要な設計判断は
[`docs/adr/`](docs/adr/)を確認してください。

## 開発環境

Windows、Python 3.12、PowerShellを基準とします。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 変更前の品質確認

```powershell
ruff check .
ruff format --check .
mypy src tests
pytest
```

時間割のハード制約をソフトな減点へ変更しないでください。制約または最適化目的を
変更する場合は、関連するscenario testとADRも更新してください。既存テストを
skip、xfail、削除することで失敗を隠してはいけません。

## データと権利

実在する生徒、講師、校舎、時間割、DB、ログ、Excel、PDF、画面キャプチャを、
リポジトリ、Issue、Pull Request、CI artifactへ追加しないでください。テストデータは
すべて架空にします。

Contributionは、このリポジトリの`LICENSE`に定めるGPL-3.0-onlyで配布できる内容に
限ります。第三者のコードや画像を追加する場合は、出典とライセンスを明記してください。
