# UI刷新で保護する契約（Stage 0）

## 変更禁止の中核契約

1. `CODEX_MASTER_SPEC.md`のハード制約を減点や警告へ変更しない。
2. OR-Toolsの候補生成、最大2名、1対1、優先度5、資格、availability、集団授業重複、
   lock、連続上限、空きコマ禁止、必要回数、辞書式目的、中断時incumbentの扱いを変更しない。
3. DnDのgreen/yellow/redは既存`ScheduleEditService` / `manual_edit.py`の結果だけを表示し、
   QML独自判定を追加しない。redを保存する経路を作らない。
4. lock、Undo/Redo、fingerprint競合検出、AuditLog、自動保存、checkpointを迂回しない。
5. 出力は最新DB再読込みと独立validatorを通し、原子的保存・上書き確認を維持する。
6. `.jukuschedule`、SQLite、Alembic revision chain、既存データ、backup/recovery、
   アンケート原本BLOBの互換性を維持する。
7. QMLからSQLAlchemy、Repository、OR-Tools、openpyxl、PDF rendererを直接呼ばない。
8. 外部通信、telemetry、cloud保存、個人情報uploadを追加しない。

## UIから保持する操作

- 新規・既存・最近使用したproject、別名保存、複製、backup、復元、dirty確認
- 生徒・講師・科目・コマ・開校日・受講希望・資格の全既存CRUD
- master Excelの出力、preview、transaction反映
- 生徒・講師アンケートのxlsx/CSV、encoding、sheet、mapping、diff、削除確認、原本差替え
- 集団授業のカレンダー登録・削除とExcel一括取込み
- 最適化preset、実行、中止、status、目的内訳、未配置診断
- 時間割TableView、日付移動、filter、DnD、lock、Undo/Redo、詳細編集、差分、履歴、再最適化
- Excel/PDF/CSV、対象filter、設定保存、PDF preview、上書き確認

## 変更可能な範囲

- 色、余白、文字サイズ、カード、ボタン、badge、inline message、empty state
- サイドバーの視覚的グルーピングと表示名（既存9項目の到達先は保持）
- 同じViewModel操作へ到達する画面レイアウト、段階表示、詳細設定の折畳み
- 初期名簿ではExcel一括登録を主導線、日常運用では個別追加を主導線とする案内
- 既存validation結果を用いた状態・件数・ジャンプ導線

## 受入安全弁

- 各Stage後に関連契約test、全QML lint、offscreen smokeを実行する。
- Stage 6でRuff、format、mypy、全pytest、migration head、起動を再確認する。
- failing testを削除・skip・xfail・弱体化しない。
- UI都合だけのmigrationや業務ロジック変更は行わない。
- 安全に実装できない項目だけを`BLOCKED`として記録し、他Stageは継続する。
