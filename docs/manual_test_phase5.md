# Phase 5 手動確認手順

この手順は、Windows 10 / 11実機でPhase 4までの機能を回帰確認しながら、Phase 5の
時間割グリッド、ドラッグ＆ドロップ、即時検証、ロック、Undo / Redo、未配置、
詳細編集、差分、監査、自動保存、ロック以外の全体再最適化、DPI・キーボード・
40講師×5コマの操作性能を確認するためのものである。

仕様上の基準は[公開仕様](specification.md)、実装判断は
[ADR 0007](adr/0007-phase5-schedule-editing-boundary.md)である。

この手順だけでPhase 6のExcel / PDF出力やPhase 7の配布を確認済みと扱わない。
実行していない項目、条件を作れなかった制約、観察できなかった性能を成功と記録しない。

実在する生徒、講師、校舎、時間割を使用しない。確認用`.jukuschedule`、backup、
ログ、画面キャプチャにも個人情報を入れず、Git、issue、Pull Request、CI artifact、
チャット、外部サービスへ添付しない。

## 1. 前提と隔離した確認領域

[README.md](../README.md)の手順でPython 3.12の仮想環境と開発依存関係を準備する。
普段のアプリ管理DB、ログ、backupへ触れないよう、同じPowerShellプロセス内だけ
保存先を一時ディレクトリへ変更する。

```powershell
$phase5Root = Join-Path ([System.IO.Path]::GetTempPath()) ("SummerSchedulerPhase5-" + [guid]::NewGuid().ToString("N"))
$projectRoot = Join-Path $phase5Root "日本語 Phase5確認"
New-Item -ItemType Directory -Path $projectRoot

$env:SUMMER_SCHEDULER_DATA_DIR = Join-Path $phase5Root "data"
$env:SUMMER_SCHEDULER_LOG_DIR = Join-Path $phase5Root "logs"

$bootstrapProject = Join-Path $projectRoot "Phase5開始用_架空講習.jukuschedule"
$sampleProject = Join-Path $projectRoot "日本語 匿名編集サンプル.jukuschedule"
$failureProject = Join-Path $projectRoot "保存失敗確認用コピー.jukuschedule"
$env:PHASE5_PROJECT_PATH = $sampleProject

python -m summer_scheduler
```

PowerShellを閉じると、このプロセスに設定した環境変数は失われる。確認中は同じ
PowerShellからアプリを起動する。

## 2. 匿名プロジェクト、初期時間割、migration 0005

1. 「ホーム」→「新規プロジェクト」で次を入力し、`$bootstrapProject`へ保存する。

   | 項目 | 値 |
   |---|---|
   | プロジェクト名 | Phase5開始用 架空講習 |
   | 校舎名 | 架空確認校 |
   | 開始日 | 2026-08-03 |
   | 終了日 | 2026-08-07 |

2. 「未配置・警告」→「匿名サンプルを作成…」で`$sampleProject`を作る。
3. 「未配置・警告」でプロジェクト全体検証を実行する。
4. 意図的なwarningは表示されてもよいが、最適化を止めるerrorが0件であることを
   確認する。
5. 「時間割」→「ロック以外を再最適化」で件数を確認し、checkpoint作成後に
   最適化画面へ進む。
6. 高速presetで自動作成し、`OPTIMAL`または`FEASIBLE`で保存されることを確認する。
7. 「時間割編集へ戻る」でカードが表示されることを確認する。
8. 「ホーム」→「複製」で`$failureProject`を作る。保存失敗試験はこのコピーだけで
   行い、通常確認用と混同しない。

アプリを終了してから次を実行する。人物名や備考本文は表示せず、revisionと列名だけを
読み取る。

```powershell
@'
import os
import sqlite3
from pathlib import Path

path = Path(os.environ["PHASE5_PROJECT_PATH"]).resolve()
if not path.is_file():
    raise SystemExit(f"project not found: {path}")
with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assignment_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(assignments)")
    }
    audit_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(audit_logs)")
    }
print("revision=", None if revision is None else revision[0])
print("assignment_note=", "note" in assignment_columns)
print("audit_reason=", "reason" in audit_columns)
print("audit_source=", "source" in audit_columns)
print("audit_operation_id=", "operation_id_optional" in audit_columns)
'@ | python -
```

次を確認する。

- `revision=20260729_0005`
- `assignment_note=True`
- `audit_reason=True`
- `audit_source=True`
- `audit_operation_id=True`

ファイルが見つからない場合に別場所へ空DBを作らないよう、存在確認とread-only modeを
使用している。

## 3. 時間割画面と日付操作

同じPowerShellからアプリを再起動し、`$sampleProject`を開く。

1. サイドバーの「時間割」を選ぶ。
2. Phase 4だけの簡易結果画面やplaceholderではなく、「時間割編集」と次が表示される。

   - 保存状態
   - Undo / Redo
   - ロック以外を再最適化
   - 検索・絞込み・拡大縮小
   - 前日／翌日
   - カレンダー
   - 日表示／複数日サマリー
   - 日付タブ
   - コマ行×講師列
   - 未配置／詳細／差分／履歴

3. 行が有効なY/Z/A/B/Cを`sort_order`順、列が講師順であることを確認する。
4. 同一講師・同一コマにカードが0～2枚表示され、3枚目の表示領域を通常配置として
   作らないことを確認する。
5. 前日／翌日、日付タブ、カレンダーから同じ開校日へ移動できる。
6. 日付タブが横に収まらない場合もスクロールして期間末へ到達できる。
7. 「複数日サマリー」で日付ごとの配置、1対2、集団授業、警告、ロック件数を確認し、
   「日表示」へ戻れる。
8. 拡大縮小を75%～150%で動かしても、カード選択、scroll、drop targetがずれない。

空白画面、`scheduleEditorViewModel is not defined`、model roleのundefined、
delegate生成のruntime errorがある場合は後続項目を成功扱いせずBLOCKEDとして記録する。

## 4. カード、集団授業、詳細表示

配置済みカードを選択し、カードと詳細パネルを確認する。

- 生徒名
- 学年
- 科目略称
- 1対1
- 優先度5
- ロック
- 手動変更
- 警告

1対1、優先度5、ロック、手動変更、警告は、該当しないカードへ偽表示しない。
警告やロックは色だけでなく、文字またはアイコンでも判別できる。

ツールチップまたは詳細パネルで次を確認する。

- LessonRequestを識別できる授業・回数
- 通常担当講師
- 希望講師
- 生徒・講師の日時希望
- 最大連続数
- 生徒・講師の空きコマ設定
- 変更履歴
- 任意備考

集団授業は「集団」等の文字・アイコン付きで表示される。Y/Z/A/B/Cと完全一致しない
集団授業は、半開区間が重なる各コマの担当講師セルへ表示される。終了時刻と次コマの
開始が接するだけのコマへ余分に表示しない。

カードの右クリックまたはダブルクリックで詳細編集ダイアログが開く。生徒と科目を
別LessonRequestへ置換するUIになっていないことを確認する。

## 5. ドラッグ＆ドロップと3段階preview

同じ架空プロジェクトのコピーで、次を少なくとも1回ずつ操作する。

- 同じ日の別講師
- 同じ講師の別コマ
- 別講師・別コマ
- 日付タブへのdropによる別日
- 1名枠から、既に1名いる1対2可能枠
- 2名枠の一方を別枠
- 未配置パネルから空きセル

drop前にtargetの表示とpreview欄が更新されることを確認する。

| 判定 | 必須表示 | 動作 |
|---|---|---|
| green | 緑系表示、許可アイコン、配置可能の文字説明、安定code | dropで即時保存 |
| yellow | 黄系表示、警告アイコン、悪化理由、前後値 | 確認dialogへ進み、理由入力後だけ保存 |
| red | 赤系表示、拒否アイコン、ハード違反理由、issue code | dropしても保存しない |

色を判別しにくい表示設定でも、アイコン、文字説明、codeで3状態を区別できることを
確認する。赤の確認dialogから強制適用できる経路がないことを確認する。

## 6. ハード制約の即時拒否

確認用コピーのGUIで各条件を作り、対象カードを違反先へdragする。条件を作れない項目は
自動テスト結果で代用したとせず、手動結果を「未確認」とする。

| 制約 | 確認操作 | 期待結果 |
|---|---|---|
| 生徒可能日時 | 生徒availability 0の枠へ移動 | red、保存しない |
| 講師可能日時 | 講師availability 0の枠へ移動 | red、保存しない |
| 講師資格 | 科目を指導不可の講師へ移動 | red、保存しない |
| 生徒重複 | 同じ生徒の別授業と同一日時へ移動 | red、保存しない |
| 講師最大2名 | 既に2名の講師・コマへ3人目を移動 | red、保存しない |
| 1対1必須 | 1対1必須を含む枠へ別生徒を追加、または逆 | red、保存しない |
| 優先度5 | 通常担当以外の講師へ移動 | red、保存しない |
| ロック | ロック済みカードを移動または未配置化 | red、先に明示解除を案内 |
| 集団授業 | 受講生または担当講師が重なる枠へ移動 | red、保存しない |
| 生徒連続上限 | 通常生徒が3連続になる枠へ移動 | red、保存しない |
| 3コマ許可 | `max_consecutive_slots=3`の生徒を正当な3連続へ移動 | hard理由では拒否しない |
| 生徒空きコマ | `allow_gap=false`の生徒がAC等になる移動 | red、保存しない |
| 講師空きコマ | `allow_gap=false`の講師がAC等になる移動 | red、保存しない |
| 休校日 | 休校日の日付タブへ移動 | red、保存しない |
| 無効コマ | 無効化したコマへ移動 | red、保存しない |
| session過不足 | 同じsessionを重複配置する操作を試す | 操作を提供しない、またはred |

1対2を作れる移動であっても、生徒・講師の空きコマ、連続上限、優先度5等を破るなら
redになることを確認する。テストを通すためにavailability、優先度5、1対1、allow_gap、
連続上限を緩めない。

自動境界テストは次で再実行できる。手動観察とは別に結果を記録する。

```powershell
python -m pytest -q tests/unit/test_manual_edit.py
python -m pytest -q tests/integration/test_schedule_edit_service.py
```

## 7. ソフト条件悪化の確認

ハード制約をすべて満たす候補だけを使い、次の悪化を個別に作る。

- 通常担当講師から外れる
- 第1～第3希望講師から外れる
- 希望日時（2）から可能日時（1）へ移る
- 1対2が別々の1対1へ分かれる
- 稼働講師×日付×コマが増える
- 既存Assignmentから変更される
- 配置から未配置になり未配置数が増える

yellow dialogで、該当指標のラベル、変更前、変更後、悪化の説明を確認する。

1. CancelするとAssignment、差分、監査が変わらない。
2. 理由を入力して承認すると変更が保存される。
3. 承認後、差分と履歴に操作が表示される。
4. soft悪化を承認しても、hard violationが混在する変更は保存されない。

## 8. 未配置パネル

1. 未配置パネルに生徒、科目、残り回数、主な未配置理由、候補数、優先度5、1対1が
   表示される。
2. 未配置理由が空の単なる「配置不可」だけになっていない。
3. 候補0件のカードをdragした場合はredとなり、理由が表示される。
4. 候補がある未配置カードをgreenのセルへdropするとAssignmentが作られる。
5. yellowの場合は配置済みカードと同じ確認dialogを使う。
6. 配置済みカードを「未配置へ移動」すると、必要回数そのものを削除せず、
   未配置一覧へ戻る。
7. Undo / Redoで未配置から配置、配置から未配置を往復できる。

## 9. 詳細編集、ロック、備考

1. 配置済みカードを右クリックまたはダブルクリックして詳細編集を開く。
2. 日付、コマ、講師、ロック、備考、変更理由を編集できる。
3. 日付・コマ・講師変更はDnDと同じgreen / yellow / red検証を使う。
4. 生徒、科目、LessonRequest自体を別のものへ置換できない。
5. 備考へ架空の日本語文を入力し、保存後と再起動後に表示される。
6. 授業をロックするとカード、詳細、lock件数に文字・アイコンで反映される。
7. ロック済みカードの移動と未配置化は拒否される。
8. ロック解除は明示ボタンまたは詳細dialogで行い、履歴へ残る。

Phase 5の必須範囲は授業単位ロックである。セル、日付、講師、選択範囲の一括lockが
存在しないことを失敗としない一方、実装済みと記録しない。

## 10. 自動保存、再読込み、保存失敗とrollback

### 正常な自動保存

1. 詳細dialogを開き、入力中に「編集中・未保存」と表示される。
2. yellow操作をdropし、dialogで回答する前は「確認待ち・未保存」と表示される。
3. Cancelすると「自動保存済み」へ戻り、DBは変わらない。
4. greenの移動を1件行う。
5. 表示が「保存処理中」から「自動保存済み」へ戻る。
6. 「手動保存」を押す。
7. `$phase5Root\backups`へ新しい`.jukuschedule`が作られ、画面に絶対保存先と
   「個人情報が含まれる可能性」が表示される。
8. backupを別名で開き、直前の変更位置、ロック、備考、AuditLogが含まれる。
9. 通常の手動保存によって再最適化差分baselineやUndo履歴が不意に変わらない。
10. アプリを終了・再起動し、元projectにも変更位置、ロック、備考が保持される。

「手動保存」を未保存queueのcommitと解釈しない。操作ごとにAssignmentとAuditLogが
同じtransactionで即時commitされ、手動保存はその時点の整合したSQLite backupを
明示保存点として作る。

### 保存失敗

`$failureProject`だけを開く。編集前の配置を目視記録し、別のPowerShellで次を実行して
SQLiteへ排他的lockを保持する。

```powershell
$env:PHASE5_LOCK_PROJECT = $failureProject
@'
import os
import sqlite3
from pathlib import Path

path = Path(os.environ["PHASE5_LOCK_PROJECT"]).resolve()
if not path.is_file():
    raise SystemExit(f"project not found: {path}")
connection = sqlite3.connect(path)
connection.execute("BEGIN EXCLUSIVE")
input("exclusive lock active; press Enter to release: ")
connection.rollback()
connection.close()
'@ | python -
```

lock保持中にアプリでgreen候補の移動を1件行う。

1. busy timeout後に日本語の保存失敗・rollback通知が出る。
2. 「自動保存済み」と偽表示しない。
3. カードが変更前位置へ戻るか、再読込みを促す。
4. helper側でEnterを押してlockを解放する。
5. アプリの手動保存またはプロジェクト再読込み後も、失敗した変更が部分反映されていない。
6. 失敗操作だけのAuditLogが追加されていない。
7. 同じ変更をlock解放後に再実行すると正常保存できる。

helperを強制終了した場合も、実運用ファイルで試さない。lockが残っていないことを
確認してから続行する。

### 異常終了時のtransaction境界

別processを`os._exit()`で終了する自動結合テストを実行する。

```powershell
python -m pytest -q tests/integration/test_schedule_edit_service.py::test_abrupt_process_exit_recovers_last_commit_and_rolls_back_incomplete_edit
```

このテストは、異常終了前にcommit済みのAssignmentとAuditLogが再接続後も残り、
異常終了したtransaction内で未commitだったAssignmentとAuditLogが両方rollbackされる
ことを確認する。実アプリや手動確認projectを強制終了して試さない。

Phase 5完了時点では、このcrash-consistencyと手動保存点だけで、起動時に複数backupから
復旧候補を選ぶUI、自動backupの世代管理、世代からの復元UIは未実装だった。これらは
Phase 7で追加したため、現在の確認は
[`manual_test_phase7_data_safety.md`](manual_test_phase7_data_safety.md)へ分ける。

## 11. Undo / Redoと競合保護

同一プロセス内で、順に次を行う。

1. 移動
2. 講師変更
3. ロック
4. ロック解除
5. 備考変更
6. 配置から未配置
7. 未配置から配置
8. 1対2枠の組替え

各操作後にUndoでbefore、Redoでafterへ戻る。逆操作後もDBへ即時保存され、履歴には
元操作とは別にUndo / Redoと理由が表示される。元操作と逆操作が同じoperation IDで
関連付くことは自動結合テストでも確認する。

次に、1件編集してUndo可能な状態で、明示再読込み、プロジェクト切替、または
checkpoint後の再最適化を行う。古いUndo stackが現在のDBを上書きせず、無効化されるか
fingerprint不一致の日本語エラーになることを確認する。

Undo / Redo履歴はアプリ再起動をまたがない。再起動後にボタンが無効でも仕様どおりで、
AuditLogの履歴表示は残ることを確認する。

## 12. 差分と監査ログ

手動移動、講師変更、未配置化、未配置から配置、1対2組替えを行い、差分tabで次を
区別できることを確認する。

- 新規配置
- 日時変更
- 講師変更
- 未配置化
- 1対1／1対2変化
- 変更なし

複数codeが該当する場合、日時と講師等を欠落させない。before / afterのIDだけでなく、
利用者が確認できる日本語summaryを表示する。

履歴tabで次を確認する。

- 時刻
- 操作
- 対象session
- 変更前後のsummary
- 理由
- 手動／Undo／Redo

取消したyellow操作、redで拒否された操作、rollbackした操作を成功監査として残さない。
AuditLogやbefore / after JSONには個人情報が含まれ得るため、外部へ添付しない。

## 13. ロック以外の全体再最適化

1. 少なくとも2件を手動移動し、そのうち1件だけをロックする。
2. ロック済みカードの日付、コマ、講師を記録する。
3. 「ロック以外を再最適化」を押す。
4. 対象配置、ロック、未配置、変更可能件数が現在画面と整合する。
5. 続行すると`$phase5Root\backups`へ新しい`.jukuschedule` checkpointが作られる。
6. checkpoint失敗時はPhase 4画面へ進まない。
7. Phase 4画面で高速または標準presetを実行する。
8. 中止した場合は現在時間割を置換しない。
9. `OPTIMAL`または`FEASIBLE`で保存された後、「時間割編集へ戻る」を押す。
10. ロック済みカードの日付、コマ、講師が変わっていない。
11. 未ロックAssignmentはsolver結果に応じて変更され得る。
12. checkpoint前後の差分に日時、講師、未配置、pairing、変更なしが正しく表示される。
13. 再最適化後に古いUndoが結果を上書きしない。

選択日、選択生徒、選択講師周辺だけの部分再最適化は未実装である。画面にもその旨が
表示され、全体再最適化を部分再最適化として報告しない。

## 14. 検索・絞込み

次を単独・組合せで確認する。

- 生徒名
- 講師名
- 学年
- 科目
- 1対1
- 優先度5
- 警告あり
- ロック済み
- 未配置

一致カードを判別でき、非一致カードは薄くなるか非表示になる。絞込み中も元Assignmentを
削除せず、filter解除で戻る。日本語の全角文字、空白、同姓同名の架空名で文字化け
しない。検索語を技術ログへ記録しない。

## 15. 40講師×5コマ×複数日の性能

自動model回帰を先に実行する。

```powershell
python -m pytest -q tests/integration/test_schedule_editor_view_model.py::test_40_teachers_multiple_days_only_materialize_current_200_cells
```

このテストは架空DTOの講師40名、5コマ、20日、1,000カードを使用し、次を検査する。

- `rowCount() == 5`
- `columnCount() == 40`
- 現在日modelは200セルだけ
- 20日分summaryを保持
- model構築5秒未満
- 20回の日付切替とfilter変更5秒未満

Windows GUIでも同等規模の架空プロジェクトを用意できる場合、次を計測する。用意
できなければ「GUI大規模データ未確認」と記録し、自動model testだけで目視成功としない。

1. 「時間割」を開いて最初のカードが表示されるまでの時間。
2. 講師列を左端から右端へ往復scrollしたときの応答。
3. 20日の日付タブを順に切り替えたときの応答。
4. 検索語、警告filter、拡大率を連続変更したときの応答。
5. card drag中にWindowsが「応答なし」にならない。
6. process memoryが日付切替のたびに無制限に増え続けない。

端末、Windows version、DPI、カード数、所要時間を記録する。性能閾値を満たすために
カード、講師、日付を黙って減らさない。

## 16. 日本語、DPI、キーボード、色以外の状態表現

Windowsの表示設定を変更した場合はアプリを再起動し、少なくとも次を確認する。

1. 1366×768、100%で、日付、filter、グリッド、未配置、詳細、差分、履歴、
   再最適化へscrollまたはkeyboardで到達できる。
2. 150%で日本語ラベル、card badge、header、dialogが重ならず、長文理由を読める。
3. 4Kの150%または200%で文字・drop targetが極端に小さくならない。
4. Tab / Shift+Tabで検索、filter、日付、Undo / Redo、再最適化、side panel、
   dialogへ移動できる。
5. Enter / Spaceでbutton、checkbox、tabを操作でき、Escapeでdialogを安全に閉じる。
6. focus位置が分かり、DnDできない利用者も詳細編集で日付・コマ・講師を変更できる。
7. green / yellow / red、警告、ロック、手動変更は色だけでなくアイコン・文字で分かる。
8. 日本語と空白を含むproject path、backup path、window title、備考が文字化けしない。

確認できない解像度や倍率は「未確認」と記録し、別環境の結果を推測しない。

## 17. ローカルログ、Git除外、Phase 4回帰

次を確認する。

- 一般技術ログへ氏名、備考、Assignment snapshot、検索語を必要以上に記録しない。
- 最適化専用ログは従来どおりrun ID、preset、状態、件数、経過時間等に限定される。
- DB、`.jukuschedule`、backup、log、xlsx、csv、PDF、snapshotがGit除外される。
- Phase 5のAuditLogはローカルproject DB内だけにあり、外部送信されない。
- [Phase 4手動確認](manual_test_phase4.md)の実行、中止、status、結果保存、
  未配置理由、専用ログが壊れていない。
- 「出力」はPhase 6のplaceholderで、存在しないExcel / PDFを生成済みと表示しない。

## 18. 確認後

アプリを終了し、次を記録する。

- 実施日、Windows version、Python / PySide6 version
- 使用したのが架空データだけであること
- 各項目の成功／失敗／未確認
- hard rejectionとsoft confirmationの確認対象
- 40講師×5コマのデータ量と実測時間
- actionableなQML error、保存失敗、rollback結果
- checkpointと再最適化のstatus、lock保持
- BLOCKED事項と再現手順

確認用ファイルを削除する場合は、`$phase5Root`がこの手順で新規作成した一時
ディレクトリであること、その解決済み絶対パスがリポジトリルート、
`%LOCALAPPDATA%\SummerScheduler`、実運用projectではないこと、内容がすべて
確認用であることを目視確認してから行う。削除操作自体は本手順に含めない。
