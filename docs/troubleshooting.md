# トラブルシューティング

対象: `1.0.1`
最終更新: 2026-07-29

## 最初に記録すること

問題を再現したら、次を記録します。生徒名、講師名、回答内容、project fileそのものを
公開issueへ添付しないでください。

- Aboutに表示されるapp version
- Aboutに表示されるDB schema revision
- Windows versionとx64
- installer版またはportable版
- 表示された日本語messageとerror code
- 操作手順
- 発生時刻
- 保存先がlocal / OneDrive / network / USBのどれか
- logの必要な時刻周辺

既定log:

```text
%LOCALAPPDATA%\SummerScheduler\logs\summer_scheduler.log
```

Explorerのaddress barへ上記を貼り付けて開けます。最適化runごとのlogは一般logと
同じ基点の隔離directoryにあります。logには氏名を必要以上に書かない設計ですが、
外部送信前に内容を確認してください。

## 1. appが起動しない

1. Windows 10 / 11 x64であることを確認します。
2. portable版はZIP内から直接開かず、すべて展開します。
3. folderの一部だけをcopyせず、portable folder全体を展開し直します。
4. appを二重起動していないか確認します。
5. antivirusの検疫履歴を確認します。保護を無効にせず、公式Releaseとhashを確認します。
6. `%LOCALAPPDATA%\SummerScheduler\logs\`の最新logを確認します。

展開後のportable application treeはread-onlyでも動作する設計です。ただし
`%LOCALAPPDATA%\SummerScheduler`と、選択したproject／出力先には書込み権が必要です。

`Qt platform plugin`、QML module、DLL等の不足を示す場合は、配布物が不完全です。
別siteからDLLを個別downloadせず、公式portableを再downloadしてSHA-256を照合します。

## 2. SmartScreenが表示される

署名なしexeではpublisherが「不明」となり、SmartScreenが警告する場合があります。

1. fileを入手したURLが公式GitHub Releaseか確認します。
2. `SHA256SUMS.txt`とhashを照合します。
3. app versionとRelease noteを確認します。
4. 組織管理PCでは管理者のpolicyに従います。

警告を回避するためにSmartScreen、Windows Defender、組織policyを恒久的に無効化
しません。hashが異なる場合や入手元が不明な場合は実行しません。

## 3. projectを開けない

主な原因:

- `.jukuschedule`ではないfileを選んだ
- SQLite headerや必要tableが壊れている
- 対応より新しいDB schemaである
- fileが別processでlockされている
- OneDriveが同期・競合している
- read-onlyまたはaccess権がない
- migration前backupを作れない

対処:

1. 原fileを上書きしません。Explorerで名前変更や修復を繰り返す前にcopyを保全します。
2. app versionとDB schema messageを記録します。
3. Excel、SQLite viewer、別起動app等、fileを開いているprogramを閉じます。
4. OneDriveの場合は同期完了を待ち、local folderへ整合したbackupをcopyして開きます。
5. migration前backup directoryの空き容量と書込み権を確認します。
6. ホームに復旧候補が表示された場合、整合性が`ok`の候補だけを選んで復元します。
   appは置換前に元fileを「復元前backup」へ退避します。

汎用SQLite toolで直接SQLを実行しないでください。外部編集したDBはハード制約や監査の
整合性を壊す可能性があります。

## 4. 新規projectを作れない／保存できない

message別に次を確認します。

- 同名file: 別名にするか、内容を確認後に明示上書きします。
- read-only: 書込み可能なDocuments等へ保存します。
- 権限不足: Program Files直下や他user folderを避けます。
- 容量不足: 保存先と`%TEMP%`の空き容量を確保します。
- 長いpath: 親folderを短くし、file名の禁止文字を除きます。
- OneDrive lock: 同期を待つかlocalへ保存します。
- antivirus lock: quarantine履歴を確認し、公式hashを照合します。

保存失敗時に元fileが残っていることを確認します。errorを無視して「保存済み」と
判断しません。

## 5. Excel取込みでerrorになる

- sheet名と1行目headerを変更していないか確認します。
- 生徒ID、講師ID、科目codeを名前の代わりに使います。
- IDの前後空白、全角／半角、先頭0が失われていないか確認します。
- 日付と時刻が文字列として崩れていないか確認します。
- availabilityが0 / 1 / 2以外になっていないか確認します。
- 優先度が1～5か、優先度5に通常担当があるか確認します。
- 希望講師が登録済みで、その科目を指導可能か確認します。
- CSVの文字化けはUTF-8 / CP932の指定を切り替えます。
- error表のsheet、行番号、列名を元fileと照合します。

previewにerrorが1件でもあれば反映しません。error行だけを勝手に飛ばしません。
preview後にfileを変更した場合は、再検証してから反映します。

## 6. 同じ人が見つからない／同姓同名

このappは名前だけで人物を決めません。安定した生徒ID・講師IDを使用します。

- 名字と名前の空白だけを直しても別IDは統合されません。
- 同姓同名は別IDにします。
- 過去projectと現在projectの人物は別snapshotです。必要ならmaster Excelで移します。
- IDを変更する場合はLessonRequest、availability、group受講者への影響を確認します。

## 7. 最適化を開始できない

「未配置・warning」でerrorを再検証します。主な原因:

- 優先度5なのに通常担当がない
- 通常担当が科目未対応
- 開校日外のavailability / 集団授業
- コマ時刻が重なる
- 固定Assignment同士、または集団授業と固定Assignmentが衝突
- 無効化した生徒・講師・科目への参照

errorをwarningへ変更して回避しません。masterまたは入力dataを修正します。

## 8. `FEASIBLE`のまま終わる

`FEASIBLE`は失敗ではなく、全ハード制約を満たす解が得られたものの、現在の段階の
最適性を時間内に証明していない状態です。

- まず未配置数と理由を確認します。
- 必要なら標準120秒または高品質600秒を選びます。
- 同じ入力でもCPU負荷や条件数により結果時間が変わります。
- より長いpresetでも全辞書式段階の`OPTIMAL`を保証しません。

ハード制約を緩める前に、availability、資格、優先度5、1対1、空きコマ、連続上限を
業務上変更してよいか確認します。

## 9. 最適化を中止できないように見える

中止はsolverの安全な停止点へ協調的に伝えます。threadを強制終了しないため、直ちに
画面が閉じない場合があります。

1. 中止要求済みの表示を確認します。
2. 数秒待ち、経過時間と状態を確認します。
3. appを何度もclickしません。
4. 長時間変化がなければ発生時刻とlogを記録します。

中止runで現在のAssignmentを置き換えない設計です。Task Managerで終了した場合も、
再起動後に現在時間割を確認してください。

## 10. cardを移動できない

赤previewのcodeと理由を確認します。主な拒否:

- 生徒または講師が不可
- 講師が科目未対応
- 優先度5の通常担当以外
- 3人目
- 1対1必須枠
- 生徒の同時刻重複
- 集団授業
- lock
- 生徒の連続上限
- 生徒・講師の空きコマ
- 休校日または無効コマ

赤を強制適用できません。黄の場合はsoft条件の悪化を読み、理由を入力すると適用できます。
preview後に別変更が入った場合は競合を拒否するため、再読込みしてやり直します。

## 11. Undo / Redoが使えない

履歴はprocess内だけです。次の場合は安全のため消えます。

- app再起動
- project切替
- 明示再読込み
- 外部変更でfingerprint不一致
- 別のbranch操作後

AuditLogは残りますが、AuditLog全体を自動的なUndo commandとして再生しません。
必要なら履歴panelで変更理由と前後を確認し、新しい手動操作として戻します。

## 12. PDFを生成できない／previewできない

- 1pageの日数または講師列数を減らします。
- font sizeを読みやすい範囲で調整します。
- 余白を確認します。
- ロゴpathが存在し、対応画像で、壊れていないか確認します。
- 保存先が書込み可能か確認します。
- 同名PDFをviewerで開いている場合は閉じます。
- 日本語pathを短いlocal pathへ変えて再試行します。

PDFが0byte、page数0、寸法不正なら成功扱いしません。appは生成後にPDFを再読込みして
検証します。実printerで崩れる場合はPDF viewer名、printer driver、用紙、倍率を
記録します。

## 13. Excelを出力できない

既存xlsxをExcelで開いているとWindows file lockで上書きできない場合があります。
Excelを閉じ、数秒待って再実行します。

- 保存先、空き容量、書込み権を確認します。
- 同名上書きは明示確認します。
- 出力先の一時`*.tmp`が残った場合は、app終了後に個人情報として安全に削除します。
- Excelの印刷結果は用紙A3 / A4、横／縦、fit設定を確認します。

Excelにはロゴ画像を埋め込みません。これは現在の既知仕様です。

## 14. CSVが文字化けする

Excelで開く場合は既定のUTF-8 BOMありを使用します。他systemがBOMを受け付けない場合
だけBOMなしを選びます。CSVは18列固定です。

先頭が`=`, `+`, `-`, `@`等の値は表計算ソフトで式にならないよう保護されます。
保護用apostropheを業務dataの一部と誤解しないでください。

## 15. OneDriveで問題が起きる

SQLiteは同期中の競合やsidecar fileの扱いに注意が必要です。

推奨:

1. 作業中のprojectはlocalの非同期folderで開く。
2. appのbackup機能で整合したsnapshotを作る。
3. appを閉じてからbackupをOneDriveへ移す。
4. 別PCでは同期完了後、localへcopyして開く。

同じ`.jukuschedule`を複数PCで同時編集しません。競合copyを自動mergeする機能はありません。

## 16. backupから復元したい

1. ホームの「バックアップとデータ整合性」を開きます。
2. 自動、migration前、復元前backupの日時と整合性messageを確認します。
3. `データベースの整合性に問題はありません`と表示された候補の「復元」を選びます。
4. 一覧外の手動backupは「別のバックアップを選んで復元」から選びます。
5. 確認dialogで対象pathと個人情報注意を確認して実行します。
6. 復元後、入力検証、Assignment、lock、未配置、警告、出力設定を確認します。

復元前:

- appが現在fileの復元前backupを作成できない場合、処理が中止されることを確認する。
- 日時、app version、DB schemaを記録する。
- backupにも個人情報があるため共有先に注意する。
- 汎用SQLite toolで修正しない。

破損した元fileも復元前backupへbyte単位で保全されます。自動修復は行いません。
「空き容量」「読み取り専用／権限」「OneDrive同期中」「pathが長すぎる」と表示された
場合は原因を解消して再試行し、元fileや一時fileを手作業で上書きしないでください。

## 17. uninstall後にprojectが見つからない

uninstallerは利用者dataを削除しない方針ですが、`.jukuschedule`の保存先は利用者が
選びます。Windows searchで`*.jukuschedule`を検索し、Documents、Desktop、
OneDrive等を確認します。

app管理dataは次にあります。

```text
%LOCALAPPDATA%\SummerScheduler
```

再install前にこのfolderを削除しないでください。削除する場合は必要なbackupとlogを
別場所へ保全します。

## 18. 問い合わせ前の安全な再現

1. 元projectをbackupします。
2. 可能なら架空sample projectで同じ操作を再現します。
3. app version、DB schema、手順、error code、発生時刻をまとめます。
4. logは該当時刻だけを確認し、個人情報や絶対pathを除きます。
5. `.jukuschedule`、Excel、PDF、screen shotを公開場所へ添付しません。

データを失う可能性、migrationで元fileが変わる可能性、ハード制約違反が保存された
可能性がある場合は操作を止め、元fileとbackupを保全してください。

## 19. Windows配布buildでLNK1104または文字化けしたpathが出る

Nuitka／MSVCが非ASCIIのworkspace実体パスを誤変換した可能性があります。`subst`、
junction、symbolic linkでdrive名や表示pathだけを変えて再試行しないでください。
これらはbuild toolから元の実体パスへ再解決されます。

正確なsource stateを`C:\build\summer-scheduler`等のASCII文字だけの実体パスへcopy
またはcloneし、`.venv-release`もその場所で新しく作ります。失敗した途中成果物や
`nuitka-crash-report.xml`をRelease候補として扱いません。この制限はbuild環境だけの
もので、完成アプリの日本語install／利用者data path対応とは別です。

## 20. installerがexit 5でrollbackする

install先のpathが長すぎる可能性があります。ローカル検証では、最深pathがおよそ
264文字になる過長なinstall先でexit 5となりrollbackしましたが、短いlocal pathでは
install、起動smoke、uninstallが成功しました。

1. 既定の`%LOCALAPPDATA%\Programs\SummerCourseScheduler`、またはより短いlocal pathを
   使用します。
2. 深い一時directory、network path、OneDrive配下を避けて再試行します。
3. 失敗後にapp本体、uninstall registry、Start menu shortcutが残っていないか確認します。
4. exit 5を成功として扱わず、installer logと最深path長を記録します。

短いpathでの成功は、Windows上限付近のすべての長いpathをサポートする証明では
ありません。既存のproject、app DB、logを削除して回避しないでください。
