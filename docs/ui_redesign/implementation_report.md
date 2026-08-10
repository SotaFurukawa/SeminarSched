# UI刷新 implementation report

実施日: 2026-08-11
対象: Stage 0～6
基準: `CODEX_MASTER_SPEC.md`、DROP-IN UI仕様、既存テスト・ADR

## 1. 結果

Stage 0からStage 6までを順番に実施した。DB schema、Alembic revision、
`.jukuschedule`形式、OR-Tools制約・目的関数、ドラッグ＆ドロップ検証、ロック、Undo/Redo、
AuditLog、Excel/PDF rendererは変更していない。最終ゲートは427 tests、Ruff、mypy、
全QML lint、DPI 100/125/150%のoffscreen起動で成功した。

## 2. Stage別の実装

### Stage 0 — 監査と凍結

- 現行画面、ViewModel、Service、DB migration、テスト、文書を監査した。
- `current_state_inventory.md`へ実装一覧を、`protected_contracts.md`へ変更禁止境界を記録した。
- baselineは423 tests成功、Ruff/mypy/QML lint/起動確認成功だった。

### Stage 1 — UI基盤とホーム

- 背景、surface、境界、青アクセント、状態色、余白、角丸、文字、control高を
  `UiTheme.qml`へ集約した。
- 共通button、badge、inline message、section header、empty state、step card、sidebar itemを
  component化した。
- サイドバーを「基本設定→アンケート→時間割作成→出力」の業務順に再構成した。
  互換性維持のため内部page indexは変更していない。
- ホームへ実データに基づく4段階の進捗、現在段階、次に行う操作を追加した。

### Stage 2 — 生徒・講師・アンケート

- 初期名簿の主導線をExcel一括追加・更新にした。
- 少人数追加は基本情報、運用設定、確認の3段階フォームにした。
- 生徒は最大連続2、空きコマ不許可、有効を初期値とし、講師は空きコマ不許可、有効を
  初期値にした。既存のViewModel保存slotをそのまま利用している。
- 生徒・講師の無効行は有効行の後へ並べる表示にした。
- 講師個別登録にメール欄を追加していない。
- アンケートを「回答ファイルを選ぶ→内容を確認する→反映完了」の3段階表示にし、
  列設定は通常非表示にした。既存のpreview、validation、transaction反映を維持した。

### Stage 3 — 集団授業

- 既定表示を月曜始まりの週カレンダーにした。
- 前週、基準週、次週を移動でき、開講日の空き列または上部buttonから予定を追加できる。
- 予定カードに時間、学年、科目、講師を表示し、選択時に詳細と削除導線を表示する。
- Excel取込み・差分タブ、区間重複検証、既存作成・削除slotを維持した。

### Stage 4 — 時間割と警告

- 左を未配置授業、中央を時間割、右を詳細・差分・履歴とする3ペインにした。
- 左の未配置カードは従来と同じlesson payloadと`dropMove`検証へ接続した。
- ロック、Undo/Redo、保存状態、再最適化、監査履歴への配線は変更していない。
- 入力検証の各行へ、対象種別に応じた修正画面を開くbuttonを追加した。

### Stage 5 — 出力

- 「出力対象→形式→保存先」の順序を画面上で明示した。
- 未配置件数を警告し、未配置・警告画面へ移動できるようにした。
- 用紙等の詳細設定を通常は閉じた状態にした。
- 出力後に保存先フォルダーを開く選択肢と、直近の保存先を開くbuttonを追加した。
- Python側の唯一の機能追加は、OS標準のフォルダー表示だけを担当する
  `OutputViewModel.openLastOutputFolder`である。出力サービスとrendererは未変更である。

### Stage 6 — QA・文書

- 新しい導線を守るQML契約テストと、日本語パスのフォルダー表示テストを追加した。
- README、利用者マニュアル、開発者ガイドを刷新UIに合わせた。
- 個人情報を読み込まない状態でafter screenshotを取得した。
- 全体回帰、lint、型検査、QML lint、DPI別起動を実行した。

## 3. 新規QML component

- `UiTheme.qml`
- `AppButton.qml`
- `StatusBadge.qml`
- `InlineMessage.qml`
- `SectionHeader.qml`
- `EmptyState.qml`
- `StepCard.qml`
- `SidebarNavButton.qml`

## 4. 保護contractに対する変更

変更なし:

- DB schema / migration head `20260807_0007`
- `.jukuschedule`の保存・再読込み
- SQLAlchemy repository / transaction境界
- OR-Toolsのハード制約、ソフト制約、辞書式目的関数、timeout処理
- DnDのpreviewとcommit直前の二重検証
- lock、Undo/Redo、AuditLog、自動保存、再最適化
- Excel/PDF/CSVのsnapshot、layout model、renderer、原子的保存
- アンケート・マスターExcelの検証後反映

追加したPython APIはPresentation convenienceの`openLastOutputFolder`のみである。

## 5. 発生し解消した回帰

- 集団授業画面の説明変更で既存QML契約文字列「区間重複」が失われ、Stage 3 testが1件
  失敗した。意味を保った説明へ戻し、同じtestを再実行して23件成功した。
- 新規`InlineMessage`利用時にproperty名を誤った箇所をQML lintが検出した。
  component契約の`kind`/`message`へ修正した。
- 新規回帰テスト自身の初期期待値とWindows path separatorを修正した。製品コードを
  testに合わせて弱める変更は行っていない。

baseline failureは0件だった。testのskip/xfail化、削除、弱体化は行っていない。

## 6. BLOCKED / 未完了

1. **集団授業の既存予定をその場で上書き編集**: 現行Application Serviceには監査付きの
   update APIがなく、UI都合でdelete+createを暗黙実行すると識別子・受講者・監査の意味を
   変える危険がある。そのため詳細確認と明示削除後の再登録までを実装し、直接更新は
   BLOCKEDとした。
2. **警告から特定時間割セルへの完全なjump**: すべてのvalidation issue DTOに
   date/slot/teacherの組が存在しない。安全に特定できる対象画面へのjumpを実装し、曖昧な
   issueを推測でセル選択する処理はBLOCKEDとした。
3. Windows 10/11実機での全画面keyboard操作、実モニターの125/150%、実Excel/PDF viewer、
   実在する旧業務プロジェクトでの目視確認は手動受入が残る。自動回帰とoffscreen DPI起動は
   成功している。

## 7. before / after

| Before | After |
|---|---|
| [`docs/images/main-window-home.png`](../images/main-window-home.png) | [`screenshots/ui_after_home_1366x768.png`](screenshots/ui_after_home_1366x768.png) |

## 8. 変更ファイル

### UI

- `src/summer_scheduler/ui/qml/{Main,Sidebar,ProjectHomePage}.qml`
- `src/summer_scheduler/ui/qml/{StudentPage,TeacherPage,AvailabilityImportPage}.qml`
- `src/summer_scheduler/ui/qml/{GroupLessonPage,ScheduleEditorPage,ValidationIssuesPage}.qml`
- `src/summer_scheduler/ui/qml/OutputPage.qml`
- `src/summer_scheduler/ui/qml/{DashboardCard,StatusBanner}.qml`
- 上記8個の新規共通QML component

### Python / tests

- `src/summer_scheduler/ui/viewmodels/output_view_model.py`
- `tests/unit/test_ui_redesign_contract.py`
- `tests/integration/test_output_view_model.py`

### 文書・安全設定

- `.gitignore`
- `README.md`
- `docs/user_manual.md`
- `docs/developer_guide.md`
- `docs/ui_redesign/current_state_inventory.md`
- `docs/ui_redesign/protected_contracts.md`
- `docs/ui_redesign/implementation_report.md`
- `docs/ui_redesign/regression_report.md`
- `docs/ui_redesign/screenshots/*`

Codex向けprompt、wireframe、作業指示と第三者サービスのreference画像はローカルで確認したが、
製品に不要であり公開再配布もしないためGit除外した。
