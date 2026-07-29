# ADR 0002: SQLite、SQLAlchemy 2、Alembic を採用する

- 状態: 採用
- 日付: 2026-07-28
- 対象: Phase 0 / Phase 1

## コンテキスト

アプリはオフラインで動作し、講習プロジェクト、マスター、希望、Assignment、履歴、警告をローカル保存する。利用者へ DB サーバーの導入を要求できない。一方で、将来の schema 変更、バックアップ、過年度データの再読込みを安全に扱う必要がある。

## 決定

- DB に SQLite を採用する。
- Python の永続化境界に SQLAlchemy 2 系を採用し、2 系の API と型付き mapping を使用する。
- schema migration に Alembic を採用する。
- 初回起動は空 SQLite DB へ Alembic の `upgrade head` を適用する処理として扱う。
- DB の既定場所を `%LOCALAPPDATA%\SummerScheduler\data\summer_scheduler.db` とする。
- SQLite の外部キー検証を接続ごとに有効化する。
- 一時的なロック競合には 5,000 ms の `busy_timeout` を設定する。
- SQLAlchemy Session を QML、ViewModel、Domain、最適化モデルへ渡さない。

Alembic の環境と revision は `src/summer_scheduler/infrastructure/db/alembic/` に置き、配布 package data に含める。アプリは `migration_runner.py` を通して packaged resource の場所を解決する。

## 根拠

- SQLite はサーバー不要で、完全ローカル・オフライン要件に合う。
- SQLAlchemy 2 は Repository 実装、transaction、型付き model を整理できる。
- Alembic により、既存利用者の DB を再作成せず段階的に更新できる。
- DB と最適化 DTO を分ければ、schema 変更と CP-SAT model の変更を独立してテストできる。

## 影響

良い影響:

- 初回起動と将来 upgrade を同じ経路で検証できる。
- SQLite ファイルをバックアップ・移動する将来機能へつなげられる。
- migration 履歴をコードレビューできる。

注意点:

- SQLite はネットワーク共有や複数人同時編集を前提としない。本アプリの初期版も複数人同時編集を対象外とする。
- OneDrive 同期中の直接更新はロックや sidecar file の問題を起こし得るため、稼働 DB は既定で `%LOCALAPPDATA%` に置く。
- journal mode とバックアップ方式は実測して決める。OneDrive 上で WAL を無条件に有効化しない。`busy_timeout` の値を変更する場合も、UI の応答と保存失敗の明示を合わせて検証する。
- migration 前バックアップ、途中失敗時の復旧、`.jukuschedule` 形式は Phase 2 以降で設計を追加する。
- `Base.metadata.create_all()` はテスト用の限定用途を除き、既存 DB 更新の代替にしない。

## 採用しなかった案

- 生の `sqlite3` だけを利用: 小規模な起動確認には足りるが、関係の多い将来 schema、Repository、migration の保守性が下がる。
- PostgreSQL 等のサーバー DB: DB サーバーが必要になり、完全ローカル配布の要件に反する。
- JSON / YAML だけで全業務データを保存: 関係整合性、transaction、検索、migration、監査履歴を安全に扱いにくい。
- 起動時の `create_all()` だけ: 既存列の変更やデータ移行を管理できない。

## migration の規則

- schema 変更には必ず revision を付ける。
- 自動生成した revision をそのまま採用せず、制約、index、既存データ移行をレビューする。
- 空 DB と前 revision から `head` への upgrade をテストする。
- migration 中のログに個人データの値を出さない。
- downgrade が安全でない場合は、その理由とバックアップからの復旧方法を revision または運用文書へ記録する。
