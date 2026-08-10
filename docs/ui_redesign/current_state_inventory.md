# 現行実装インベントリ（Stage 0）

- 監査日: 2026-08-11
- 監査基準commit: `c24c937`（`main` / `v1.0.4`）
- Python: 3.12系
- UI: PySide6 / Qt Quick Controls / QML
- DB: SQLite / SQLAlchemy 2 / Alembic
- Alembic head: `20260807_0007`

## 起動・構成

`python -m summer_scheduler` が正規の入口である。`app.py`でQMLへ公開されるのは
`appViewModel`、`workspaceViewModel`、`phase3ViewModel`、
`optimizationViewModel`、`scheduleEditorViewModel`、`outputViewModel`である。
依存方向は `QML → ViewModel → Application → Domain / port ← Infrastructure` を維持している。

## 現行画面と接続済み機能

| 画面 | QML | 既存の実処理 |
|---|---|---|
| ホーム | `ProjectHomePage.qml` | 新規作成、既存・最近使ったプロジェクト、保存・複製・backup・復元、4段階フロー |
| 生徒 | `StudentPage.qml` | 検索・並替え、CRUD、使用停止、受講希望、通常担当・希望講師、1対1、連続・空きコマ上書き |
| 講師 | `TeacherPage.qml` | 検索・並替え、CRUD、使用停止、指導可能科目、学校段階filter、一括選択・copy |
| アンケート | `AvailabilityImportPage.qml` | xlsx/CSV調査、encoding/sheet、列mapping、preview、diff、validation、transaction反映、原本内包 |
| 集団授業 | `GroupLessonPage.qml` | カレンダー入力、削除、Excel template、preview/diff/validation/transaction反映 |
| 最適化 | `OptimizationPage.qml` | 30/120/600秒、協調中止、進捗、診断、検証済み結果保存 |
| 時間割編集 | `ScheduleEditorPage.qml` | 仮想化TableView、DnD事前検証、lock、Undo/Redo、AuditLog、差分、再最適化checkpoint |
| 未配置・警告 | `ValidationIssuesPage.qml` | 全体入力検証、severity/filter、匿名sample作成 |
| 出力 | `OutputPage.qml` | Excel/PDF/CSV、対象選択、設定保存、上書き確認、Qt PDF preview |
| 設定 | `SettingsPage.qml` | プロジェクト、コマ、開校日、科目、master Excel |

## 保存形式とDB

`.jukuschedule`は1ファイル1 CourseProjectのSQLite DBである。現行headの主要tableは、
`students`、`teachers`、`subjects`、`teacher_qualifications`、`lesson_requests`、
`student_availabilities`、`teacher_availabilities`、`group_lessons`、`assignments`、
`optimization_runs`、`audit_logs`、`validation_issues`、`output_settings`、
`import_source_snapshots`である。

UI刷新ではmigrationを追加せず、既存table、column、外部キー、check constraint、
revision chain、初回作成・旧版upgrade・backup-before-migrationを変更しない。

## 最適化・編集・出力の正本

- OR-Tools境界: `optimization/`と`OptimizationRunService`
- ハード制約: `hard_constraints.py`と独立`result_validation.py`
- 手動編集判定: `manual_edit.py`（green / yellow / red）
- 保存・lock・Undo/Redo・AuditLog: `ScheduleEditService`
- 出力直前検証: `OutputService`
- Excel/PDF共通中間表現: `reporting/LayoutDocument`
- 姓の一意表示: `reporting/person_names.py`

QMLに同等ロジックを複製せず、既存ViewModel slotとPropertyを利用する。

## 公開QML/ViewModel契約

主要Propertyは、workspaceのproject/people/master/dirty/recovery、phase3のsource/mapping/
diff/issues/group/validation、schedule editorのgrid/date/unassigned/selected/dropPreview/
history/diff/lock/undo、outputのreport/format/destination/settings/selection/previewである。

主要slotは、project lifecycle、master CRUD、master Excel preview/apply、survey
inspect/validate/apply、group calendar create/delete/import、optimization run/cancel、
schedule preview/drop/edit/lock/undo/redo/checkpoint、output generate/preview/settings saveである。
名称・引数・戻り値をStage 1～6で破壊しない。

## ベースライン試験

2026-08-11、UI変更前に以下を実行した。

| コマンド | 結果 |
|---|---|
| `.venv\\Scripts\\python.exe -m ruff check .` | PASS |
| `.venv\\Scripts\\python.exe -m ruff format --check .` | PASS（223 files） |
| `.venv\\Scripts\\python.exe -m mypy src tests` | PASS（166 source files） |
| `.venv\\Scripts\\python.exe -m pytest -q` | PASS（423 tests、133.52秒） |
| `.venv\\Scripts\\pyside6-qmllint.exe <全QML>` | PASS |
| `python -m summer_scheduler --smoke-test`（offscreen、software） | PASS（exit 0） |

現行画面の既存参考snapshotは `docs/images/main-window-home.png` にある。これはUI回帰の
構造比較用であり、pixel一致を受入条件にしない。
