# 開発者ガイド

## 1. この文書の位置づけ

このガイドはリリース候補`1.0.0-rc.4`時点の実装を説明する。公開版の機能仕様と
ハード制約は[`specification.md`](specification.md)、初期設計は
[`phase0_design.md`](phase0_design.md)、主要な判断理由は[`adr/`](adr/)を参照する。
このガイドは、仕様に定めたハード制約やデータ安全性要件を緩和しない。

Phase 1の起動、設定、ログ、DB接続・migration、QML画面シェル、品質基盤に加え、
Phase 2の`.jukuschedule`、マスターCRUD、`master_data.xlsx`に加え、Phase 3では
日時アンケート、集団授業、入力検証、Phase 4ではORM非依存DTO、候補生成、CP-SAT
ハード制約、辞書式最適化、中断、診断、履歴保存、Phase 5では時間割グリッド、
ドラッグ前検証、ロック、Undo / Redo、差分、監査、自動保存、ロック以外の全体
再最適化、Phase 6では共通帳票レイアウト、Excel / PDF / CSV、印刷プレビュー、
生徒別・講師別・未配置／警告帳票、出力設定保存、Phase 7では自動backup世代管理、
破損検出と原子的復元、版表示、Windows standalone / portable / installer / checksumの
配布境界、性能・受入・運用文書を実装した。

## 2. 前提環境

- Windows 10 / 11 x64
- Python 3.12 系
- PowerShell
- Git

開発とsource testにはPython 3.12を使用する。portable / installerは利用者側へ
Python、Node.js、Qt SDKを要求しないstandalone構成とする。ただしclean Windowsでの
最終受入状態は[`acceptance_test_phase7.md`](acceptance_test_phase7.md)を参照する。

## 3. 開発環境の準備

PowerShell でリポジトリ直下から実行する。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

PowerShell の実行ポリシーで仮想環境を有効化できない場合は、アクティベートせず `.\.venv\Scripts\python.exe` を各コマンドの `python` の代わりに使える。

## 4. 起動

```powershell
python -m summer_scheduler
```

起動すると、設定とローカル保存先を解決し、ログを初期化し、アプリ管理SQLiteへ
migrationを適用してからQMLを読み込む。日本語タイトルのメインウィンドウ、9項目の
サイドバー、プロジェクト選択を兼ねたホームが表示される。プロジェクトを作成または
開くと、その`.jukuschedule`へも必要なmigrationを適用し、Phase 6までの業務画面と
Phase 7の自動backup／復旧候補を利用できる。

QML の表示だけを確認する場合も、QML ファイルを単独起動せず Python のエントリーポイントを使う。これにより、設定・ログ・DB・ViewModel が本番と同じ順序で初期化される。

## 5. ソース構成

主要ファイルの責務は次のとおりである。

| パス | 責務 |
|---|---|
| `src/summer_scheduler/__main__.py` | `python -m summer_scheduler` の入口 |
| `src/summer_scheduler/app.py` | Qt アプリケーションの生成、QML 読込み、終了コード |
| `src/summer_scheduler/bootstrap.py` | 設定、ログ、DB 等の起動時組立て |
| `src/summer_scheduler/shared/settings.py` | YAML 設定の読込み、検証、パス解決 |
| `src/summer_scheduler/resources/default_settings.yaml` | パッケージに含める読取り専用の既定設定 |
| `src/summer_scheduler/infrastructure/logging/configuration.py` | ローカルログ設定 |
| `src/summer_scheduler/infrastructure/db/base.py` | SQLAlchemy declarative base |
| `src/summer_scheduler/infrastructure/db/database.py` | engine / session と SQLite 接続 |
| `src/summer_scheduler/infrastructure/db/migration_runner.py` | 埋込み Alembic 環境の実行 |
| `src/summer_scheduler/domain/defaults.py` | 既定5コマと23科目 |
| `src/summer_scheduler/domain/validation.py` | UIとDBに依存しないPhase 2入力検証 |
| `src/summer_scheduler/domain/time_ranges.py` | 任意時刻を半開区間で比較する共通規則 |
| `src/summer_scheduler/application/project_service.py` | `.jukuschedule`の作成・読込み・コピー・整合性検査・世代backup・安全な復元 |
| `src/summer_scheduler/application/master_data_service.py` | マスターCRUDとtransaction境界 |
| `src/summer_scheduler/application/availability_import_service.py` | 生徒・講師availabilityの調査、検証、差分、反映 |
| `src/summer_scheduler/application/group_lesson_service.py` | 集団授業の検証、差分、反映 |
| `src/summer_scheduler/application/project_validation_service.py` | 保存済みプロジェクト全体の入力検証 |
| `src/summer_scheduler/application/optimization_input_builder.py` | ORM行を不変な最適化DTOへコピー |
| `src/summer_scheduler/application/optimization_run_service.py` | 最適化prepare、fingerprint、結果検証、履歴とAssignmentのtransaction保存 |
| `src/summer_scheduler/application/phase5_dto.py` | 時間割ボード、preview、差分、監査、再最適化確認の不変DTO |
| `src/summer_scheduler/application/schedule_board_query.py` | ORMを保持しない時間割編集用読取りモデルの組立て |
| `src/summer_scheduler/application/schedule_edit_service.py` | 手動編集の再検証、自動保存、監査、Undo / Redo、手動保存点、checkpoint |
| `src/summer_scheduler/application/phase6_dto.py` | 出力画面、生成結果、選択肢の不変DTO |
| `src/summer_scheduler/application/output_service.py` | 最新DBの再検証、帳票組立て、Excel / PDF / CSV出力のユースケース |
| `src/summer_scheduler/application/sample_project_service.py` | 架空名だけの匿名サンプル生成 |
| `src/summer_scheduler/application/dto.py` | ApplicationとViewModel間の表示用DTO |
| `src/summer_scheduler/infrastructure/db/models.py` | アプリ状態とPhase 2～6業務モデル |
| `src/summer_scheduler/infrastructure/db/alembic/` | Alembic 設定、環境、revision |
| `src/summer_scheduler/infrastructure/repositories/master_repository.py` | SQLAlchemyによるマスターRepository |
| `src/summer_scheduler/infrastructure/repositories/phase4_repository.py` | AssignmentとOptimizationRunの永続化 |
| `src/summer_scheduler/infrastructure/repositories/phase5_repository.py` | Assignment snapshotの作成・復元とAuditLog永続化 |
| `src/summer_scheduler/infrastructure/repositories/output_repository.py` | 出力snapshotの一括読取りとプロジェクト出力設定の永続化 |
| `src/summer_scheduler/infrastructure/excel/` | 5シートのschema、出力、読取り、検証、反映 |
| `src/summer_scheduler/infrastructure/importing/` | Phase 3のxlsx / CSV調査、mapping、template、diff |
| `src/summer_scheduler/infrastructure/exporting/` | 原子的保存、openpyxl Excel、Qt PDF、HTML、18列CSV renderer |
| `src/summer_scheduler/reporting/` | DB・QML非依存の出力snapshot、設定、共通レイアウト、帳票builder |
| `src/summer_scheduler/optimization/dto.py` | ORM、UI、solverから独立した不変DTO |
| `src/summer_scheduler/optimization/candidates.py` | 疎な候補と候補除外理由の生成 |
| `src/summer_scheduler/optimization/hard_constraints.py` | CP-SATハード制約 |
| `src/summer_scheduler/optimization/objectives.py` | 辞書式目的の整数式 |
| `src/summer_scheduler/optimization/solver.py` | 単一deadline、段階Solve、snapshot、中断 |
| `src/summer_scheduler/optimization/diagnostics.py` | 未配置理由の組立て |
| `src/summer_scheduler/optimization/result_validation.py` | solverとは独立した保存前ハード制約検証 |
| `src/summer_scheduler/optimization/manual_edit.py` | UI・ORM・solver非依存の手動編集previewとソフト評価差 |
| `src/summer_scheduler/optimization/schedule_diff.py` | session単位の配置・日時・講師・未配置・pairing差分 |
| `src/summer_scheduler/optimization/serialization.py` | version付き最適化JSON snapshot codec |
| `src/summer_scheduler/ui/viewmodels/app_view_model.py` | QML へ公開するアプリ状態 |
| `src/summer_scheduler/ui/viewmodels/workspace_view_model.py` | プロジェクトとPhase 2画面の状態・操作 |
| `src/summer_scheduler/ui/viewmodels/phase3_view_model.py` | Phase 3画面の状態・操作 |
| `src/summer_scheduler/ui/viewmodels/optimization_view_model.py` | QThread workerとPhase 4表示状態 |
| `src/summer_scheduler/ui/viewmodels/schedule_editor_view_model.py` | Phase 5編集状態、`QAbstractTableModel`、操作slot |
| `src/summer_scheduler/ui/viewmodels/output_view_model.py` | Phase 6のdraft設定、対象選択、出力worker、一時PDF管理 |
| `src/summer_scheduler/ui/qml/Main.qml` | ApplicationWindow、ナビゲーション、ページ切替 |
| `src/summer_scheduler/ui/qml/Sidebar.qml` | 9 項目のサイドバー |
| `src/summer_scheduler/ui/qml/ProjectHomePage.qml` | プロジェクト選択、最近使用した一覧、概要 |
| `src/summer_scheduler/ui/qml/StudentPage.qml` | 生徒とLessonRequestのCRUD |
| `src/summer_scheduler/ui/qml/TeacherPage.qml` | 講師と指導可能科目のCRUD |
| `src/summer_scheduler/ui/qml/SettingsPage.qml` | プロジェクト、コマ、開校日、科目、Excelの入口 |
| `src/summer_scheduler/ui/qml/*SettingsTab.qml` | Phase 2設定の各タブ |
| `src/summer_scheduler/ui/qml/AvailabilityImportPage.qml` | アンケート取込みウィザード |
| `src/summer_scheduler/ui/qml/GroupLessonPage.qml` | 集団授業一覧・取込み |
| `src/summer_scheduler/ui/qml/ValidationIssuesPage.qml` | エラー・警告・情報の表示 |
| `src/summer_scheduler/ui/qml/OptimizationPage.qml` | Phase 4の実行、経過、結果、診断の簡易画面 |
| `src/summer_scheduler/ui/qml/ScheduleEditorPage.qml` | Phase 5のTableView、カード、DnD、詳細、未配置、差分、履歴 |
| `src/summer_scheduler/ui/qml/OutputPage.qml` | Phase 6の帳票・設定・対象選択・PDF印刷プレビュー |
| `src/summer_scheduler/ui/qml/PlaceholderPage.qml` | 未接続ページに対する安全なfallback表示 |
| `packaging/pysidedeploy.spec` | pyside6-deploy / Nuitka standalone build設定 |
| `packaging/requirements-release.txt` | Windows x64 release buildの固定依存 |
| `scripts/build_windows.ps1` | standalone tree、portable directory / ZIPの生成 |
| `scripts/build_installer.ps1` | 同じstandalone treeからInno Setup installerを生成 |
| `scripts/package_release.py` | version、配布内容、決定的ZIP、SHA-256の検証 |
| `scripts/collect_licenses.py` | release環境のruntime依存と全文licenseの収集 |
| `scripts/verify_authenticode.ps1` | 署名前の境界と署名後の署名者・timestamp検証 |
| `installer/SummerCourseScheduler.iss` | 利用者単位install、shortcut、data保持方針 |

SignPath Foundation申請の信頼境界、担当者、承認後に登録するGitHub Environment /
secret / variablesは[`code_signing_policy.md`](code_signing_policy.md)と
[`signpath_application.md`](signpath_application.md)を正本とする。未承認のIDを仮設定
したworkflowを有効化せず、署名後にsmokeとchecksumをやり直す。

後続Phaseの追加先は次のように分離する。

- `domain/`: UIやSQLAlchemyに依存しない値、既定値、検証規則
- `application/`: ユースケースを実行するApplication ServiceとDTO
- `infrastructure/repositories/`: Repository interface の SQLAlchemy 実装
- `optimization/`: ORM と独立した DTO、候補生成、制約、目的、solver、診断
- `infrastructure/excel/`: Phase 2のマスターExcel adapter
- `infrastructure/importing/`: Phase 3のアンケート・集団授業Excel / CSV adapter
- `reporting/`: Phase 6の出力snapshot、純粋な帳票builder、共通`LayoutDocument`
- `infrastructure/exporting/`: Phase 6のExcel / PDF / CSV rendererと原子的保存adapter
- `ui/viewmodels/`: Application Service を呼び出し、QML 用状態へ変換する ViewModel

目標とする依存方向は
`QML → ViewModel → Application → Domain / port ← Infrastructure`である。
DomainからQML、PySide6、SQLAlchemy、OR-Toolsをimportしない。

Phase 2 / 3のApplication Serviceは、プロジェクト単位transactionを一か所で管理する
ため、現時点では具体的な`MasterRepository`と一部ORM型を直接使用している。
QMLからDBを直接操作せずDomainをInfrastructure非依存に保つ境界は満たすが、完全な
Repository port抽出には至っていない。Phase 4の最適化層にはこの依存を持ち込まず、
Application ServiceがORMを`frozen` DTOへコピーした後はSessionを閉じる。既存
Application Serviceのport抽出は動作を保った
段階的な保守課題とし、仕様上の理由なく全面書換えしない。

## 6. 起動シーケンス

起動処理は概ね次の順番で行う。

1. 内蔵既定設定を読み込む。
2. 利用者設定が存在すれば読み込み、設定を上書きする。
3. 指定された環境変数があれば、保存先に関する設定をさらに上書きする。
4. 必要なローカルディレクトリを作る。
5. ローカルログを設定する。
6. DB engine を作成し、Alembic を `head` まで適用する。
7. DB 接続状態を ViewModel 用の状態へ変換する。
8. `QGuiApplication` と `QQmlApplicationEngine` を生成する。
9. アプリ管理DBを使う`ProjectService`と、プロジェクトを開いた後に利用する
   `MasterDataService` / Excel adapter / `OptimizationRunService` /
   `ScheduleEditService` / `OutputService`を組み立てる。
10. `AppViewModel`を`appViewModel`、`WorkspaceViewModel`を`workspaceViewModel`、
    `Phase3ViewModel`を`phase3ViewModel`、`OptimizationViewModel`を
    `optimizationViewModel`、`ScheduleEditorViewModel`を
    `scheduleEditorViewModel`、`OutputViewModel`を`outputViewModel`という
    context propertyとして公開する。
11. project open後の自動backup timerを開始し、復旧候補をViewModelへ公開する。
12. `Main.qml` を読み込み、event loop を開始する。

初期化失敗を握り潰して「正常起動」に見せてはならない。技術的な詳細はログへ残し、利用者には日本語で失敗箇所とログ保存先を案内できる構造を保つ。

## 7. 設定

設定は次の順で重ねる。

1. パッケージ内の `src/summer_scheduler/resources/default_settings.yaml`
2. 任意の利用者設定 `%LOCALAPPDATA%\SummerScheduler\config.yaml`
3. 保存先を明示する環境変数

利用者設定が存在しないことは正常である。内蔵設定ファイルは配布物の一部であり、実行時に書き換えない。明示指定した設定ファイルが存在しない場合や、利用する設定値の型・値が不正な場合は `SettingsError` とする。

Phase 6でも利用できる起動時指定は次のとおりである。

| 指定 | 意味 |
|---|---|
| `python -m summer_scheduler --config <path>` | 読み込む利用者 YAML を明示 |
| `SUMMER_SCHEDULER_CONFIG` | 利用者 YAML のパス |
| `SUMMER_SCHEDULER_DATA_DIR` | DB の既定ディレクトリ |
| `SUMMER_SCHEDULER_DATABASE_PATH` | DB ファイルを直接指定 |
| `SUMMER_SCHEDULER_LOG_DIR` | ログディレクトリ |

相対パスは選択された設定ファイルの親ディレクトリを基準に解決する。テストや CI ではこれらを一時ディレクトリへ差し替え、実運用データに触れない。

設定値を追加する場合は次を同じ変更で行う。

1. 設定を利用する層を確認する。QML から YAML を直接読まない。
2. `default_settings.yaml` に安全な既定値を追加する。
3. `settings.py` の型と検証を更新する。
4. 既定値、上書き、欠落、不正値、日本語パスのテストを追加する。
5. 利用者が変更する項目なら README または将来の設定画面へ説明を追加する。

最適化の高速／標準／高品質は既定で30／120／600秒であり、乱数seed、search worker数、
段階内スコアとともに`optimization`設定から`OptimizationSettings` DTOへ注入する。
solverコードへ設定値を直書きしない。既定では再現性を優先してsearch worker数を1に
している。

`output`設定は、新しいプロジェクトでまだ出力設定を保存していない場合の既定値である。
用紙、向き、表示項目、1ページ当たり日数、講師列数、文字サイズ、余白、ファイル名規則、
既定出力先、生徒別改ページ、CSV BOM、色と文字マーカーを型付きで読み込む。相対的な
既定出力先は選択したYAMLの親ディレクトリを基準に解決する。

プロジェクトで「出力設定を保存」した後は、`.jukuschedule`内の`output_settings`を
正本とし、後からYAMLを変更して既存プロジェクトの判断を暗黙に変えない。ロゴだけは
校舎単位の`Campus.logo_path_optional`を正本とする。ロゴファイル自体をDBへ埋め込まず、
対応形式、存在、サイズをPDF生成時にも検査する。

`backup.automatic_interval_minutes`と`backup.automatic_generations`はどちらも正の整数で、
既定値は5分、5世代である。project open直後にも自動backupを作る。timerとQMLは
`WorkspaceViewModel`を呼ぶだけで、SQLite backup、世代削除、復元検証を直接扱わない。

## 8. ローカルデータ、プロジェクト、ログ

アプリ自身の既定パスは次のとおりである。

| 種別 | 既定パス |
|---|---|
| アプリ管理SQLite DB | `%LOCALAPPDATA%\SummerScheduler\data\summer_scheduler.db` |
| ログ | `%LOCALAPPDATA%\SummerScheduler\logs\summer_scheduler.log` |
| 自動・migration前・復元前snapshot | `%LOCALAPPDATA%\SummerScheduler\backups\` |
| 任意の利用者設定 | `%LOCALAPPDATA%\SummerScheduler\config.yaml` |

アプリ管理DBは`application_metadata`と最近使用したプロジェクト等のアプリ状態だけを
保持する。生徒、講師、科目、受講希望等は、利用者が保存先を選んだ
`.jukuschedule`へ保存する。1ファイルは1つのSQLite DBかつ1つのCourseProjectで
ある。詳細は
[`ADR 0005`](adr/0005-project-file-and-master-data-lifecycle.md)を参照する。

パスは文字列連結ではなく`platformdirs`、`pathlib.Path`、Qtの`QUrl`変換を通じて
扱う。`file:///C:/...`をそのまま`Path`へ渡さず、Windowsのローカルパスへ正規化する。
リポジトリ内を実データの既定保存先にしない。

ログには、起動・終了、設定読込みの成否、migration、重大な例外など運用に必要な
情報だけを記録する。生徒名、講師名、アンケート内容などの個人情報を必要以上に
残さない。Phase 4はOR-Toolsの検索ログを標準出力へ出さず、worker例外も値ではなく
例外型だけを記録する。一般ログの隣の`optimization-runs`ディレクトリに、runごとの
UTF-8 JSON Linesログを排他的に作成し、OptimizationRunの`log_path_optional`へその
固有パスを記録する。内容はrun ID、preset、状態、solver status、件数、経過時間に
限定し、solverへパスやログwriterを持ち込まない。
入力・結果snapshotは個人情報を含み得るため、プロジェクトDBの外へ出さない。

Phase 5の手動変更履歴は技術ログではなくプロジェクトDBの`AuditLog`へ保存する。
変更理由、操作種別、対象session、変更前後、手動／Undo／Redo、operation IDを保持する。
画面の履歴には業務上必要な値が表示されるため、スクリーンショットやDB snapshotを
外部へ添付しない。技術ログへAssignment snapshotや氏名を複製しない。

Phase 6の出力と印刷プレビューにも氏名等が含まれ得る。保存先は利用者が選んだローカル
ディレクトリとし、外部へ送信しない。一時PDFはOSの一時ディレクトリに作り、preview
切替と終了時に削除する。出力本文、CSV行、ロゴ画像を技術ログへ複製しない。

DB、`.jukuschedule`、ログ、利用者設定、入力・出力・バックアップはGitの管理対象外
である。テストには一時ディレクトリと架空データを用いる。

### 8.1 プロジェクトファイル操作

- 新規作成は目的ファイルと同じディレクトリの一時SQLiteでmigrationとseedを完了し、
  `os.replace`する。
- 別名保存、複製、バックアップはSQLite backup APIでsnapshotを一時ファイルへ
  作成し、成功後に置き換える。
- 別名保存だけが現在の接続先を新ファイルへ切り替える。
- 古いrevisionを開く場合はmigration前に自動snapshotを作る。snapshot作成失敗時に
  migrationを続行しない。
- open時はSQLite形式、`alembic_version`、`course_projects`、プロジェクト件数を
  検証し、migration前に`PRAGMA integrity_check`と書込み可否を確認する。
- 保存先がロックされている、空き容量がない、同期競合している場合は日本語エラーを
  返し、元ファイルを開いたままにする。
- open直後と設定間隔ごとにSQLite backup APIで自動snapshotを作る。元path由来の
  SHA-256 keyでprojectごとに識別し、`backup.automatic_generations`だけ残す。
- open中pathは`recovery-session.json`へ原子的に記録し、正常close時だけ削除する。
  残存markerまたはopen失敗pathから復旧候補を走査する。path値を技術logへ書かない。
- 復元は選択backupを一時SQLiteへcopyし、整合性、migration、1 CourseProject不変条件を
  検証する。既存復元先の`pre_restore` snapshotを作れた場合だけ`os.replace`する。
  破損した復元先は自動修復せず、証跡保全のbyte copyを作る。
- QMLは候補pathと利用者操作だけを`WorkspaceViewModel`へ渡す。整合性検査、世代削除、
  復元、例外分類は`ProjectService`から下で完結する。詳細は
  [`ADR 0009`](adr/0009-project-backup-and-recovery-safety.md)を参照する。

## 9. SQLAlchemy と Alembic

### 9.1 接続境界

- SQLAlchemy 2 系の API と型付き ORM を使用する。
- Session を QML や Domain へ渡さない。
- transactionの開始・commit・rollbackはApplication Serviceまたは明示した
  Unit of Work境界で完結させ、Repositoryはflushまでを担当する。
- SQLite の外部キー制約を接続ごとに有効化する。
- 接続時に 5,000 ms の `busy_timeout` を設定し、一時的なファイルロックを無限待機にしない。
- engine / session の生成は `database.py` に集約し、画面ごとに作らない。

### 9.2 migration 方針

アプリ起動時は`migration_runner.py`が、パッケージ内の
`infrastructure/db/alembic/`を使ってアプリ管理DBを最新revisionまで更新する。
プロジェクト作成時とopen時も、同じrunnerで`.jukuschedule`をheadへ更新する。
初回作成は空DBに対するmigrationとして扱う。

スキーマ変更時は次を守る。

1. SQLAlchemy metadata を更新する。
2. Alembic revision を作成し、生成内容を必ずレビューする。
3. upgrade と、必要な場合は downgrade / 復旧方針を記述する。
4. 空 DB と一つ前の revision からの upgrade をテストする。
5. `.jukuschedule`の旧revisionを開く前にsnapshotを作る。
6. 日本語データ、既存データ、失敗時の transaction を確認する。

アプリ実行時に`Base.metadata.create_all()`だけで既存DBを暗黙更新しない。
Phase 2のrevision `20260728_0002`はCampus、CourseProject、TimeSlot、OpenDate、
Student、Teacher、Subject、TeacherQualification、LessonRequestを追加する。
Phase 3のrevision `20260728_0003`はStudentAvailability、TeacherAvailability、
GroupLesson、GroupLessonStudent、ImportBatch、ValidationIssue、AuditLogを追加する。
Phase 4のrevision `20260728_0004`はOptimizationRun、Assignment、関連indexと
複合外部キーを追加する。
Phase 5のrevision `20260729_0005`はAssignmentへ任意備考、AuditLogへ任意理由、
操作元、任意operation IDと検索indexを追加する。
Phase 6のrevision `20260729_0006`はプロジェクトと1対1の`output_settings`を追加する。

Phase 3テーブルの主要な整合性は次のとおりである。

- availabilityは`(project_id, person_id, date, time_slot_id)`を複合主キーとし、
  `availability_level`を0～2に制限する。projectとtime slotの組を複合外部キーで
  拘束し、日付・コマ／人物・日付検索用indexを持つ。
- GroupLessonは`(project_id, group_code)`を一意とし、`start_time < end_time`を
  DBでも検査する。受講者は`(group_lesson_id, student_id)`を複合主キーとする。
- ImportBatchの件数は非負、ValidationIssueのseverityは
  `error / warning / info`に限定し、project・状態・対象検索用indexを持つ。
- AuditLogはproject・時刻／対象検索用indexを持つ。全テーブルはproject削除時に
  CASCADEし、集団授業の科目はRESTRICT、担当講師はSET NULLとする。

Phase 4テーブルの主要な整合性は次のとおりである。

- Assignmentは`(project_id, lesson_request_id, session_index)`を一意とし、
  session indexを1以上に制限する。projectとLessonRequest、projectとTimeSlotを
  複合外部キーで拘束し、別プロジェクトの参照をDBでも拒否する。
- AssignmentからTeacher、LessonRequest、TimeSlotはRESTRICTし、参照中のマスターを
  暗黙削除しない。OptimizationRun削除時だけ任意のrun参照をSET NULLにする。
- OptimizationRunは`running / completed / cancelled / failed`、solver statusは
  `OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN / MODEL_INVALID`に制限する。
- 制限時間、件数、経過秒、終了日時、空でないJSON snapshotをDB制約でも検査する。
- `20260728_0003 → 20260728_0004`のupgradeは既存Phase 3データを保持する。
  プロジェクトopen時のmigration前snapshot方針は従来どおりである。

Phase 5 migrationの主要な整合性は次のとおりである。

- `Assignment.note`はnullable textとし、既存Assignmentを変換せず保持する。
- `AuditLog.source`は`system / manual / automatic / undo / redo / import`だけを許し、
  既存行はserver default `system`で安全にupgradeする。
- `AuditLog.reason`と`operation_id_optional`はnullableとし、Phase 3の既存取込み監査を
  壊さない。Phase 5の新しい手動操作ではApplication Serviceが理由を必須化する。
- `operation_id_optional`は元操作とUndo / Redoを関連付ける36文字IDであり、
  `(project_id, operation_id_optional)`のindexを持つ。
- `20260728_0004 → 20260729_0005`のupgrade / downgradeとORM schema一致を
  一時SQLiteで検証する。migration前snapshot方針を迂回しない。

Phase 6 migrationの主要な整合性は次のとおりである。

- `output_settings.project_id`を主キーかつ`course_projects.id`へのCASCADE外部キーとし、
  1プロジェクト1設定に限定する。
- A3 / A4、縦横、生徒別改ページmode、日数1～7、講師列1～20、文字5～18pt、
  余白0～30mmをDB制約でも検査する。
- 表示項目と色・文字マーカーはJSON textとして保存するが、空文字をDBで拒否し、
  読込み時にPython側で構造、必須code、色形式を再検証する。
- 既定出力先はnullableとする。校舎ロゴは`output_settings`へ複製せず、
  既存の`Campus.logo_path_optional`を使用する。
- `20260729_0005 → 20260729_0006`のupgradeは既存プロジェクト、Assignment、
  AuditLog、校舎ロゴを変更しない。downgradeは`output_settings`だけを削除する。

### 9.3 Phase 2の所属範囲と一意性

Student、Teacher、Subjectはファイル境界のマスターである。各行へ`project_id`を
追加せず、1 `.jukuschedule` = 1 CourseProjectという不変条件で所属範囲を定める。
したがって`external_id`と`code`はファイル内で一意である。同じIDを別の
`.jukuschedule`で使用してもDB上は衝突しない。

TimeSlot、OpenDate、LessonRequestは`project_id`を持つ。LessonRequestは
`(project_id, student_id, subject_id)`を一意とし、通常担当と希望講師の参照は
nullableで保持する。TeacherQualificationは複合主キーとし、高校数学一般と
高校数学IIIを含む各科目の`can_teach`を個別に明示する。

### 9.4 削除方針

- 通常運用はStudent、Teacher、Subjectの`active = false`による使用停止を優先する。
- StudentとSubjectを参照するLessonRequestには`RESTRICT`を設定する。生徒の物理削除を
  利用者が確認した場合は、Application Serviceが同じtransactionで依存LessonRequestを
  明示削除する。SubjectはPhase 2 UIでは使用停止を基本とする。
- TeacherQualificationはTeacher / Subject削除に`CASCADE`する。
- LessonRequestの通常担当・希望講師参照はTeacher削除に`SET NULL`し、
  LessonRequest自体を失わない。
- TimeSlot、OpenDate、LessonRequestはCourseProject削除に`CASCADE`する。
- CampusはCourseProjectから参照されている間は`RESTRICT`する。

Phase 4で追加したAssignmentは、履歴と時間割を誤って失わないようStudent、Teacher、
Subject、TimeSlot、LessonRequestの物理削除をより制限する。Phase 5以降で編集・削除
操作を追加する場合も、この参照方針を迂回せず、明示的な利用者確認と監査要件を
合わせて設計する。

## 10. QML と Python の接続

QMLへ公開するPythonオブジェクトはViewModelに限定する。

- `appViewModel`: アプリバージョン、アプリ管理DB準備状態、状態の日本語表示
- `workspaceViewModel`: 現在のプロジェクト、最近使用した一覧、Phase 2の表示用
  collection、操作slot、状態・エラーメッセージ
- `phase3ViewModel`: availability / 集団授業取込み、差分、入力検証、匿名サンプルの
  表示用collection、操作slot、状態・エラーメッセージ
- `optimizationViewModel`: preset、実行中状態、経過時間、solver status、目的内訳、
  未配置理由、警告、中断操作、ログ保存先
- `scheduleEditorViewModel`: 当日`QAbstractTableModel`、日付・filter、カード・未配置・
  集団授業・差分・履歴、drop preview、詳細編集、lock、Undo / Redo、checkpoint
- `outputViewModel`: 出力workspace、draft設定、日付／講師／生徒選択、保存先、
  QThread出力worker、上書き確認、一時PDF URL、状態・エラーメッセージ

各ViewModelはQMLの文字列、bool、ID、`file:` URLをPythonの型へ変換し、Application
Serviceを呼ぶ。SQLAlchemy SessionやORM objectをQMLへ返さず、DTOを
`QVariantList`相当の辞書または`QAbstractTableModel`へ変換する。Application /
Domainの例外は、入力欄または状態バナーで表示できる日本語メッセージへ変換する。

`Main.qml`は9画面のメタデータを一元管理する。`Sidebar.qml`が選択indexを通知し、
`Loader`がPhase 2の管理画面、Phase 3のAvailabilityImportPage、GroupLessonPage、
ValidationIssuesPage、Phase 5のScheduleEditorPage、Phase 6のOutputPageを表示する。
「時間割」内部の`StackLayout`はScheduleEditorPageとPhase 4のOptimizationPageを
切り替え、再最適化後も同じViewModel接続を使う。`PlaceholderPage`は未接続indexへの
fallbackとして残す。

新しい画面を追加するときは次を守る。

- QML 内で SQL を発行しない。
- QML から Repository や SQLAlchemy model を直接触らない。
- QML に入力検証や時間割制約の正本を置かない。
- ViewModel は表示用変換と操作受付を担当し、業務判断は Application / Domain に委譲する。
- 長時間処理を UI thread で実行しない。
- エラー状態は色だけでなく、文字やアイコンでも伝える。
- 日本語文字列、キーボード操作、DPI、1366×768 を確認する。

未保存状態には2種類あることに注意する。QMLフォーム上でまだApplication Serviceへ
渡していない編集中の値と、Project Serviceが開いているSQLiteへ反映済みの値である。
「保存／キャンセル」はフォーム編集を明示し、クローズや別ファイルopen前には
ViewModelのdirty状態を確認する。QMLローカル状態だけをPython側が認識できない設計に
しない。

## 11. マスターExcel

Phase 2のExcel adapterは`infrastructure/excel/`へ置き、5シートのschemaを
`schema.py`で一元管理する。UIはopenpyxlを直接呼ばない。利用者向けの列契約は
[`master_data_excel.md`](master_data_excel.md)を参照する。

```text
QML
  → WorkspaceViewModel
  → MasterDataExcelService
  → reader / validation / template
  → SQLAlchemy transaction
```

出力は目的ディレクトリの一時ファイルへ保存し、成功後に`os.replace`する。ブックには
日本語ヘッダー、架空の例示行、列コメント、入力規則、フィルター、固定ヘッダーを
設定する。「例示行」が「はい」の行は再取込み時に無視する。

取込みは次の順で行う。

1. 必須5シートとヘッダーを検査する。
2. セルを文字列、整数、真偽値へ正規化し、シート・行・列付きissueを作る。
3. シート内重複、既存DBとの差分、参照ID、学校段階、講師資格、優先度5、
   無効講師、希望講師重複を横断検証する。
4. まだDBを変更せず、新規／更新件数と警告・エラーをpreviewとして返す。
5. エラーがない同じpreviewを利用者が確認した後、全シートを1transactionで反映する。
6. flush / commitで例外が発生した場合は全体をrollbackする。

入力エラーをログへ記録するとき、Excel行全体や氏名をそのまま残さない。Phase 3の
日時アンケート取込みは、列マッピング・差分を持つ別adapter / application flowとして
追加し、この固定5シートschemaへ混在させない。

## 12. Phase 3の取込みと入力検証

Phase 3のDB非依存ファイル処理は`infrastructure/importing/`へ置く。xlsx / CSVの
読取り、CSV文字コード判定、元セル保持、canonical field mapping、型変換、
テンプレート、セル差分を担当する。DB照合、保護項目、transactionはApplication
Serviceが担当する。

```text
QML
  → Phase3ViewModel
  → AvailabilityImportService / GroupLessonService
  → infrastructure.importing + MasterRepository
  → 1 SQLAlchemy transaction（業務データ + ImportBatch + AuditLog）
```

availabilityの取込みは、入力ファイルを調査してシート・文字コード・ヘッダー・先頭
20行とmapping候補を返し、利用者のmappingで全行を検証する。エラーを含むpreviewは
反映できない。反映時は同じファイルを同じmappingで再読込み・再検証する。削除候補は
表示するだけで、利用者が明示した場合だけ削除する。生徒アンケートから更新できる
LessonRequest項目は第1～第3希望講師だけである。

集団授業は「集団授業」「受講者」2シートを一緒に検証する。任意時刻は半開区間
`[start, end)`で比較し、同一講師または同一生徒の重複をエラーにする。終了と次の
開始が同じだけなら重複ではない。

`ProjectValidationService`は保存済みデータから可能枠不足、優先度5共通枠不足、
講師資格、集団授業衝突、コマ時刻重複、休校日データ、無効マスター参照等を再計算
する。前回の未解決ValidationIssueを解決済みにして、現在の結果を追加する。詳細な
設計判断は[`adr/0006-phase3-import-validation-and-audit.md`](adr/0006-phase3-import-validation-and-audit.md)、
手動確認は[`manual_test_phase3.md`](manual_test_phase3.md)を参照する。

## 13. Phase 4の最適化境界

### 13.1 入力DTOと候補

`OptimizationRunService.prepare()`は最初に`ProjectValidationService`を実行し、
errorが1件でもあればrunを作らず終了する。errorがない場合だけ短いDB transactionで
`build_optimization_input()`を呼び、ORM行を`frozen=True`の`OptimizationInput`へ
コピーする。DTOはSession、ORM object、QObjectを保持せず、worker threadへ安全に
渡せる。

DTOには全マスター、開校日、コマ順序、availability 0／1／2、講師資格、
LessonRequest、任意時刻の集団授業、既存Assignment、設定値を安定順で含める。
version付きJSONはkey順を正規化し、NaNや重複key、未知field、不正schema、過大payloadを
拒否する。入力JSONのSHA-256をprepare結果とOptimizationRunへ対応付ける。

候補生成は単一候補だけで判定できる次を先に除外し、疎な`CandidateData`と
機械可読な除外理由を返す。

- 休校日、無効コマ、availability 0
- 無効な生徒・講師・科目、講師資格なし
- 優先度5で通常担当講師以外
- 半開区間で重なる集団授業
- ロック済みAssignmentとの明白な衝突

連続上限、空きコマ、複数候補間の容量は候補だけでは確定しないため、CP-SAT制約と
保存前validatorで扱う。

### 13.2 ハード制約

各LessonRequestを`session_index=1..required_sessions`へ展開し、各sessionへ
`sum(candidate x) + unassigned == 1`を課す。必要回数を超えず、配置不能でも
ハード制約を破らず未配置になる。

Phase 4で扱うハード制約は次のとおりであり、目的関数のpenaltyへ変更しない。

1. 各sessionはちょうど1候補または未配置
2. 生徒の同時刻重複禁止
3. 同一講師・同一コマは最大2名
4. 1対1必須を含む講師枠は合計1名
5. 優先度5は通常担当講師だけ
6. 講師科目資格
7. 生徒availability 0の除外
8. 講師availability 0の除外
9. 開校日・有効コマだけを使用
10. 任意時刻の集団授業と受講生の重複禁止
11. 任意時刻の集団授業と担当講師の重複禁止
12. ロック済みAssignmentの日時・コマ・講師保持
13. 同一LessonRequestの同一日複数回は許すが、他のハード制約を適用
14. 生徒の最大連続コマ数
15. `allow_gap=false`の生徒の空きコマ禁止
16. `allow_gap=false`の講師の空きコマ禁止
17. 必要回数超過禁止
18. 無効な生徒・講師・科目を使用しない

空きコマはowner・日付ごとに`sort_order`順のactive列を作り、0から1へ変化する
start変数の合計を1以下にすることで、空集合または1つの連続区間に限定する。
固定集団授業の占有もactiveへ含める。生徒の`allow_gap_override`は値があれば
Student標準値より優先し、講師はTeacher値を用いる。

連続上限は`limit + 1`個の各窓のactive合計を`limit`以下にする一般形である。
LessonRequestの`max_consecutive_slots_override`があればStudent標準値より優先する。
講師には連続上限を追加しない。詳細な決定は
[`ADR 0004`](adr/0004-ortools-boundary-and-lexicographic-optimization.md)を参照する。

### 13.3 辞書式Solveとstatus

目的は次の順で別々にSolveする。

1. 未配置数を最小化
2. 優先度1～4、通常担当、第1～第3希望の講師希望違反を最小化
3. 稼働する講師×日付×コマ数を最小化
4. 生徒・講師のavailability level 2を最大化
5. 未ロック既存Assignmentからの変更を最小化
6. 設定値が正の場合だけ任意の講師負荷差を最小化

候補生成開始前から全処理で1つのdeadlineを共有する。候補生成とハード制約構築には
利用者中止または期限到達を判定するcallbackを渡し、各Solveには残り時間だけを渡す。
候補生成中の期限到達は利用者キャンセルと区別し、`cancelled=false`の`UNKNOWN`、
Assignmentなしで終了する。初期解・model構築中は、独立検証済みincumbentがあれば
`FEASIBLE`として復帰し、なければ`UNKNOWN`とする。

候補生成後は、ロック済み授業を先に保持し、候補数、優先度5、1対1必須を考慮する
決定論的greedy初期解を作る。追加ごとのschedule解析と完成後の独立validatorを通過した
解だけをincumbentとする。CP-SATへは配置・未配置、occupancy、start、補助indicatorを
含む全非固定変数のcomplete hintを渡す。既定規模では153,221変数であり、partial hint
の補完探索を避ける。初期解採用時と公開結果返却直前の二重validatorを通し、保存前の
Application Serviceでも独立検証する。同一生徒・講師の同時刻重複・容量制約は、
候補ペアごとではなくoccupancy単位へ集約する。

ある段階が`OPTIMAL`のときだけ整数目的値を等式で固定して次へ進む。`FEASIBLE`は
実行可能snapshotを保存するが、最適性未証明の目的値を固定せず、その時点で段階実行を
止める。`UNKNOWN`、`INFEASIBLE`、`MODEL_INVALID`ではsolverの変数値を読まない。
後段で`UNKNOWN`またはdeadline到達となっても、greedy初期解または直前までに取得した
検証済みincumbentだけを`FEASIBLE`として復帰する。`INFEASIBLE`と`MODEL_INVALID`は
過去snapshotで隠さない。

各段階にはincumbentの目的値より悪化させないcutoffを設ける。検証済みincumbentが
ある状態で残り5秒未満なら次段階を開始せず、各Solveでは残り時間の15%・最大3秒を
snapshot抽出、独立検証、診断、返却のために残す。

OR-Toolsは`9.14.6206`へ固定する。CP-SATのstatus、停止、value取得の境界と同じseedの
再現性をscenario testで管理するためであり、更新時は全制約・deadline・中断の
シナリオを再実行してから固定versionを変更する。

### 13.4 QThreadと中断

`OptimizationViewModel`はUI threadでprepareとfinalizeを行い、DB資源を持たない
`OptimizationInput`だけを`_OptimizationWorker`へ渡す。workerはQThread上で
`solve_optimization()`だけを実行する。

中止は`CancellationToken`の`threading.Event`へ記録し、候補・モデル構築の安全点で
確認する。Solve中はtokenへ束縛した`CpSolver.stop_search()`を呼ぶ。QThreadの
`terminate()`は使用しない。中止結果はAssignmentへ反映せず、OptimizationRunだけを
cancelledにする。実行中のプロジェクト切替も拒否する。

### 13.5 保存前安全弁と履歴

`OptimizationRunService.finalize()`は、同じproject IDと正規化したWindows pathを
確認し、保存済み入力JSON、prepare済みDTO、現在のDBから同じ設定で再構築した入力の
fingerprintを照合する。その後、候補を再生成し、
`validate_optimization_result()`でsessionの過不足、候補一致、固定、重複、容量、
1対1、集団授業、空きコマ、連続上限をsolverとは独立に検査する。

非中止の`OPTIMAL`または`FEASIBLE`だけを保存する。同じtransactionで既存
Assignmentを結果snapshotへ含め、既存のrunning OptimizationRunをcompletedへ更新し、
ロック済みAssignmentを保持して現在時間割を置換する。入力変更、validator違反、
保存例外ではtransactionをrollbackし、runをfailedへ更新する。キャンセルと
非実行可能statusではAssignmentへ触れない。

専用ログはsolver開始前に作成し、作成できなければ日本語エラーでrunの作成も
rollbackする。完了・中止・失敗の追記はDB transactionのcommit後に行う。追記だけが
失敗した場合は保存済みAssignmentやrun状態を戻さず、一般ログへ例外型だけを記録する。

### 13.6 簡易UIの範囲

OptimizationPageは30／120／600秒preset、実行、中止、経過時間、solver status、
配置／未配置、目的内訳、未配置理由、警告、最適化専用ログ保存先を表示する。
日付×コマ×講師グリッド、ドラッグ＆ドロップ、画面からのロック／解除、Undo / Redo、
差分表示、ロック以外の全体再最適化への接続はPhase 5で追加した。選択日・生徒・
講師周辺の部分再最適化は未実装である。Phase 4画面のWindows手動確認は
[`manual_test_phase4.md`](manual_test_phase4.md)を参照する。

### 13.7 性能測定

`tools/benchmark_phase4.py`は固定seedの架空データを生成し、候補数、候補生成時間、
end-to-end時間、status、配置件数をJSONで返す。既定値は生徒150名、講師40名、
40日、5コマ、300 LessonRequest、1,050 sessionである。

```powershell
python .\tools\benchmark_phase4.py --time-limit 30
```

2026-07-29の通常経路による既定規模・高速30秒実測は、候補73,440件、
独立候補生成3.369秒、end-to-end 27.179秒（solver報告27.015秒）、
status `FEASIBLE`、配置1,042件／未配置8件、時間内判定`true`だった。
全benchmarkは30.595秒だが、独立候補生成と、候補生成を再度行うend-to-endの
両計測を含むため、アプリの1回の待ち時間ではない。

同じ既定規模を
`python .\tools\benchmark_phase4.py --time-limit 120`で測定した標準120秒の正式値は、
独立候補生成3.451292秒、end-to-end 117.939982秒
（solver報告117.765秒）、status `FEASIBLE`、配置1,042件／未配置8件、警告1件、
時間内判定`true`である。全benchmark 121.440812秒は候補生成単独とend-to-endの
二重測定であり、アプリの120秒実行時間ではない。

通常経路では`tracemalloc`を無効にする。Python allocationの参考測定が必要な場合だけ
`--trace-memory`を指定する。この値はnative OR-Tools memoryを含まず、計測負荷も
大きいため、性能合否には用いない。

初期規模で高速presetが実用的な`FEASIBLE`を返す性能目標は満たした。標準presetは
後段の辞書式目的を改善するための選択肢であり、全入力・全環境で全段階の`OPTIMAL`
完了を保証しない。小規模scenario testと実規模benchmarkは引き続き分けて評価する。

## 14. Phase 5の時間割編集境界

### 14.1 読取りモデルと仮想化

`ScheduleEditService.load_board()`は短いSession内で最適化入力、候補、Assignment、
集団授業、未配置session、AuditLog、差分を読み、不変な`ScheduleBoardDto`として
Session外へ返す。カードやセルは安定IDを持ち、ORM objectをViewModelへ渡さない。

`ScheduleEditorViewModel`の`ScheduleGridModel`は`QAbstractTableModel`を継承し、
選択中の1日だけを「コマ行×講師列」として保持する。QMLは`TableView`、
`HorizontalHeaderView`、`VerticalHeaderView`と`reuseItems: true`を使用する。
全日×全講師×全コマを同時にQML Itemへ展開しない。複数日表示は日ごとの配置、
1対2、集団授業、警告、ロック件数の軽量summaryである。

日付は前日／翌日、横スクロール可能な日付タブ、`MonthGrid`で選択する。日付タブも
drop targetであり、同じ講師・コマの別日へ移動できる。検索・絞込みは氏名を表示用
モデル内だけで扱い、技術ログへ出さない。

40講師×5コマ×20日、1,000カードの架空DTOを使う自動テストでは、現在日modelを
200セルに限定し、構築と20日分の日付切替・filter操作をそれぞれ5秒未満とする。
これはPython modelの回帰閾値であり、Windows実機のdelegate描画、スクロール、DPIは
[`manual_test_phase5.md`](manual_test_phase5.md)で別に観察する。

### 14.2 編集previewとハード制約

`optimization/manual_edit.py`はUI、ORM、CP-SAT solverから独立し、次の不変値だけを
扱う。

```text
OptimizationInput + CandidateGenerationResult
  + 現在のEditSchedule
  + EditOperation(move / assign_unassigned / unassign)
  → EditPreview(green / yellow / red)
```

previewは現在状態が全sessionを配置または未配置として一度ずつ表す完全partitionで
あることを先に検証する。次に操作を不変snapshotへ仮適用し、Phase 4と同じ
`validate_optimization_result()`で候補一致、availability、資格、優先度5、重複、
最大2名、1対1、集団授業、ロック、連続上限、空きコマ等を再検査する。

- green: 全ハード制約を満たし、悪化するソフト評価がない
- yellow: 全ハード制約を満たすが、ソフト評価が悪化する
- red: 操作不正、現在状態不正、候補外、またはハード制約違反

redを適用する管理者強制経路は設けない。QMLに制約の正本を複製せず、drag entered時の
previewとdrop後の保存transaction内で同じApplication / Optimization境界を再実行する。
表示は色だけでなく、アイコン、安定したpreview / issue code、日本語説明を併記する。

yellowは未配置数、通常担当、希望講師、希望日時、1対2枠数、稼働講師枠、既存配置変更の
前後値と改善／不変／悪化を返す。利用者が確認し、理由を入力してからだけ保存できる。
ハード制約をyellowへ降格しない。

### 14.3 自動保存、監査、競合検出

`ScheduleEditService`は適用時に現在DBからcontextを再構築し、画面が保持する
fingerprintと照合する。同じtransactionでAssignment snapshotを作成・更新・削除し、
変更後contextを再構築して、AuditLogを追記する。途中例外ではtransaction全体を
rollbackし、日本語の`ScheduleSaveError`を返す。

手動変更のAuditLogは次を持つ。

- actionと`LessonRequest ID:session index`
- 変更前後Assignmentのcanonical JSON
- 利用者の変更理由
- `source=manual / undo / redo`
- 元操作と逆操作を関連付けるoperation ID

Assignmentが存在しないsessionを「未配置」と解釈し、別の未配置tableは追加しない。
必要session集合と候補・診断はPhase 4の入力DTOから再構築する。Assignmentへ
`note`を追加し、AuditLogの理由・source・operation IDとともにrevision
`20260729_0005`でmigrationする。

「手動保存」は即時保存済みDBをProjectServiceのSQLite backup APIで整合した明示
保存点へ複製し、保存先と個人情報を含み得る旨を表示する。未保存queueをcommitする
操作ではない。詳細dialog編集中は「編集中・未保存」、yellow確認待ちは
「確認待ち・未保存」、transaction中は「保存処理中」、成功後は「自動保存済み」、
失敗時は「保存失敗・未反映」とrollback済みの日本語エラーを表示する。
再最適化前にも同じbackup APIでcheckpointを
作るが、通常の手動保存は再最適化差分baselineを変更しない。

別processでSQLite transactionを開始し、未commitのAssignment / AuditLogを書いた後に
`os._exit()`する結合テストを持つ。最後にcommit済みのAssignmentとAuditLogは再接続後も
残り、未commitの両方はrollbackされることを確認する。これはtransactionの
crash-consistency確認である。Phase 7の異常終了marker、自動backup世代管理、復旧候補、
復元前退避とは別の安全層であり、両方を
`tests/integration/test_project_recovery.py`で補完する。

### 14.4 Undo / Redoと差分

Undo / Redoはprocess内のcommand stackで管理する。commandはbefore / after
Assignment snapshot、before / after fingerprint、理由、operation ID、差分を持つ。
逆操作も同じDB transactionで保存し、`source=undo / redo`のAuditLogを追記する。

Undo前の現在fingerprintがcommandのafter、Redo前がbeforeと一致する場合だけ適用する。
対象Assignmentもsnapshot一致を検査し、外部変更を古いcommandで上書きしない。
明示再読込み、プロジェクト切替、再起動、fingerprint不一致時はprocess内stackを
破棄するが、既存AuditLogは削除しない。

差分はsession単位で新規配置、日時変更、講師変更、未配置化、pairing size変化、
変更なしを機械可読codeと日本語summaryで返す。手動操作直後は直前操作前後、
checkpoint後の再最適化ではcheckpoint baselineと再読込み後の時間割を比較する。

### 14.5 ロックと再最適化

Phase 5で必須の授業単位ロック／解除を実装する。ロック済みAssignmentは手動移動・
未配置化を拒否し、解除は明示操作とAuditLogを伴う。セル・日付・講師・選択範囲の
一括ロックは任意拡張であり、現時点では提供しない。

「ロック以外を再最適化」は次の順で既存Phase 4境界を再利用する。

1. 対象配置数、ロック数、手動変更数、未配置数、fingerprintを表示する。
2. 現在の`.jukuschedule`をSQLite backup checkpointへ保存する。
3. 同じ「時間割」内のOptimizationPageへ移動する。
4. Phase 4が全Assignmentを既存配置として読み、ロック済みをハード制約で保持する。
5. 非中止の独立検証済み`OPTIMAL` / `FEASIBLE`だけをtransaction保存する。
6. 編集画面へ戻るとsignalで再読込みし、checkpoint前後の差分を表示する。

選択日、選択生徒、選択講師周辺だけの部分再最適化は、境界が安全に定義されるまで
提供しない。全体再最適化を「部分再最適化済み」と表現しない。

詳細な判断は
[`ADR 0007`](adr/0007-phase5-schedule-editing-boundary.md)を参照する。

## 15. Phase 6の出力境界

### 15.1 最新DBから共通レイアウトまで

QMLは帳票種別、形式、保存先、draft設定、日付／講師／生徒IDだけを
`OutputViewModel`へ渡す。DB、候補生成、ハード制約検証、未配置診断、ファイル生成を
QML JavaScriptへ記述しない。

実ファイル生成のデータフローは次のとおりである。

```text
OutputPage.qml
  → OutputViewModel（QThread worker）
  → OutputService
      → ProjectValidationService
      → OutputRepository / OptimizationInputBuilder
      → Phase 4独立result validator
      → OutputSnapshot
      → reporting builder
      → LayoutDocument
          ├─ ExcelRenderer
          └─ HtmlRenderer → QtPdfRenderer
```

`OutputRepository`は短いSession内で、プロジェクト、期間内の全日、コマ、生徒、講師、
科目、受講希望、Assignment、集団授業、ValidationIssueを不変な`OutputSnapshot`へ
コピーする。ORM objectとSessionをViewModel、QML、帳票builder、rendererへ渡さない。

実際のExcel、PDF、CSV出力では`OutputService._prepare(refresh=True)`を必ず通し、
画面表示時のcacheを使わず現在DBを再読込みする。全Assignmentと未配置sessionの
partitionを再構築し、Phase 4のsolverから独立した
`validate_optimization_result()`でハード制約と参照整合性を検査する。不正な現在状態では
すべての出力を中止し、既存の出力ファイルを変更しない。

未配置理由は現在のAssignmentに対して再診断する。「単独配置可」は現在結果へ対象
sessionを1件だけ追加して独立validatorを通過した最大3候補だけに付ける。複数候補を
同時適用できる保証や自動修正案ではない。候補がなければ診断コードに対応する
availability、資格、1対1、定員、空きコマ、連続上限等の条件確認案を表示する。

`reporting/`の純粋builderは次の`LayoutDocument`を作る。

- 全体時間割: 日付×講師の表、コマ／時刻、最大2名、集団、休校、凡例。日付数と
  講師列数で物理ページ分割し、担当未設定の集団授業は別sectionへ置く。
- 生徒別: 日付、コマ、時刻、科目、講師、1対1／1対2、備考、状態、未配置残数。
  1人1ページまたは2人ずつまとめる。
- 講師別: 生徒1／2、学年・科目、集団授業、日ごとの連続勤務範囲、
  期間の合計稼働コマ数。
- 未配置・警告: 必要／配置済／不足、理由、解決候補、優先度、通常担当、1対1、備考と、
  severity、issue type、日時、人物、内容、対応状況。

`LayoutDocument`以下は帳票metadata、section、物理page、table、row、cell、列幅、
row / column span、文字配置、役割、表示ruleを持つ不変型である。ExcelとPDFが同じ
中間表現を消費し、形式別に業務データを再解釈しない。

### 15.2 Excel、PDF、CSV

`ExcelRenderer`はopenpyxlで編集可能なxlsxを生成する。A3 / A4、縦横、余白、
fit-to-width、印刷範囲、改ページ、繰り返し文書見出し、ヘッダー／フッター、ページ番号、
罫線、結合、列幅、行高、折返し、縮小表示を設定する。利用者文字列は明示的な文字列型とし、
先頭`=`等を数式に変換しない。共通レイアウトはロゴパスを持つが、Phase 6のExcelには
編集性と画像依存追加を避けるためロゴ画像を埋め込まない。

PDFは次のローカル処理だけで生成する。

1. `HtmlRenderer`が各物理ページをQt rich text互換のtable中心HTMLへ変換する。
2. 利用者文字列をHTML escapeし、対応する任意ロゴをdata URLへ埋め込む。
3. `QTextDocument`を`QPdfWriter`へ描画する。
4. Windowsの`Yu Gothic UI`、`Yu Gothic`、`Meiryo`等を優先し、存在しなければ
   Qtのsystem fontを使う。フォントファイルは同梱しない。
5. `QPdfDocument`で一時PDFを再読込みし、サイズ、ページ数、各ページ寸法を検証する。

内容がページに収まらない場合は縮小するが、0.62未満になる場合は読めないPDFを保存せず、
日数または講師列数を減らす日本語エラーを返す。Chromium、クラウドPDF変換、外部URLを
必要としない。

`CsvRenderer`はPython標準`csv`で、マスター仕様の18列をCRLF付きUTF-8へ出力する。
BOM有無を設定でき、既定はExcelで開きやすいBOMありである。個別Assignmentに加え、
固定集団授業を受講者単位の行として出力する。先頭空白を除いた値が
`= / + / - / @`で始まる場合はapostropheを付け、表計算ソフトでの数式解釈を防ぐ。

### 15.3 印刷プレビューとUI

印刷プレビューは保存用PDFと同じ`OutputService` / `QtPdfRenderer`経路で一時PDFを作り、
QMLの`PdfDocument` / `PdfMultiPageView`へ渡す。前／次ページ、50～300%の倍率、
幅合わせ、全体表示、用紙・向き・日数・講師列数の表示を提供する。CSVは印刷帳票では
ないためプレビュー対象外である。

一時PDFは専用`TemporaryDirectory`へ置き、古いpreviewの切替時とアプリ終了時に削除する。
出力worker実行中は二重生成とプロジェクト切替を拒否する。終了処理ではworker完了を待つ。
30秒で完了しない場合は警告を記録し、原子的置換の途中でworkerを強制終了せず完了を
待つため、OSや外部ファイルシステムが応答しない場合は終了が遅れる可能性がある。

出力画面では次を編集または選択できる。

- 全体、生徒別、講師別、未配置・警告、割当て生データ
- Excel、PDF、CSV。ただし生データはCSV、他帳票はExcel / PDF
- 保存先、用紙A3 / A4、横／縦、日数1～7、講師列1～20、文字5～18pt、余白0～30mm
- ファイル名規則の`{project}` / `{report}` / `{date}`
- 校舎ロゴ、表示項目、生徒別改ページ、CSV BOM、色と文字マーカー
- 対象日、対象講師、対象生徒

対象が存在する場合は各分類で1件以上を選択する。保存した設定と未保存draftを区別し、
「元に戻す」は最後の保存値へ戻す。ロゴは`Campus.logo_path_optional`、他項目は
`output_settings`へ同一transactionで保存する。

### 15.4 原子的保存とエラー

Excel、PDF、CSVは最終保存先と同じディレクトリへ一時ファイルを作り、生成処理
（PDFでは生成後の再読込み検証を含む）が完了した後だけ`os.replace`で最終名へ
置き換える。既存ファイルを先に削除しない。
`overwrite=False`では既存ファイルを拒否し、QMLで明示確認後だけ再実行する。一時ファイル
作成後に同名ファイルが現れるraceも拒否する。

保存先権限、Excel等のファイルロック、書込み、描画、参照欠落は型付き例外と日本語
メッセージに変換する。失敗を正常完了として表示せず、一時ファイルを削除し、既存の
最終ファイルを保持する。

### 15.5 業務上の参考資料から独立した帳票

業務上の参考PDFやExcelは個人情報を含む可能性があるため、公開リポジトリ、
テストfixture、配布物へ含めない。アプリの起動と帳票生成も外部の参考資料へ依存しない。

公開仕様から、校舎／講習／更新日のheader、日付block、縦方向の
コマ／時刻、講師列、最大2名の生徒情報、1対1、集団、休校、凡例、ページ番号という
情報構造を実装した。参考資料固有の寸法、書体、配色、装飾、余白、注記位置を直接再現・
検証したとは扱わない。

可読性のため、日付と講師を物理ページへ先に分割し、担当未設定集団授業、未配置、
警告を独立sectionにした。色へ文字マーカーを併記し、過密PDFは極小表示せずエラーにする。
用紙、向き、日数、講師列、文字、余白、表示項目、色、マーカー、対象、改ページmode、
ロゴ、ファイル名、保存先、BOMを設定可能にした。

詳細な判断は
[`ADR 0008`](adr/0008-common-layout-and-safe-local-output.md)、Windows実機確認は
[`manual_test_phase6.md`](manual_test_phase6.md)を参照する。

## 16. 検査とテスト

仮想環境を有効にして次を実行する。

```powershell
ruff check .
ruff format --check .
mypy src tests
pytest
```

自動修正を行う場合は、差分を確認してから次を使用する。

```powershell
ruff check . --fix
ruff format .
```

テストの分類は次のとおりとする。

- `tests/unit/`: 設定、Domain 規則、変換など外部 I/O を持たない単体テスト
- `tests/integration/`: 一時 SQLite、migration、QML resource 読込みなど境界を含むテスト
- `tests/scenarios/`: Phase 4以降の最適化シナリオ

Phase 6では、共通レイアウト、対象filter、表示項目、HTML escapeを単体テストし、
openpyxlで生成xlsxを再読込みして主要セルと印刷設定を検査する。Qt PDFはoffscreenの
別processで生成し、`QPdfDocument`でA3横、ページ数、寸法、日本語パスを検査する。
CSV 18列、BOM有無、集団授業、数式注入候補、上書き、原子的保存、最新DB再読込み、
独立validator拒否、設定round trip、`0005 → 0006` migrationも結合テストする。

Phase 7では、integrity check、write / lock probe、世代削除、recovery marker、
破損元／破損backup、migrationを含む復元、復元前退避、容量・権限・lock・長いpathの
例外分類を`test_project_recovery.py`で確認する。版整合、About、release packaging、
license収集も独立test対象とする。目標規模の性能は
[`performance.md`](performance.md)に実測値と未測定境界を記録する。

テストで `%LOCALAPPDATA%` の実運用 DB やログを使用してはならない。一時ディレクトリへ明示的に差し替える。実在する生徒・講師名を fixture や snapshot に入れない。

GUI smoke testを実行する場合はQtのoffscreen platformを利用し、event loopを無期限に
待たない。業務ロジックの正しさをQMLのpixel比較だけに依存させない。PDFの
`QTextDocument` / `QPdfWriter`にはQt applicationが必要なため、単体builder testと
Qt process testを分ける。

性能変更時は小規模の自動テストに加え、上記benchmarkを同じ設定と環境で実行する。
status、配置・未配置件数、`within_requested_wall_time`を合わせて確認し、プロセスの
終了コードだけを「性能成功」と解釈しない。memory測定は通常の時間合否から分離する。

Windowsでの画面、キーボード、DPIの確認項目は
[`manual_test_phase6.md`](manual_test_phase6.md)に記載する。Phase 5以下の回帰は
[`manual_test_phase5.md`](manual_test_phase5.md)、
[`manual_test_phase4.md`](manual_test_phase4.md)、
[`manual_test_phase3.md`](manual_test_phase3.md)、
[`manual_test_phase2.md`](manual_test_phase2.md)と
[`manual_test_phase1.md`](manual_test_phase1.md)を参照できる。
Phase 7の強制終了、OneDrive競合、read-only、容量、権限、長いpath、復元確認は
[`manual_test_phase7_data_safety.md`](manual_test_phase7_data_safety.md)を使う。
Phase 7全体の状態は[`acceptance_test_phase7.md`](acceptance_test_phase7.md)で
PASS／PARTIAL／NOT TESTEDを区別する。source service testの成功を、packaged GUIや
clean Windowsの成功へ読み替えない。

## 17. GitHub Actions

通常の`.github/workflows/ci.yml`はpush／pull requestで少なくとも次を実行する。

1. Python 3.12 のセットアップ
2. 開発依存関係のインストール
3. `ruff check .`
4. `ruff format --check .`
5. `mypy src tests`
6. `pytest`

CIで利用するアプリ管理DB、`.jukuschedule`、Excel、ログ、設定は一時領域に置き、
artifactへ含めない。

`.github/workflows/release-candidate.yml`は`v*`tagだけを入力とし、次を別jobで行う。

1. 通常CIと同じRuff、format、mypy、pytestを先に通す。
2. tagの`v`を除いた値が`pyproject.toml`のapp versionと完全一致することを検証する。
3. Python 3.12 x64へ`packaging/requirements-release.txt`の固定依存を導入する。
4. pyside6-deploy／Nuitkaでstandalone treeと決定的portable ZIPを作る。
5. Pythonを`PATH`から外し、日本語の一時data／log pathでstandalone smokeを行う。
6. Authenticode署名を検査したInno SetupをCI用一時directoryへ展開する。
7. installerを作り、日本語pathへsilent install、smoke、uninstallし、user data保持を
   検証する。
8. portableとinstallerのSHA-256を生成・再検証してCI artifactへ保存し、再download後も
   同じchecksumになることを確認する。
9. build jobはrepository read-onlyとし、後続の最小jobだけへ`contents: write`を与える。
10. 再download・再検証した成果物だけを同じtagの**draft prerelease**へ添付する。

workflow fileとcontract testが存在しても、GitHub-hosted runを実行していなければ
`NOT TESTED`である。tag pushはdraft Release作成を開始する外部状態変更なので、
[`release_checklist.md`](release_checklist.md)のlicense、clean Windows、成果物、
公開責任者の確認を終えるまで行わない。draftを本番公開する処理はworkflowに含めない。

## 18. Phase 7のWindows buildとRelease候補

### 18.1 固定release環境

release buildは通常のeditable開発環境と分け、Python 3.12 x64で固定依存を使う。

release buildはrepositoryと`.venv-release`を含む**実体パス**がASCII文字だけの
workspaceで行う。`subst`、junction、symbolic linkではNuitka／MSVCが非ASCIIの実体
パスを再解決するため回避できない。正確なsource stateを
`C:\build\summer-scheduler`等へcopy／cloneし、その場所でrelease用仮想環境を新規作成
する。この制限はbuild時だけで、完成アプリの日本語install／data path対応とは別である。

```powershell
py -3.12 -m venv .venv-release
.\.venv-release\Scripts\python.exe -m pip install --upgrade pip
.\.venv-release\Scripts\python.exe -m pip install -r packaging\requirements-release.txt
.\.venv-release\Scripts\python.exe -m pip install --no-deps --no-build-isolation .
.\.venv-release\Scripts\python.exe -m pip check
```

`requirements-release.txt`は再現可能な候補を作るための入力である。正式Releaseごとに
依存版、脆弱性、license、Windows 10 / 11対応を再確認し、過去の固定版を無条件に
使い続けない。

### 18.2 standaloneとportable

```powershell
.\scripts\build_windows.ps1 `
  -Python .\.venv-release\Scripts\python.exe `
  -Version 1.0.0-rc.4
```

scriptはworkspace内の`build/deploy`と`build/portable`だけを初期化し、
`build/portable/SummerCourseScheduler`を配布内容の正本として検査する。QML、
既定YAML、全Alembic revision、Qt Quick／PDF、OR-Tools native runtime、
`THIRD_PARTY_NOTICES.md`、収集したlicenseが必要で、DB、`.jukuschedule`、log、
入出力、backup、user config、build crash reportを拒否する。検査後に
`dist/SummerCourseScheduler-Portable-1.0.0-rc.4.zip`を決定的順序で作る。

2026-07-29に同一build machineで生成した未公開候補は143,564,844 bytes、
SHA-256 `5611f8e62b6e7e8e9ac456ca91186f5a52e207573fb866b377ccbaf0796eba2f`だった。
日本語と空白を含むpathへ展開し、PATHを制限したoffscreen `--smoke-test`は4.111秒、
exit 0である。application treeは実行前後とも3,494 files、差分0、
`__pycache__`／`.pyc` 0だった。利用者領域へ266,240 bytesのapp DB
（Alembic head `20260729_0006`）とlogを作り、application treeを変更していない。

ZIP作成だけではportable受入完了ではない。別directoryへ展開し、Python／Node.jsのない
clean Windows、offline、日本語user pathで起動し、新規projectからPDF、再起動・再open
まで確認する。展開後のapplication treeをread-onlyにしても、書込み可能な利用者別
local領域とproject／出力先を使って動作することも確認する。

### 18.3 installerとchecksum

Inno Setupの基礎ライセンス条件とcommercial userへの購入要請に対する方針を配布
責任者が確認し、承認した`ISCC.exe`がある環境で次を実行する。

```powershell
.\scripts\build_installer.ps1 `
  -Python .\.venv-release\Scripts\python.exe `
  -Version 1.0.0-rc.4 `
  -Iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

.\.venv-release\Scripts\python.exe scripts\package_release.py checksums `
  --output dist\SHA256SUMS.txt `
  dist\SummerCourseScheduler-Portable-1.0.0-rc.4.zip `
  dist\SummerCourseScheduler-Setup-1.0.0-rc.4.exe

.\.venv-release\Scripts\python.exe scripts\package_release.py verify-checksums `
  --checksums dist\SHA256SUMS.txt `
  --directory dist
```

同日の未署名・未公開installerは90,164,009 bytes、SHA-256
`98601a138cdda25a088c93bf2c96e93338098788de31fac2ff5bb8ac33d1dc89`だった。同一build
machineの短いlocal pathではfresh install 19.192秒、installed appのoffscreen smoke
8.057秒で、install、smoke、uninstallはいずれもexit 0だった。registry登録とStart
menu shortcutは1→0、未選択のdesktop shortcutは0のままで、app DB、log、sentinelは
uninstall後も保持された。

最深pathがおよそ264文字になる過長なinstall先ではexit 5となり、installerはrollback
した。短いpathでは成功したが、この結果を任意の長いpath対応へ一般化しない。

installerは同じstandalone treeだけを利用者単位でinstallする。uninstallはapp本体と
shortcutを削除するが、`%LOCALAPPDATA%\SummerScheduler`と利用者が選んだ
`.jukuschedule`を削除しない。`.jukuschedule`のfile associationはこの候補では
登録しない。fresh install、同じAppIdの上書きupgrade、任意desktop shortcut、
uninstall、user data保持は実installerで確認する。

### 18.4 公開境界

version、CHANGELOG、依存、成果物、SHA-256、clean Windows受入、hosted workflow、
GPL-3.0-only、Qt完成artifact、Inno Setupの基礎ライセンス条件とcommercial userへの
購入要請に対する方針を
[`release_checklist.md`](release_checklist.md)で確認する。タグは公開操作の入力であり、
確認前に作成・pushしない。承認後もworkflowが作るのはdraft prereleaseであり、
artifactを再downloadしてhashと起動を確認した後、配布責任者が別途公開判断する。
SignPath署名では秘密鍵をrepositoryやartifactへ置かず、署名後の最終成果物から
SHA-256を計算する。

## 19. 将来機能の追加手順

### 19.1 業務機能

1. マスター仕様の該当要件とハード／ソフト分類を確認する。
2. Domain の型と規則を先に定義し、単体テストを追加する。
3. Application Service のユースケースと Repository port を定義する。
4. SQLAlchemy adapter と migration を追加する。
5. ViewModel と QML を追加する。
6. 結合テストとドキュメントを更新する。

### 19.2 最適化制約

1. マスター仕様のどの制約かを明記する。
2. ORM ではなく最適化入力 DTO に必要な値を追加する。
3. 候補除外、CP-SAT 制約、診断理由を同じ変更で実装する。
4. 単体テストとシナリオテストを追加する。
5. ハード制約を penalty へ置き換えない。
6. 目的関数を追加する場合は辞書式順序と設定値を更新する。

### 19.3 入出力

Excel / CSV / PDFはInfrastructure adapterとして実装し、Application Serviceが呼び出す。
共通`LayoutDocument`へ業務情報を集約し、rendererごとにDBを再読込みしない。新しい形式を
追加する場合も、出力直前の最新DB再読込み、独立validator、原子的保存、上書き確認、
利用者向け日本語エラーを迂回しない。参考PDFはlayoutの参考に限り、実行時依存や
テストfixtureにしない。

## 20. Phase 7リリース候補の制限

- 「時間割」は時間割編集画面とPhase 4最適化画面を切り替える。「出力」は
  Excel / PDF / CSVと印刷プレビューを持つ実画面である。
- `master_data.xlsx`はマスター5シートだけであり、生徒・講師の日時availability、
  集団授業、固定Assignmentを混在させない。Phase 3入力は別テンプレートで扱う。
- 選択日・選択生徒・選択講師周辺の部分再最適化、セル・日付・講師・範囲単位の
  一括ロックは未実装である。
- Undo / Redoのcommand stackはprocess内だけであり、再起動、明示再読込み、
  プロジェクト切替、外部変更検出時に破棄する。監査ログはDBへ残る。
- 業務上の参考PDFは公開物や実行時依存へ含めない。帳票の情報構造は公開仕様から
  実装しており、特定資料のピクセル単位の再現は目的としない。
- 校舎ロゴはPDFヘッダーへ出力する。Phase 6のExcelにはロゴ画像を埋め込まない。
- PDFはQt rich text対応範囲で描画し、Windowsに存在する日本語フォントを使用する。
  DPI、プリンタードライバー、業務で使用するExcel / PDF viewerの実機確認は
  [`manual_test_phase6.md`](manual_test_phase6.md)に従う。
- 未配置の「単独配置可」は対象1sessionだけを現在結果へ追加した検証であり、
  複数候補の同時実行可能性や最適性を保証しない。
- 初期規模では高速30秒で実用的な`FEASIBLE`を取得できるが、標準／高品質presetでも
  入力規模や計算環境によって全辞書式段階の`OPTIMAL`完了は保証しない。
- project open直後とevent loop中の自動backup、整合性検査、復旧候補、安全な復元は
  実装済みだが、実OneDrive競合、組織ACL、OS上限に近い長いpath、実際の強制終了は
  手動確認が残る。backupは暗号化しない。
- standalone／portable／installer／checksumの生成scriptとrelease workflowは
  実装済みである。同一build machineではportable smoke、短いlocal pathへのfresh
  install、installed smoke、uninstall、user data保持が成功した。一方、Python未導入の
  clean Windows、offline、上書きupgrade、実GUI操作、署名、GitHub-hosted runは
  `NOT TESTED`である。およそ264文字の過長install pathはexit 5でrollbackした。
- 本番tag／GitHub Release／コード署名は未実施である。完成artifactのQt module、
  第三者notice、SBOMと署名経路を確認するまで、Windowsバイナリを公開しない。

Phase 7のsource実装完了と、法的・運用的に配布可能な本番Releaseは別状態である。
残項目は[`acceptance_test_phase7.md`](acceptance_test_phase7.md)と
[`release_checklist.md`](release_checklist.md)を参照する。
