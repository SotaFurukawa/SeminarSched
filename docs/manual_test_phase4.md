# Phase 4 手動確認手順

この手順は、Windows 10 / 11実機でPhase 3までの機能を回帰確認しながら、Phase 4の
簡易最適化画面、非同期実行、中止、結果表示、履歴保存、再最適化、入力エラー拒否、
ローカルログ、日本語・DPI表示を確認するためのものである。仕様上の基準は
[公開仕様](specification.md)、実装判断は
[ADR 0004](adr/0004-ortools-boundary-and-lexicographic-optimization.md)である。

この手順を実施しただけでPhase 5の時間割編集やPhase 6の出力を確認済みと扱わない。
また、実行していない項目や、処理が速すぎて観察できなかった中止操作を成功と記録
しない。

実在する生徒、講師、校舎、時間割は使用しない。確認用の`.jukuschedule`、入力、
snapshot、ログにも個人情報を入れず、Git、issue、Pull Request、CI artifact、
チャットへ添付しない。

## 1. 前提と隔離した確認領域

[README.md](../README.md)の手順でPython 3.12の仮想環境と開発依存関係を準備する。
普段使用しているアプリ管理DBやログへ触れないよう、同じPowerShellプロセス内だけ
保存先を一時ディレクトリへ変更する。

```powershell
$phase4Root = Join-Path ([System.IO.Path]::GetTempPath()) ("SummerSchedulerPhase4-" + [guid]::NewGuid().ToString("N"))
$projectRoot = Join-Path $phase4Root "日本語 Phase4確認"
New-Item -ItemType Directory -Path $projectRoot

$env:SUMMER_SCHEDULER_DATA_DIR = Join-Path $phase4Root "data"
$env:SUMMER_SCHEDULER_LOG_DIR = Join-Path $phase4Root "logs"

$bootstrapProject = Join-Path $projectRoot "Phase4開始用_架空講習.jukuschedule"
$sampleProject = Join-Path $projectRoot "日本語 匿名最適化サンプル.jukuschedule"
$invalidProject = Join-Path $projectRoot "入力エラー確認専用_匿名サンプル.jukuschedule"
$env:PHASE4_PROJECT_PATH = $sampleProject

python -m summer_scheduler
```

PowerShellを閉じると、このプロセスに設定した環境変数は失われる。確認中は同じ
PowerShellからアプリを起動する。

## 2. Phase 4画面の出現を確認する

次はPhase 4手動確認の入口となる必須ゲートである。

1. ウィンドウタイトルが日本語で表示され、サイドバーに9項目があることを確認する。
2. 「時間割」を選ぶ。
3. Phase 5のプレースホルダーではなく、次が同じ画面に表示されることを確認する。

   - 高速（30秒）
   - 標準（120秒）
   - 高品質（600秒）
   - 「自動作成を実行」
   - 「中止」
   - 経過時間
   - solver status
   - 配置／未配置
   - 目的関数の内訳
   - 未配置授業と理由
   - 警告
   - 最適化専用ログ保存先

「時間割」がプレースホルダーのまま、画面が空白、または
`optimizationViewModel is not defined`等のQMLエラーがログへ出る場合は、Phase 4 UIの
接続が未完了である。その状態で後続項目を成功扱いにせず、BLOCKEDとして記録する。

プロジェクトをまだ開いていない状態では、実行ボタンが無効、または実行時に
「先にプロジェクトを作成または開いてください」と日本語で案内されることも確認する。

## 3. 匿名サンプルとmigration 0004

匿名サンプル作成ボタンはプロジェクトを開いているときに表示されるため、最初に
開始用プロジェクトを1件作る。

1. 「ホーム」→「新規プロジェクト」で次を入力し、`$bootstrapProject`へ保存する。

   | 項目 | 値 |
   |---|---|
   | プロジェクト名 | Phase4開始用 架空講習 |
   | 校舎名 | 架空確認校 |
   | 開始日 | 2026-08-03 |
   | 終了日 | 2026-08-07 |

2. 「未配置・警告」→「匿名サンプルを作成…」で`$sampleProject`を作る。
3. 表示中のプロジェクトが「匿名サンプル 2026夏期講習」へ切り替わることを確認する。
4. 同じ方法で`$invalidProject`も作る。通常確認と入力エラー確認で取り違えないよう、
   毎回ウィンドウタイトルとプロジェクトパスを確認する。
5. `$sampleProject`を開き直し、「未配置・警告」でプロジェクト全体検証を実行する。
6. 意図的な希望講師資格の警告は表示されてもよいが、最適化を止めるerrorが0件で
   あることを確認する。errorがある場合は原因を解消するまで実行しない。

アプリを終了してから、次の読取り専用確認を実行する。人物名やavailabilityを表示せず、
schema revision、最新run、Assignmentの数値配置signatureだけを出力する。

```powershell
@'
import hashlib
import os
import sqlite3
from pathlib import Path

path = Path(os.environ["PHASE4_PROJECT_PATH"]).resolve()
if not path.is_file():
    raise SystemExit(f"project not found: {path}")
uri = path.as_uri() + "?mode=ro"
with sqlite3.connect(uri, uri=True) as connection:
    revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    run = connection.execute(
        "SELECT id, status, solver_status, unassigned_count, warning_count "
        "FROM optimization_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    rows = connection.execute(
        "SELECT lesson_request_id, session_index, date, time_slot_id, teacher_id, is_locked "
        "FROM assignments "
        "ORDER BY lesson_request_id, session_index"
    ).fetchall()
payload = repr(rows).encode("utf-8")
print("revision=", None if revision is None else revision[0])
print("latest_run=", run)
print("assignment_count=", len(rows))
print("assignment_signature=", hashlib.sha256(payload).hexdigest())
'@ | python -
```

最適化前でも`revision=20260728_0004`となり、`optimization_runs`と`assignments`を
読めることを確認する。最新runがまだなければ`latest_run=None`、Assignmentがなければ
件数0でよい。ファイルが見つからない場合に別場所へ空DBを作らないよう、スクリプトは
存在確認とSQLiteのread-only modeを使っている。

## 4. 高速presetの実行とUI応答

同じPowerShellからアプリを再起動し、`$sampleProject`を開く。

1. 「時間割」で「高速（30秒）」を選ぶ。
2. 「自動作成を実行」を押す。
3. 実行直後に「実行中」、経過時間、現在の段階が更新されることを確認する。
4. 実行中もウィンドウの移動、スクロール、ボタンの再描画が行え、Windowsから
   「応答なし」と判定されないことを確認する。
5. 実行中に別プロジェクトを開こうとした場合は、先に中止するよう案内され、
   接続中のプロジェクトが切り替わらないことを確認する。
6. 完了後、solver statusが`OPTIMAL`または`FEASIBLE`であることを確認する。
7. 成功メッセージに配置件数と未配置件数が表示されることを確認する。

`INFEASIBLE`、`UNKNOWN`、`MODEL_INVALID`、保存エラーになった場合は、画面の警告と
ローカルログを記録して原因を調べる。無理に成功扱いにせず、現在のAssignmentが
部分置換されていないことを手順7のsignatureで確認する。

## 5. 結果、未配置理由、目的内訳

完了後の簡易画面で次を確認する。

1. 「配置」と「未配置」の件数が負数でなく、合計が必要session数と整合する。
2. 目的関数の内訳に少なくとも次が表示される。

   - 未配置数
   - 講師希望違反
   - 稼働講師枠
   - 希望日時
   - 既存時間割からの変更
   - 任意の負荷調整

3. 未配置がある場合、受講希望IDとsession番号だけでなく、日本語の理由が表示される。
4. 候補なし、優先度5共通枠不足、資格、availability、集団授業、1対1定員、
   連続上限、空きコマ、固定授業等の理由を、該当しないデータへ偽表示しない。
5. 未配置が0件の場合は「未配置授業はありません」と明示される。
6. warningがある場合は文字でも判別でき、色だけに依存しない。

Phase 4簡易画面はAssignmentの生徒名・日付・コマ・講師をグリッド表示しない。
グリッドがないことをPhase 4失敗とはしない一方、存在しないドラッグ＆ドロップ、
ロック操作、Undo / Redoを確認済みと記録しない。

## 6. 保存履歴と再起動

アプリを終了し、手順3の読取り専用スクリプトを再実行する。

- `revision=20260728_0004`
- `latest_run`のstatusが`completed`
- solver statusが`OPTIMAL`または`FEASIBLE`
- Assignment件数が画面の配置件数と一致
- `assignment_signature`が64文字のSHA-256

を確認して値を手動記録する。DBのinput/result snapshot自体は個人情報を含み得るため、
画面共有、ログ、報告書へ貼り付けない。

アプリを再起動して同じ日本語パスのプロジェクトを開き、migrationの再適用エラーが
なく、マスターとプロジェクト全体検証が利用できることを確認する。Phase 5グリッドは
未実装のため、保存済みAssignmentのカード表示まではこのPhaseの確認対象にしない。

## 7. 中止と現在時間割の保持

手順6で記録した`assignment_signature`を中止前signatureとする。

1. 「高品質（600秒）」を選び、「自動作成を実行」を押す。
2. 実行中表示になったら直ちに「中止」を押す。
3. 「中止を要求しました。安全な停止を待っています」と表示されることを確認する。
4. UIが固まらず、処理終了後に中止された旨と「現在の時間割は変更していません」が
   表示されることを確認する。
5. アプリ終了後に手順3のスクリプトを実行する。
6. 最新runのstatusが`cancelled`で、Assignment件数とsignatureが中止前と一致する
   ことを確認する。

匿名サンプルが速く完了し、「中止」を押す前に`completed`になった場合、この手順は
未確認である。入力を壊したり実データを使ったりせず、`$sampleProject`のコピーへ
架空の生徒、講師、資格、LessonRequest、availabilityを追加して計算量を増やし、
再確認する。観察できなかった中止を成功と報告しない。自動境界テストは次で別途
確認できる。

```powershell
python -m pytest -q tests/integration/test_optimization_view_model.py
python -m pytest -q tests/scenarios/test_phase4_optimizer_edges.py
```

## 8. 同じ入力での再最適化

入力を変更せず、最初と同じpresetで再度自動作成する。

1. 完了status、配置・未配置、目的内訳を記録する。
2. アプリ終了後にAssignment signatureを再取得する。
3. 両方の実行が全段階`OPTIMAL`で、設定、マスター、availability、集団授業が
   同一なら、既存Assignment維持段階と同一seedによりsignatureが一致することを
   確認する。
4. どちらかが`FEASIBLE`の場合は、後の実行が上位目的を改善して配置を変更する可能性が
   ある。変更だけで失敗とせず、未配置数等の上位目的が悪化していないことを確認する。
5. OptimizationRunが新規履歴として追加され、過去runを上書きしないことを確認する。

画面からの部分再最適化とロック／解除はPhase 5である。この手順は現在時間割全体を
入力に含めた全体再最適化だけを確認する。

## 9. invalid入力を開始前に拒否する

入力エラー確認専用の`$invalidProject`を開き、既存時間割のsignatureを記録する。

1. 「講師」で`T-002`（架空 講師みどり）を選ぶ。
2. 指導可能科目から`JH_MATH`を指導不可へ変更する。
3. 「未配置・警告」でプロジェクト全体検証を実行する。
4. 優先度5の通常担当講師資格、または集団授業担当講師資格のerrorが表示されることを
   確認する。
5. 「時間割」で自動作成を実行する。
6. 入力検証error件数を含む日本語メッセージが表示され、workerが開始しないことを
   確認する。
7. アプリ終了後、最新runがこの失敗操作だけで`running`として追加されていないこと、
   Assignment signatureが変わらないことを確認する。
8. `T-002`の`JH_MATH`資格を元へ戻し、再検証でerrorが解消することを確認する。

入力検証を通すために優先度5を1～4へ下げたり、1対1必須を解除したりしない。
ハード制約を変更する回避は、この確認の修正ではない。

## 10. ローカルログと個人情報

最適化を1回実行し、画面の「最適化専用ログ保存先」に表示された固有パスを
`$optimizationLog`へ貼り付ける。一般ログ直下の`optimization-runs`にある
UTF-8ファイルであり、実行のたびに異なることを確認する。

```powershell
$optimizationLog = Read-Host "画面に表示された最適化専用ログの絶対パス"
Test-Path -LiteralPath $optimizationLog
Split-Path -Leaf (Split-Path -Parent $optimizationLog)
Get-Content -Encoding utf8 -LiteralPath $optimizationLog
```

次を目視確認する。

- 開始と完了・中止・失敗についてrun ID、preset、状態、件数、経過時間を追跡できる。
- OR-Toolsの大量のsearch logが標準出力やログへ出続けない。
- 生徒名、講師名、availability回答、備考、入力snapshot本文が最適化ログへ出ない。
- プロジェクトの絶対パスが最適化ログ本文へ出ない。
- workerの予期しない例外で、入力由来の例外値をそのまま記録しない。
- ログにエラーがある場合、画面の成功表示だけで握り潰さない。

専用ログへの終了追記だけが失敗した場合は、一般ログ
`$env:SUMMER_SCHEDULER_LOG_DIR\summer_scheduler.log`へ例外型が記録される一方、
completedとして保存済みのOptimizationRunとAssignmentがrollbackされないことを
自動テストで確認する。

ログ保存先の絶対パスにはWindows利用者名等が含まれ得る。架空データだけの確認でも、
ログを外部へ添付しない。`.gitignore`で`*.log`、DB、`.jukuschedule`、入力・出力・
backupが除外されることも確認する。

## 11. 日本語、画面サイズ、DPI、キーボード

Windowsの表示設定を変更した場合はアプリを再起動し、少なくとも次を確認する。

1. 1366×768、表示倍率100%で、preset、実行、中止、status、件数、目的内訳、
   未配置理由、警告、ログ保存先へスクロールして到達できる。
2. 表示倍率150%で、日本語ラベルが重ならず、長い理由を折返しまたはスクロールで
   読める。
3. 4Kディスプレイの150%または200%で、文字とボタンが極端に小さくならない。
4. 「高速」「標準」「高品質」、「実行中」「中止」「完了」、warningが文字で
   判別でき、色だけに依存しない。
5. Tab、Shift+Tab、矢印、Enter、Spaceでpreset、実行、中止、結果一覧へ移動・操作
   でき、フォーカス位置が分かる。
6. 日本語と空白を含むプロジェクトパス、ログパス、ウィンドウタイトルが文字化け
   しない。
7. 実行中の経過時間更新でレイアウトが跳ねたり、ボタンが操作不能位置へ移動したり
   しない。

確認できない解像度や倍率は「未確認」と記録する。別環境で未実施の項目を推測で
成功扱いにしない。

## 12. Phase 3回帰

[Phase 3手動確認手順](manual_test_phase3.md)を参照し、最低限次を再確認する。

1. 日本語パスの`.jukuschedule`を新規作成、保存、再読込みできる。
2. 生徒、講師、科目、資格、LessonRequestの編集が動作する。
3. availabilityと集団授業の取込み、差分、明示削除、全体検証が動作する。
4. 集団授業の半開区間による講師・生徒衝突検証が維持される。
5. 「出力」はPhase 6のプレースホルダーであり、Excel / PDFを出力済みのように
   表示しない。

## 13. 確認後

アプリを終了し、`OptimizationRun`に`running`のまま残った手動確認runがないこと、
ログに未処理例外がないことを確認する。中止を観察できずアプリを強制終了した場合は、
そのrunとAssignmentの状態を確認し、成功扱いにしない。

確認用ファイルを削除する場合は、`$phase4Root`がこの手順で新規作成した一時
ディレクトリであること、その解決済み絶対パスがリポジトリルート、
`%LOCALAPPDATA%\SummerScheduler`、実運用プロジェクトではないこと、内容がすべて
確認用であることを目視確認してから行う。削除操作自体は本手順に含めない。
