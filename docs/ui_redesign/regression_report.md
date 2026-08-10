# UI刷新 regression / acceptance report

実施日: 2026-08-11

## 1. 実行結果

| Gate | 結果 |
|---|---|
| Baseline pytest | PASS — 423 tests / 133.52s |
| Stage 1関連test | PASS — 8 tests |
| Stage 2関連test | PASS — 38 tests / 35.13s |
| Stage 3関連test | PASS — 23 tests / 12.42s |
| Stage 4関連test | PASS — 38 tests / 13.43s |
| Stage 5関連test | PASS — 19 tests / 7.41s |
| Stage 6追加test | PASS — 11 tests / 2.25s |
| 最終pytest | PASS — 427 tests / 109.20s |
| `ruff format --check .` | PASS — 227 files |
| `ruff check .` | PASS |
| `mypy src tests` | PASS — 167 source files |
| 全QML `pyside6-qmllint` | PASS |
| `python -m summer_scheduler --smoke-test` | PASS |
| DPI scale 1 / 1.25 / 1.5 offscreen smoke | PASS / PASS / PASS |
| Alembic heads | PASS — `20260807_0007 (head)` |

smokeは毎回独立した日本語対応の一時data/log領域で実行し、初回SQLite作成とmigration適用を
含む。実行したcommandは本書末尾に記載する。

## 2. 回帰範囲

最終427 testsには次が含まれる。

- 新規/既存project、保存、再読込み、recent project
- SQLite初回migration、各Phase migration、Assignment/AuditLog保持
- 生徒・講師・LessonRequest、master Excel、旧header互換、日本語round-trip
- 生徒・講師アンケート、原本保管、差分、transaction、集団授業、区間重複
- Phase 4中核制約、timeout、独立validator、未配置理由、最適化ViewModel
- DnD、hard violation拒否、lock、Undo/Redo、AuditLog、lock保持再最適化
- Excel/PDF/CSV、全帳票、原子的保存、日本語path、150生徒×40講師×40日
- 匿名projectのimport→optimize→edit→output→restart end-to-end
- backup、破損検出、復元、release環境・packaging契約

## 3. 受入チェック

凡例: PASS = 自動または目視で確認、PARTIAL = 安全な範囲まで実装し手動/追加APIが残る、
BLOCKED = 既存contractを推測で変えないため未実装、MANUAL = 実機確認が必要。

### A. 回帰・互換性

- PASS: 全自動test、migration round-trip、旧Excel header互換、project再読込み。
- PASS: DB/migration、OR-Tools、rendererにUI都合の変更なし。
- PASS: lock保持再最適化、Undo/Redo、AuditLog、出力を既存integration/scenarioで確認。

### B. 1366×768 / Windows

- PASS: `Main.qml`は1366×768、minimum 1040×640。Windows上でafter画像を取得。
- PASS: DPI 100/125/150%相当のscaleで全QMLを読み込み、起動終了した。
- PASS: 主要buttonに日本語label、Accessible.name、標準focus behaviorを維持。
- MANUAL: Windows 10/11の実モニターで全画面Tab順、focus ring、長文・長い同姓名の目視。

### C. ホーム / 導線

- PASS: 4段階、現在状態、次に行うこと、管理画面への常時navigationを実装。
- PASS: project未選択時はproject開始、選択後は実データ状態に応じた次操作を表示。

### D. 管理画面

- PASS: 生徒/講師の一覧＋詳細、検索/filter、詳細設定折りたたみ、無効行の末尾表示。
- PASS: 初期Excel一括と日常の段階式個別追加を分離。

### E. アンケート

- PASS: file選択→内容確認→反映完了、列設定の通常非表示、既存差分・issue表示。
- PARTIAL: 不一致だけを専用resolverへ集約する新APIは追加していない。既存の行・列付きissueと
  差分を使い、QMLから推測補正しない。

### F. 集団授業

- PASS: 週カレンダー、開講日から追加、上部追加、必須項目、予定詳細、Excel取込み。
- PASS: 衝突は既存区間重複validatorが拒否し、日本語error bannerで理由を表示。
- BLOCKED: 既存予定の監査付きin-place update。理由はimplementation report参照。

### G. 自動作成

- PASS: 既存の準備状態、error理由、詳細設定、自動作成結果件数を維持。
- PASS: OR-Tools入力・制約・保存条件に差分なし。

### H. 時間割編集

- PASS: 未配置・grid・詳細の3ペイン、DnD判定色＋日本語理由、lock文字、保存状態。
- PASS: Undo/Redo、全体再最適化、lock保持、二重検証。
- PARTIAL/BLOCKED: issueから修正画面へは移動するが、情報不足のissueを特定cellへ推測jump
  しない。

### I. 警告

- PASS: error/warning/infoを記号＋文字＋色で表示し、内容・詳細・修正画面buttonを表示。
- PARTIAL: 全issueに「なぜ」を独立fieldで保持していないため、既存message/detailsの範囲で
  表示する。

### J. 出力

- PASS: 対象→形式→保存先、未配置警告、詳細設定折りたたみ、完了後folder表示。
- PASS: renderer/layout modelは未変更で、全出力integration test成功。

### K. 見た目

- PASS: 新規共通themeは背景`#F6F7F9`、白surface、薄いborder、青accent、4px系spacing。
- PASS: 状態は色だけでなくsymbol/日本語を併用し、不要animationを追加していない。
- PARTIAL: 既存の情報密度が高い時間割cellや一部legacy補助labelは8～12pxを維持した。
  一律拡大は1366×768の情報量と既存DPI契約を壊すため行っていない。

## 4. 手動確認手順

1. `python -m summer_scheduler`で起動し、1366×768、Windows表示倍率100/125/150%で確認する。
2. 旧版で作成した匿名化済み`.jukuschedule`を開き、project名、名簿、希望、時間割、lock、
   AuditLog、出力設定を確認する。
3. 新規projectを作り、Excel名簿、アンケート、集団授業、自動作成、DnD、lock、Undo/Redo、
   未配置確認、Excel/PDF出力を4段階で通す。
4. 保存して終了し、再起動後に同じprojectを開いて件数と内容を比較する。
5. 長い日本語氏名、同姓、長い備考、日本語＋空白を含むWindows pathで目視する。
6. keyboardだけで主要button・入力へ移動し、focus位置とCtrl+Z/Ctrl+Yを確認する。

実データではなく匿名化projectを使用する。問題があれば元projectを直接編集せず、backupを
確保してから再現条件を記録する。

## 5. 実行command

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src tests
.\.venv\Scripts\pyside6-qmllint.exe <全QMLファイル>
.\.venv\Scripts\python.exe -m summer_scheduler --smoke-test
.\.venv\Scripts\alembic.exe heads
```

DPI smokeでは`QT_SCALE_FACTOR=1`、`1.25`、`1.5`を順に設定し、
`QT_QPA_PLATFORM=offscreen`、software backend、独立data/log directoryで同じsmokeを実行した。
