# 夏期講習時間割作成アプリ 公開仕様

## 1. この文書の位置づけ

この文書は、公開版の業務要件、機能範囲、最適化制約と非機能要件をまとめた
プロジェクト仕様である。実装、テスト、README、開発者ガイド、ADRはこの文書に定める
ハード制約やデータ安全性要件を省略・緩和できない。

仕様と実装文書の役割は次のとおりとする。

1. `docs/specification.md` — 公開版の業務・機能・制約仕様
2. `docs/adr/` — 仕様を実現するための主要な技術判断
3. `docs/developer_guide.md` — 現在の実装構造と開発・検証手順
4. `README.md`と`docs/user_manual.md` — 導入・操作手順

仕様から合理的に決められない重要事項は、IssueまたはADRで影響と判断を記録する。
ハード制約を実装上の都合でソフトな減点へ変更してはならない。

## 2. 実装済みのスコープ

Phase 0からPhase 7までの段階的な開発項目を実装し、現在は`1.0.0-rc.3`の
リリース候補である。正式な署名済みWindows Releaseは未公開である。

### Phase 0：設計

- 技術選定の確定と ADR
- レイヤー構造とディレクトリ構成
- 初期 ER 設計
- 将来実装する最適化の変数、ハード制約、ソフト制約、辞書式目的の設計
- 画面遷移
- Phase 1 の実装計画
- リスクと未決事項の整理

設計対象には後続Phaseの拡張境界も含むが、コードとしての先行実装は行わない。

### Phase 1：アプリの土台

- Python 3.12 系を基準にした `src` レイアウトとパッケージ設定
- PySide6 / Qt Quick / QML による Windows 向けローカルデスクトップアプリ
- `python -m summer_scheduler` による起動
- 日本語タイトルのメインウィンドウ
- 次の 9 項目を持つ QML サイドバー
  - ホーム
  - 生徒
  - 講師
  - 集団授業
  - アンケート取込み
  - 時間割
  - 未配置・警告
  - 出力
  - 設定
- ホームの仮ダッシュボードと、未実装機能のプレースホルダー
- 初回起動時の SQLite データベース作成
- SQLAlchemy 2 系による接続基盤
- Alembic によるマイグレーション方針
- ローカルログ
- 内蔵既定設定と利用者設定の読込み
- pytest、Ruff、mypy の設定
- GitHub Actions による lint、型検査、test
- Windows での開発環境構築、起動、検査手順の文書化
- 実データ、DB、ログ、入力ファイル、出力ファイルを Git に含めない運用

Phase 1で作った画面シェルと基盤はPhase 2でも維持する。

### Phase 2：マスター管理

- `.jukuschedule`プロジェクトの新規作成、開く、最近使用した一覧
- プロジェクト情報の編集、別名保存、複製、バックアップ、クローズ
- アプリ管理DBと、1ファイル1SQLiteのプロジェクトDBの分離
- Campus、CourseProject、TimeSlot、OpenDate、Student、Teacher、Subject、
  TeacherQualification、LessonRequestのDBモデルとAlembic migration
- 既定5コマと、重複・時刻範囲・時刻区間重複等の検証
- 講習期間内の開校日・休校日・備考、一括開校、曜日休校、選択日変更
- 小学校5、中学校5、高校13区分、合計23科目の初期登録
- 生徒・講師の一覧、部分一致検索、追加、編集、使用停止、削除確認
- 講師×科目の指導可否と一括操作
- 生徒×科目のLessonRequestと優先度・講師参照等の検証
- `master_data.xlsx`の5シート出力、再取込み、行単位検証、プレビュー、
  新規／更新件数、確認後のtransaction反映、失敗時rollback
- 日本語名、日本語ファイル名、Windowsパスを含む自動・手動確認

Phase 2では「生徒」「講師」「設定」を実画面へ置き換えた。Phase 3で「集団授業」
「アンケート取込み」「未配置・警告」、Phase 4で簡易最適化、Phase 5で時間割編集、
Phase 6で「出力」を実画面へ置き換えた。

### Phase 3：アンケート・集団授業・入力検証

- StudentAvailability、TeacherAvailability、GroupLesson、GroupLessonStudent、
  ImportBatch、ValidationIssue、AuditLogとAlembic revision `20260728_0003`
- 生徒・講師availabilityのxlsxテンプレート、xlsx / UTF-8 / CP932 CSV読取り
- シート、文字コード、列マッピング、先頭プレビュー、行検証、セル差分
- 追加、変更、変更なし、削除候補と、利用者が明示した場合だけの削除
- アンケートから通常担当、優先度5、1対1契約を変更させない保護
- 集団授業と受講者の2シートテンプレート・取込み
- 任意時刻を半開区間として扱う講師・生徒衝突判定
- 反映直前の再読込み・再検証、業務データ・ImportBatch・AuditLogの
  1トランザクション保存とrollback
- 保存済みプロジェクト全体の入力検証とValidationIssue更新
- 架空名だけの匿名サンプルプロジェクト生成

Phase 3の全体検証は、現時点でDBに表現できるマスター、availability、集団授業を
対象とする。Assignmentが存在して初めて検査可能になる「1対1必須の割当矛盾」、
「固定授業同士の重複」、「集団授業と固定授業の衝突」は、Phase 4でAssignmentを
追加した際に同じ検証サービスへ接続し、最適化開始前のエラーとした。Phase 3時点で
Assignmentの仮モデルや偽の検証結果を追加しなかった方針は維持している。

### Phase 4：時間割最適化

- ORM、SQLAlchemy Session、QML、OR-Toolsから独立した`frozen`最適化DTO
- 必要回数の1始まりsession展開と、version付き正規化JSON snapshot
- 開校日、有効コマ、availability、資格、優先度5、任意時刻の集団授業、
  ロック済みAssignmentを用いた疎な候補生成
- 各sessionの配置または未配置、生徒重複禁止、講師最大2名、1対1必須、固定、
  集団授業、生徒連続上限、生徒・講師の空きコマ禁止をCP-SATのハード制約として実装
- 未配置、講師希望、稼働講師枠、希望日時、既存割当変更、任意の負荷調整の順による
  複数Solveの辞書式最適化
- 独立検証済みgreedy初期解、全非固定変数complete hint、occupancy単位の制約集約
- 全段階で共有する単一deadlineと、`OPTIMAL`の目的値だけを固定する安全規則
- incumbent cutoff、5秒の次段開始閾値、最大3秒の返却余白と、
  `UNKNOWN`等でsolver valueを読まないsnapshot管理
- 候補除外理由と解後競合による未配置診断、solverから独立した結果validator
- QThread worker、`CancellationToken`、`CpSolver.stop_search()`による協調的中断
- 高速30秒、標準120秒、高品質600秒の設定プリセット
- Assignment、OptimizationRun、Alembic revision `20260728_0004`
- 入力fingerprintの保存前再照合、旧Assignmentを含む結果snapshot、履歴更新と
  Assignment置換の単一transaction
- 一般ログ配下の隔離ディレクトリに作るrun固有のUTF-8最適化ログと、
  `OptimizationRun.log_path_optional`による保存先履歴
- solver status、配置・未配置、経過時間、目的内訳、理由、警告、ログ保存先を扱う
  簡易最適化画面

Phase 4では、ハード制約を目的関数のpenaltyへ変更しない。制約を満たせない授業は
未配置とし、非中止の`OPTIMAL`または`FEASIBLE`で、独立validatorを通過した結果だけを
保存する。入力変更、キャンセル、非実行可能status、validator違反、保存失敗では
現在のAssignmentを変更しない。

候補生成とmodel構築にもSolveと同じ単一deadlineを適用する。期限到達時はsolverの
未保証valueを読まず、独立検証済みincumbentがあれば`FEASIBLE`として復帰し、
なければ`UNKNOWN`としてAssignmentなしで終了する。

マスター仕様27章の初期規模を通常経路・高速30秒で実測し、候補73,440件、
独立候補生成3.369秒、end-to-end 27.179秒（solver報告27.015秒）、
status `FEASIBLE`、配置1,042件／未配置8件、時間内判定`true`を確認した。
全benchmark 30.595秒は候補生成単独とend-to-endの二重測定である。高速presetで
実用的な`FEASIBLE`を返す性能目標は満たすが、標準presetを含め全段階の`OPTIMAL`
完了は保証しない。`tracemalloc`は`--trace-memory`指定時の参考測定だけに用い、
性能合否には使わない。

同規模の標準120秒正式測定は、独立候補生成3.451292秒、
end-to-end 117.939982秒（solver報告117.765秒）、status `FEASIBLE`、
配置1,042件／未配置8件、警告1件、時間内判定`true`だった。
全benchmark 121.440812秒は候補生成単独とend-to-endの二重測定であり、
標準presetでも全段階の`OPTIMAL`完了は保証しない。

### Phase 5：時間割表示・手動編集・固定・再最適化

- ORM、QML、solverから独立した`EditSchedule`、`EditOperation`、`EditPreview`と、
  Phase 4の独立result validatorを再利用する手動編集preview
- 配置済み・未配置の全session partitionを編集前後で検証し、壊れた現在状態や
  ハード制約違反を赤判定で拒否する境界。管理者強制経路は設けない
- 通常担当、希望講師、希望日時、1対2、稼働講師枠、既存配置、未配置数のソフト評価を
  前後比較し、悪化時は黄判定と理由付き確認を要求
- 日付、コマ、講師、カード、集団授業、未配置、監査、差分を一括読取りする不変DTO
- 当日分だけを5行×講師列として保持する`QAbstractTableModel`と、delegateを再利用する
  QML `TableView`。全日・全セルを同時に重いItemへ展開しない
- 前日／翌日、日付タブ、カレンダー、日表示、複数日サマリー、拡大縮小、検索・絞込み
- 生徒名、学年、科目、1対1、優先度5、ロック、手動変更、警告の授業カードと、
  任意時刻の集団授業を重複コマへ表示するブロック
- 配置済みカード、未配置カード、日付タブを含むドラッグ＆ドロップと、
  緑／黄／赤にアイコン・判定コード・日本語説明を併記するpreview
- 日付・コマ・講師・ロック・備考の詳細編集、配置から未配置、未配置から配置
- 授業単位のロック／解除。ロック済みAssignmentの移動・未配置化と、再最適化での
  変更を禁止
- AssignmentとAuditLogを同じSQLAlchemy transactionへ保存し、失敗時にrollbackする
  操作後の自動保存
- 即時保存済みDBをSQLite backup APIで複製する手動保存点と、保存先・個人情報注意の
  日本語表示
- fingerprint付きプロセス内command stackによるUndo / Redo。元操作と逆操作を
  operation IDで関連付け、外部変更検出時は古い履歴を適用しない
- 新規配置、日時変更、講師変更、未配置化、1対1／1対2変化、変更なしを区別する差分
- 対象配置数、ロック数、未配置数を確認し、SQLite backup checkpoint作成後に
  Phase 4の最適化画面へ進む「ロック以外を全体再最適化」
- Assignment備考、AuditLogの理由・操作元・operation IDとAlembic revision
  `20260729_0005`

Phase 5でもハード制約をソフト警告へ落とさない。ドラッグ前previewとtransaction内の
再検証は同じPython境界を使用する。QMLはIDと表示状態だけをViewModelへ渡し、DB操作、
候補生成、制約判定、監査保存を直接行わない。

手動保存は即時保存済みDBを整合したSQLite backupへ複製する明示保存点である。
未保存キューを後からcommitする意味ではない。別processの強制終了を使う結合テストで、
commit済みAssignment / AuditLogだけが再起動後に残り、未commitの両方がrollbackされる
ことを確認する。Undo / Redoのcommand stackはプロセス内だけであり、再起動、
明示再読込み、プロジェクト切替、fingerprintの異なる外部変更では安全のため破棄する。
監査ログはプロジェクトDBへ残る。

40講師×5コマ×20日、1,000カードの架空読み取りモデルを使う自動テストでは、当日に
materializeするmodelセルを200件に限定し、構築と20日分の日付切替・filter操作を
それぞれ5秒未満とする回帰条件を通過している。Windows実機の描画・DPI・入力応答は
[`manual_test_phase5.md`](manual_test_phase5.md)で別途確認する。

### Phase 6：Excel・PDF・個人別出力

- ORMやQMLに依存しない`OutputSnapshot`、`OutputSettings`、`OutputSelection`と、
  Excel / PDFで共有する不変な`LayoutDocument`
- 最新DBからプロジェクト、日付、コマ、人物、科目、受講希望、Assignment、集団授業、
  警告を一括読取りする`OutputRepository`
- 実出力ごとの入力再検証、現在の全session partition再構築、Phase 4のsolverから
  独立したresult validatorによるハード制約・参照整合性の確認
- 日付数と講師列数で物理ページ分割する全体時間割。日付、コマ／時刻、講師、
  最大2名分の生徒名・学年・科目、1対1、集団、休校、ロック、手動変更、警告、
  未確定、凡例、校舎、講習名、更新日時、ページ番号を扱う
- 生徒別時間割の1人1ページ／複数人まとめ、講師別時間割の連続勤務範囲・合計稼働、
  未配置一覧と警告一覧
- 現在の他Assignmentを動かさず対象1sessionだけを仮追加し、独立validatorを通った
  最大3件だけを「単独配置可」とする未配置解決候補
- openpyxlによる編集可能なExcel。A3 / A4、縦横、罫線、結合、印刷範囲、
  改ページ、繰り返し文書見出し、折返し、縮小表示、ヘッダー／フッター、ページ番号
- Qt `QTextDocument` / `QPdfWriter`によるローカルPDFと、`QPdfDocument`による
  生成後のサイズ・ページ数・寸法検証
- 保存用と同じ一時PDFを`QtQuick.Pdf`で表示する、ページ送り、50～300%拡大縮小、
  幅合わせ、全体表示付き印刷プレビュー
- マスター仕様の18列を持つUTF-8 CSV、BOM有無、個別Assignmentと集団授業、
  表計算ソフトの数式注入候補に対する文字列保護
- 日付、講師、生徒の出力対象選択
- 用紙、向き、表示項目、日数、講師列数、文字、余白、ファイル名規則、既定保存先、
  生徒別改ページ、BOM、色・文字マーカー、校舎ロゴの設定と再読込み
- プロジェクトと1対1の`output_settings`、校舎ロゴを正本とする既存Campus、
  Alembic revision `20260729_0006`
- 同一ディレクトリの一時ファイル、明示上書き確認、成功後だけの`os.replace`、
  権限・lock・描画失敗時の既存ファイル保持
- QThread worker、プロジェクト切替guard、一時プレビューの終了時cleanup

Phase 6でも、出力のためにハード制約を警告へ落とさない。画面読込み後にDBが変わっても、
実際のExcel、PDF、CSVは現在DBを再読込みし、独立validatorを通過したsnapshotだけを
使う。不正な現在状態、参照欠落、読めない縮尺のPDF、保存失敗を成功扱いしない。

色設定には文字マーカーを必須とし、モノクロ印刷でも1対1、集団、ロック、警告、
未確定、手動変更、休校を区別できる。校舎ロゴはPDFヘッダーへ埋め込む。
Phase 6のExcelには画像を埋め込まない。

PDFとExcelの共通レイアウト、Qt選定、原子的保存、安全検証の判断は
[`ADR 0008`](adr/0008-common-layout-and-safe-local-output.md)、Windows実機確認は
[`manual_test_phase6.md`](manual_test_phase6.md)を参照する。

### Phase 7：品質保証・バックアップ・Windows配布

- app version `1.0.0-rc.3`をpackage metadata、Qt application、About、log、帳票へ
  表示し、Alembic schema revisionとは別の版として扱う
- project open直後と設定間隔ごとの自動backup。既定5分間隔・project別5世代で、
  `%LOCALAPPDATA%\SummerScheduler\backups`へ保存する
- `PRAGMA integrity_check`、必須table、書込み／lock probeによるopen前の安全確認
- 正常close時だけ消すrecovery session markerと、異常終了／open失敗後の復旧候補
- 選択backupを一時copyしてintegrityとmigrationを検証し、現在projectの
  `pre_restore`退避に成功した場合だけ原子的に置換する復元
- `ENOSPC`、`EACCES`、OneDrive等のlock、`ENAMETOOLONG`を握り潰さない日本語エラー
- `pyside6-deploy`とNuitka 4.0によるWindows x64 standalone treeを正本とし、
  同じtreeからportable ZIPとInno Setup installerを作る配布境界
- QML、Qt module／plugin、SQLite、OR-Tools、Alembic revision、YAML、
  runtime licenseの同梱検証と、実DB・log・input／output／backupの混入拒否
- Semantic Versioning、決定的portable archive、installer、SHA-256、
  品質gate後だけartifactを作るrelease workflow
- 匿名目標規模での30／120／600秒solver測定と、起動、読込み、一覧、xlsx取込み、
  入力検証、最適化、時間割読込み、Excel／PDF、process peak memoryの通し測定
- 利用者manual、troubleshooting、性能記録、受入表、release checklist、
  third-party license監査

QMLはbackup候補と復元操作を`WorkspaceViewModel`へ渡し、SQLiteを直接操作しない。
backupにも元projectと同じ個人情報が含まれることをホームへ明示する。技術的に
artifactを生成できることと、本番配布の権利・clean PC受入・公開承認は区別する。
project自身はGPL-3.0-onlyを採用した。Qt Community Editionの対応ソース・notice、
Inno Setup利用条件とSignPath署名対象の適格性が確認されるまで、署名済み本番
GitHub Releaseを公開しない。

安全な復旧は[`ADR 0009`](adr/0009-project-backup-and-recovery-safety.md)、配布と
公開gateは
[`ADR 0010`](adr/0010-release-candidate-packaging-and-security-boundaries.md)を
参照する。実施済み／未実施の境界は
[`acceptance_test_phase7.md`](acceptance_test_phase7.md)を正本とする。

## 3. 今回実装しない範囲

次はPhase 7完了後の拡張、Phase 5 / 6の任意拡張、または所有者の明示判断へ残す。

- 選択日、選択生徒、選択講師周辺だけの部分再最適化
- セル、日付、講師、選択範囲単位の一括ロック
- Undo / Redo履歴のアプリ再起動をまたぐ復元
- Excelへのロゴ画像埋込み
- 指定された参考PDFとの直接比較、ピクセル単位の再現
- SignPathによる実署名（申請資料、署名境界、検証scriptまでは実装済み）
- Qt完成artifactの配布監査、SignPath承認、本番GitHub Releaseの公開
- Google API、クラウド同期その他、マスター仕様 33 章にある初期版の対象外機能

これらのためのパッケージ境界やインターフェース方針は設計するが、空のサービスや動作しない仮実装を大量に追加しない。

Phase 2のExcel機能はマスター情報5シート、Phase 3の入力は
`student_availability.xlsx`、`teacher_availability.xlsx`、CSV、集団授業、
列マッピングである。Phase 6の時間割Excel、個人別Excel、未配置・警告Excel、
生データCSVは`reporting/`と`infrastructure/exporting/`で扱う。名称が同じ
「Excel」であっても、入力テンプレート、マスターExcel、帳票出力を混同しない。

## 4. 制約の解釈

「ハード制約」と「ソフト制約」は混同しない。

- ハード制約は、時間割最適化で絶対に破ってはならない条件である。Phase 4では
  候補除外とCP-SAT制約として実装し、Phase 5では同じ候補集合と独立validatorで
  手動編集を検査する。満たせない授業は無理に配置せず未配置とする。
- ソフト制約は、すべてのハード制約を満たした解の間で品質を比較する目的である。優先順位はマスター仕様 18 章の辞書式順序に従う。
- 対象環境、プライバシー、レイヤー分離などのシステム要件も必須であるが、最適化モデル上の「ハード制約」とは区別して記述する。

具体的な分類と実装モデルは [`phase0_design.md`](phase0_design.md)、Phase 4で確定した
OR-Tools境界とstatus規則は
[`ADR 0004`](adr/0004-ortools-boundary-and-lexicographic-optimization.md)、Phase 5の
編集・自動保存・Undo / Redo境界は
[`ADR 0007`](adr/0007-phase5-schedule-editing-boundary.md)、Phase 6の出力直前検証、
共通帳票、原子的保存は
[`ADR 0008`](adr/0008-common-layout-and-safe-local-output.md)を参照する。

## 5. 業務上の参考資料の扱い

実在の時間割、PDF、Excel、画像その他の業務資料は個人情報を含む可能性があるため、
公開リポジトリ、Issue、CI artifact、テストfixture、配布物へ含めない。これらの資料が
なくてもアプリの起動、テスト、ビルド、帳票出力ができなければならない。

帳票では次の情報構造を提供する。特定の業務資料をピクセル単位で再現することは
目的としない。

- 校舎名、講習名、更新日時、帳票名、ページ番号
- 日付ごとのblock、コマと開始・終了時刻の縦並び、講師列
- 各講師・各コマの最大2名分の生徒名、学年、科目
- 1対1、集団授業、休校、ロック、手動変更、警告、未確定、凡例
- 生徒別、講師別、未配置、警告の独立帳票

参考資料固有の寸法、書体、配色、装飾、余白、注記位置は再現・検証していない。
可読性のため、日付数と講師列数で物理ページを先に分割し、担当未設定集団授業、
未配置、警告を別sectionにし、色へ文字マーカーを併記する。PDFが読める縮尺に
収まらない場合は極小文字にせず設定変更を要求する。

用紙、向き、1ページ当たり日数、講師列数、文字サイズ、余白、表示項目、色、
文字マーカー、生徒別改ページ、対象日／講師／生徒、校舎ロゴ、ファイル名規則、
既定保存先、CSV BOMを設定可能にした。ロゴはPDFヘッダーへ描画し、Phase 6の
Excelには画像を埋め込まない。

参考資料には個人情報が含まれる可能性があるため、Git へコミットしない。取扱いは [`docs/reference/README.md`](reference/README.md) に従う。

## 6. 仕様変更の扱い

仕様変更が必要になった場合は、次の順で扱う。

1. マスター仕様との不一致か、未決事項かを確認する。
2. ハード制約、ソフト制約、単なる実装詳細のどれかを明記する。
3. 重要な技術判断は ADR に記録する。
4. マスター仕様そのものを変更する場合は、明示的な合意のもとで行う。
5. 実装、テスト、README、仕様参照文書を同じ変更で整合させる。

Phase 7のsource自動品質gate、配布build、artifact検査、Windows実機の手動確認可能
項目を区別して記録する。source testやworkflow定義の成功を、clean Windows受入、
license承認、署名、本番GitHub Release公開の完了と解釈しない。
