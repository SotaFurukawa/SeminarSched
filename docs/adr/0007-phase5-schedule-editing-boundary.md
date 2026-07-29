# ADR 0007: 時間割編集を不変preview・transaction・fingerprint境界に置く

- 状態: 採用・Phase 5実装済み
- 日付: 2026-07-29
- 対象: Phase 5の時間割表示、手動編集、ロック、Undo / Redo、差分、再最適化

## コンテキスト

Phase 4は、ハード制約を満たすAssignmentと未配置sessionを独立validatorで確認してから
保存できる。しかしPhase 5の手動編集では、利用者がカードを別日・別コマ・別講師へ
動かすたびに、Phase 4と同じハード制約を即時検査する必要がある。

QML側へ制約を複製すると、自動最適化では拒否される配置を手動編集だけが保存する
危険がある。drag entered時のpreviewだけを信頼すると、preview後にDBが変化した場合に
古い判断を適用する。操作ごとの自動保存とUndo / Redoを両立するには、逆操作が
現在DBの別変更を上書きしない仕組みも必要である。

対象規模は講師40名×5コマ×複数日である。全日・全セル・全カードを重いQML Itemとして
同時に作る設計は、スクロール、日付切替、DPI環境でUIを固める可能性がある。

## 決定

### 1. 時間割ボードを不変DTOとして一括取得する

`ScheduleEditService.load_board()`は短いSQLAlchemy Session内で、日付、コマ、講師、
Assignment、LessonRequest、集団授業、未配置session、AuditLog、差分を読み取る。
Session外へはORM objectではなく、`ScheduleBoardDto`とその子DTOだけを返す。

```text
SQLite / SQLAlchemy
  → ScheduleEditService
  → ScheduleBoardDto
  → ScheduleEditorViewModel
  → QAbstractTableModel / QML
```

`ScheduleGridModel`は`QAbstractTableModel`を使い、現在日だけをコマ行×講師列として
materializeする。QMLは`TableView`、`HorizontalHeaderView`、
`VerticalHeaderView`とdelegate reuseを使う。複数日は全グリッドではなく、配置、
1対2、集団授業、警告、ロック件数の軽量summaryとして表示する。

前日／翌日、日付タブ、カレンダーで日付を選べる。日付タブは同じ講師・コマの別日へ
移すdrop targetにもする。

### 2. Phase 4の独立validatorを手動編集の正本として再利用する

`optimization/manual_edit.py`へ、UI、ORM、CP-SAT solverに依存しない次の不変型を置く。

- `EditSchedule`: 配置と未配置で全sessionを一度ずつ表すsnapshot
- `EditOperation`: `move / assign_unassigned / unassign`
- `EditTarget`: 日付、コマID、講師ID
- `EditPreview`: green / yellow / red、安定code、説明、前後schedule、issue、soft差分

previewは現在の`EditSchedule`を先に
`validate_optimization_result()`で検証する。現在状態が完全partitionでない場合や、
既にハード制約を破っている場合、編集で上書きして正常扱いしない。

操作を不変snapshotへ仮適用した後も、Phase 4と同じ候補集合と独立validatorで次を含む
全ハード制約を再検査する。

- 開校日、有効コマ、生徒・講師availability、講師資格
- 生徒重複、同一講師・同一コマ最大2名、1対1必須
- 優先度5、集団授業、ロック済みAssignment
- 生徒連続上限、生徒・講師の空きコマ
- session過不足と候補一致

red判定を適用する管理者強制経路は実装しない。将来追加する場合も、ハード制約を
ソフト化せず、マスター仕様との整合、明示確認、理由、AuditLogを新しいADRで定める。

### 3. green / yellow / redを色以外でも示す

- green: ハード制約を満たし、悪化するソフト条件がない
- yellow: ハード制約を満たすが、1つ以上のソフト条件が悪化する
- red: 操作不正、現在状態不正、候補外、またはハード制約違反

QMLは色だけでなく、アイコン、安定したpreview / issue code、日本語説明を表示する。

yellowでは、次の前後値、評価方向、改善／不変／悪化を返す。

- 未配置数
- 通常担当講師からの乖離
- 第1～第3希望講師からの乖離
- 生徒・講師の希望日時
- 1対2枠数
- 稼働講師×日付×コマ数
- 既存Assignmentからの変更数

利用者が悪化内容を確認し、理由を入力した場合だけ適用する。未配置数の増加もyellowの
明示確認対象であり、ハード制約を破って無理に配置することはない。

### 4. previewと保存で同じ検証を再実行する

drag entered時のpreviewは表示だけに使う。dropまたは詳細編集の適用時は、
`ScheduleEditService`がtransaction内で現在DBからOptimizationInput、候補、
EditScheduleを再構築し、同じ`preview_edit()`を再実行する。

画面が保持するfingerprintと現在DBが一致しない場合は、変更を拒否して再読込みを
要求する。preview結果だけを信頼して古い状態へ保存しない。

### 5. AssignmentとAuditLogを1トランザクションで自動保存する

操作ごとにAssignmentの作成・更新・削除とAuditLog追記を同じSQLAlchemy
transactionで行う。途中エラーは全体をrollbackし、日本語エラーを表示する。
エラーを握り潰して保存済みと表示しない。

未配置はAssignment行を作らず、Phase 4の必要session集合から再構築する。偽の
未配置Assignmentや別の重複tableは追加しない。

Alembic revision `20260729_0005`で次を追加する。

- `assignments.note`: 任意の授業備考
- `audit_logs.reason`: 任意理由。Phase 5の手動操作ではApplication Serviceが必須化
- `audit_logs.source`: `system / manual / automatic / undo / redo / import`
- `audit_logs.operation_id_optional`: 元操作とUndo / Redoを関連付ける任意ID
- `(project_id, operation_id_optional)`の検索index

既存AuditLogはserver default `system`でupgradeし、Phase 3の取込み監査を壊さない。

「手動保存」は、操作ごとに即時保存されたDBをSQLite backup APIで整合した明示保存点へ
複製する。未保存キューを後でcommitする方式にはしない。保存先と、backupに個人情報が
含まれ得る旨を日本語表示する。通常の手動保存は再最適化の差分baselineを変更しない。
詳細dialog編集中、yellow確認待ち、保存処理中、保存失敗・未反映、自動保存済みを
実状態から区別して表示する。失敗時はrollback済みの日本語エラーも表示する。

別processでSQLite transactionを開始し、未commitのAssignmentとAuditLogを書いた後に
`os._exit()`する結合テストを設ける。最後にcommit済みのAssignment / AuditLogだけが
再接続後に残り、未commitの両方がrollbackされることを確認する。これは即時保存の
crash-consistencyであり、起動時に複数backupから復旧候補を選ぶUIや自動backup世代管理
とは区別する。

### 6. Undo / Redoはfingerprint付きprocess内command stackとする

各commandは次を持つ。

- 対象LessonRequest IDとsession index
- before / after Assignment snapshot
- before / after schedule fingerprint
- action、理由、operation ID
- 前後差分

Undo前は現在fingerprintとcommandのafter、Redo前はcommandのbeforeが一致することを
要求する。対象Assignmentのsnapshotも一致する場合だけ逆操作を同じtransactionで
保存する。逆操作は`source=undo / redo`としてAuditLogへ追記し、元操作と同じ
operation IDを使用する。

command stackはprocess内だけに保持する。再起動、明示再読込み、プロジェクト切替、
fingerprintの異なる外部変更では破棄する。永続AuditLogを起動時にcommandとして
自動再生しない。監査履歴と安全な逆操作の責務を分ける。

### 7. 差分をsession単位で分類する

`optimization/schedule_diff.py`は前後scheduleをsession keyで比較し、次を安定codeで
返す。

- 新規配置
- 日時変更
- 講師変更
- 未配置化
- 1対1／1対2のpairing size変化
- 変更なし

手動操作直後は直前操作前後、再最適化ではcheckpoint前後を表示する。差分は
Assignmentの承認を遅延するshadow copyではなく、即時保存済み状態の説明に使う。

### 8. 授業単位ロックとロック以外の全体再最適化を実装する

Phase 5の必須範囲として授業単位ロック／解除を実装する。ロック済みAssignmentの
手動移動・未配置化を拒否し、解除は明示操作とAuditLogを伴う。

「ロック以外を全体再最適化」は次の既存境界を組み合わせる。

1. 配置数、ロック数、手動変更数、未配置数、fingerprintを表示する。
2. `ProjectService.backup()`でSQLite checkpointを作る。
3. 同じ「時間割」内のPhase 4 `OptimizationPage`へ移動する。
4. Phase 4 optimizerがロック済みAssignmentをハード制約として保持する。
5. 非中止の独立検証済み`OPTIMAL` / `FEASIBLE`だけを保存する。
6. 編集画面を再読込みし、checkpoint前後の差分を表示する。

checkpoint作成に失敗した場合は最適化画面へ進まない。選択日、選択生徒、選択講師
周辺だけの部分再最適化は、安全な境界が確定するまで提供しない。

## 根拠

- Phase 4のvalidatorを唯一の正本として再利用すると、自動配置と手動編集の
  ハード制約解釈を一致させられる。
- previewとtransaction内再検証を分けることで、操作性とTOCTOU対策を両立できる。
- 不変DTOとQAbstractTableModelにより、QMLへORM、Session、候補生成を漏らさず、
  当日分だけを効率よく表示できる。
- AssignmentとAuditLogの同一transactionにより、変更だけ、または監査だけが残る
  部分成功を防げる。
- fingerprint付きcommandにより、Undo / Redoが再最適化や外部変更を上書きすることを
  防げる。
- Phase 4のlockとsolverを再利用し、弱い別solverや偽の部分再最適化を追加しない。

## 影響

良い影響:

- GUIなしで手動編集の全ハード制約、soft差分、schedule差分をテストできる。
- hard rejection、soft confirmation、保存失敗が安定codeと日本語説明を持つ。
- Undo / Redo、監査、自動保存の整合性をtransaction testで検証できる。
- 40講師×5コマでも現在日の200 modelセルだけをmaterializeできる。
- 再最適化前のbackupとロック保持を既存の安全境界へ接続できる。

注意点:

- command stackは再起動をまたがない。監査ログは残るが、監査ログから任意の過去状態へ
  自動復元する機能ではない。
- 手動保存点とtransactionの異常終了rollbackはあるが、自動backup世代管理、
  backupから選ぶ復元UI、起動時の復旧候補UIはない。
- セル、日付、講師、選択範囲の一括lockは未実装である。
- 選択日、生徒、講師周辺だけの部分再最適化は未実装である。
- 即時保存後の差分は説明用であり、「承認するまでDBを変更しない」draft方式ではない。
- Windows実機のTableView描画、DPI、キーボード、長時間操作は自動model testだけでは
  保証できず、手動確認を別に行う。
- backup、AuditLog、Assignmentには個人情報が含まれ得るため、Git、CI artifact、
  issue、チャット、外部サービスへ送らない。

## 採用しなかった案

- QML JavaScriptへハード制約を複製する: Phase 4と判定がずれ、GUIなしテストと
  レイヤー分離を損なう。
- red判定を管理者確認だけで強制適用する: ハード制約違反を保存し得るため採用しない。
- preview結果を保存時に再検証しない: DB変更後の古い判断を適用し得る。
- AssignmentとAuditLogを別々にcommitする: 部分成功で監査または変更が欠落する。
- Undo / Redoをfingerprintなしで逆SQLとして実行する: 外部変更を上書きし得る。
- AuditLogを起動時にすべてcommandへ復元する: migration以前の監査、取込み監査、
  分岐した履歴を安全な逆操作として解釈できない。
- 全日×全講師×全コマをQML Itemへ常時展開する: 対象規模で描画負荷が増える。
- Phase 5専用の再最適化solverを作る: Phase 4のハード制約・status・保存安全弁を
  重複させる。
- 部分再最適化を全体再最適化のfilter表示だけで完成扱いする: 対象外Assignmentの
  保持を保証しないため採用しない。

## 検証方針

自動テストでは次を確認する。

- 正常移動、未配置から配置、配置から未配置、1名枠から2名枠
- availability、資格、優先度5、最大2名、1対1、集団授業、ロック、連続上限、
  生徒・講師の空きコマ等のhard rejection
- green / yellow / red、安定code、soft前後値と評価方向
- 同じpreviewのtransaction内再検証、fingerprint競合、rollback
- AssignmentとAuditLogの同時保存、理由、source、operation ID
- SQLite backupによる通常の手動保存点、個人情報注意、保存先表示
- 別processの`os._exit()`後にcommit済みAssignment / AuditLogだけを復元し、
  未commitの両方をrollbackするcrash-consistency
- move、lock、unassign、assign、pairing変更のUndo / Redo
- 新規配置、日時、講師、未配置、pairing、変更なしの差分
- checkpoint、ロック数・未配置数、再最適化後のlock保持
- revision `20260729_0005`のupgrade / downgrade / ORM schema一致
- 40講師×5コマ×20日・1,000カードで現在日200セルだけをmaterializeし、構築と
  日付・filter反復をそれぞれ5秒未満とするmodel回帰
- QML contract、qmllint、offscreen起動と時間割ページ生成

Windows実機のDnD、色以外の表示、DPI、キーボード、保存失敗、再最適化、監査、
40講師×5コマの描画は
[`manual_test_phase5.md`](../manual_test_phase5.md)で確認する。

Phase 6のExcel / PDF出力を、このADRの検証済み範囲へ含めない。
