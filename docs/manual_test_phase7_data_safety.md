# Phase 7 データ安全性・復旧 手動確認票

## 目的と安全条件

自動backup、破損検出、異常終了候補、安全な復元、日本語Windows pathの利用者向け
経路を確認する。実在する生徒・講師・時間割を使用しない。

- `docs`、repository直下、普段使う`.jukuschedule`を試験対象にしない。
- `%TEMP%\SummerScheduler_Phase7_匿名確認`だけに架空projectを作る。
- 破損操作は「破損確認専用copy」だけに行う。
- backupにも個人情報が含まれるため、実データで画面収録・issue添付をしない。
- OneDrive確認では、作業用の架空copyだけを使用する。

## 1. 準備

```powershell
$phase7SafetyRoot = Join-Path $env:TEMP "SummerScheduler_Phase7_匿名確認"
$phase7Config = Join-Path $phase7SafetyRoot "config.yaml"
$phase7Data = Join-Path $phase7SafetyRoot "local-data"
New-Item -ItemType Directory -Force -Path $phase7SafetyRoot | Out-Null
Copy-Item -LiteralPath ".\config.example.yaml" -Destination $phase7Config
$env:SUMMER_SCHEDULER_DATA_DIR = $phase7Data
python -m summer_scheduler --config $phase7Config
```

`config.yaml`の`backup.automatic_interval_minutes`を手動確認時だけ`1`、
`backup.automatic_generations`を`3`へ変更してよい。確認後は試験directoryごと削除する。

## 2. 日本語pathと世代管理

1. `日本語 フォルダー\架空講習.jukuschedule`を新規作成する。
2. ホームに「バックアップとデータ整合性」が表示されることを確認する。
3. 「DB整合性を確認」で「整合性に問題はありません」と表示されることを確認する。
4. 1分ごとに自動backupが増え、4回目以降も自動候補が3世代を超えないことを確認する。
5. migration前・復元前候補があっても、自動3世代の数に含めて削除されないことを確認する。
6. 候補ごとに種類、日時、整合性が文字で表示され、色だけに依存しないことを確認する。

## 3. 復元前退避

1. 架空projectの校舎名を「変更後架空校」へ変更する。
2. 変更前の自動backupを選び、「復元」を押す。
3. 確認dialogに、現在fileを復元前backupへ退避する旨と個人情報注意があることを確認する。
4. 復元後、変更前の校舎名へ戻ることを確認する。
5. 候補一覧に「前回の復元前」があり、それを開くと「変更後架空校」が保全されている
   ことを、別名copyを開いて確認する。
6. 選択したbackup自体が0 byteや破損になっていないことを確認する。

## 4. 異常終了候補

1. 架空projectを開き、自動backupが1件以上あることを確認する。
2. この架空試験でだけ、Task Managerからappを終了する。
3. appを再起動し、projectを開く前に「前回正常終了を確認できない」と対象pathが
   表示されることを確認する。
4. 整合した候補を復元し、projectを閉じて再起動する。
5. 正常close後は異常終了表示が残らないことを確認する。

## 5. 破損検出

先に元の架空projectと自動backupがあることを確認し、appを閉じる。

```powershell
$source = Join-Path $phase7SafetyRoot "日本語 フォルダー\架空講習.jukuschedule"
$corrupt = Join-Path $phase7SafetyRoot "破損確認専用copy.jukuschedule"
Copy-Item -LiteralPath $source -Destination $corrupt
[System.IO.File]::WriteAllBytes($corrupt, [byte[]](1, 2, 3, 4))
```

1. `破損確認専用copy.jukuschedule`を開く。
2. SQLite形式または整合性破損の日本語errorが表示されることを確認する。
3. open成功やmigration成功として扱われないことを確認する。
4. 対象に紐づくbackupがなければ「候補がない」と明示されることを確認する。
5. 破損fileが自動的に書き換え・削除されないことを確認する。

## 6. 読取専用、権限、同期、path

- 読取専用: 架空copyのプロパティで読取専用にし、「読み取り専用」のmessageを確認する。
- 権限不足: 書込みを許可されていない試験folderを組織管理者が用意できる場合だけ確認する。
- OneDrive: 架空copyを同期中に開き、lock時は同期完了後の再試行を案内するmessageを確認する。
- 長いpath: Windowsのpolicy範囲で長い日本語folder名のcopyを開き、成功するか、
  「pathが長すぎる」と短縮を案内することを確認する。
- 容量不足は実diskを満杯にして確認しない。自動テストの`ENOSPC` simulation結果を使う。

いずれも失敗時に元fileのSHA-256が変わらず、0 byteの最終fileが作られないことを確認する。

```powershell
Get-FileHash -LiteralPath $source -Algorithm SHA256
```

## 7. 個人情報とlog

1. 手動backup、自動backup、復元確認dialogに個人情報注意が表示される。
2. 一般logに生徒名、講師名、希望日時、backup本文がない。
3. error logへ絶対project pathを必要以上に複製していない。
4. network接続やtelemetryを要求せず、offlineで上記操作を完了できる。
5. `*.jukuschedule`、backup、marker、logが`git status`へ実データとして出ない。

## 8. 自動テスト対応

次は`tests/integration/test_project_recovery.py`で再現する。

- 日本語pathと自動backup世代数
- `PRAGMA integrity_check`による破損検出
- 異常終了marker
- 有効・破損元の復元前退避
- 破損backup拒否時の対象hash保持
- 読取専用
- 容量不足、権限不足、OneDrive lock相当、長いpathの例外分類
- 同名backupの上書き拒否
- QML ViewModelからの実復元
