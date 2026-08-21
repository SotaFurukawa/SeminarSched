# Phase 7 最終受入テスト

最終更新: 2026-07-29

## 1. 状態の意味

| 状態 | 意味 |
|---|---|
| PASS | 記載した確認方法で要求を確認済み |
| FAIL | 要求を満たさないことを確認 |
| PARTIAL | 下位境界や自動testは通るが、要求全体または実機確認が未完了 |
| NOT TESTED | 対応する環境・成果物で未確認 |

成功した自動testをGUI目視、clean Windows、GitHub-hosted Actions、実installerの
成功へ読み替えない。状態は本番公開承認ではない。

## 2. マスター仕様35章 — 機能

| 受入項目 | 状態 | 確認方法 | 備考 |
|---|---|---|---|
| GUIから新規プロジェクトを作成できる | PASS | project service / WorkspaceViewModel integration、QML offscreen smoke | `.jukuschedule`作成・再openを自動確認 |
| 生徒・講師・科目を登録できる | PASS | master service / repository / QML contract tests | validation、使用停止、削除方針を含む |
| 講師対応科目を登録できる | PASS | qualification service / QML integration tests | 中学受験区分と数学IA・IIBC・IIIを自動推定しない |
| 生徒・講師アンケートを取り込める | PASS | xlsx / UTF-8 / CP932 integration tests、Phase3 ViewModel tests | 列mapping、preview、transaction反映 |
| 集団授業を取り込める | PASS | group lesson service integration tests | 2sheet、任意時刻、受講者、衝突検証 |
| 必要回数を指定できる | PASS | LessonRequest CRUD、session展開tests | 正数、session過不足を検査 |
| 優先度5を担当講師へ固定できる | PASS | Phase4 scenarios / candidate / result validator tests | 指定講師で不可能なら未配置 |
| 1対1必須を守る | PASS | Phase4 scenarios、manual edit、result validator tests | 同じ講師枠への他生徒を拒否 |
| 講師1名につき最大2名 | PASS | Phase4 scenarios、manual edit、result validator tests | 3名目を拒否 |
| 生徒の連続3コマを防ぐ | PASS | Phase4 scenarios | override=3の例外も別test |
| 生徒・講師の空きコマを防ぐ | PASS | Phase4 scenarios / edge tests | 集団授業が間を埋める場合も検証 |
| 可能な範囲で1対2を増やす | PASS | 辞書式目的と1対2scenario tests | 空きコマ等のhard制約を優先 |
| 未配置を明示する | PASS | optimizer、UI ViewModel、帳票tests | Assignmentを偽造せずsession差分から再構築 |
| 未配置理由を表示する | PASS | diagnostics / reporting / UI tests | 「単独配置可」は独立validatorを再実行 |
| 手動編集できる | PARTIAL | manual edit / ScheduleEditService / ViewModel / QML contract tests | Windows実機のdrag操作は未確認 |
| lockして再最適化できる | PASS | real reoptimization transaction integration test | 授業単位lock。部分再最適化は対象外 |
| Excel・PDFを出力できる | PASS | 全帳票を実生成・再読込み、Qt PDF tests | Windows実viewer / printerは未確認 |
| 保存・再読込みできる | PASS | project lifecycle / SQLite backup / crash transaction tests | auto backup世代・復旧UIは別項目 |
| Windows実行ファイルを生成できる | PASS | local Windows buildでportable ZIP / installerを生成し、配布内容を検証 | clean Windowsでの起動は別項目 |

## 3. マスター仕様35章 — 品質

| 受入項目 | 状態 | 確認方法 | 備考 |
|---|---|---|---|
| 主要制約にtestがある | PASS | `tests/scenarios/test_phase4_optimizer*.py`ほか | skip / xfailなしで全体gateへ含める |
| sample dataで再現可能 | PASS | anonymous sample / benchmark tests | 架空名、固定seed |
| 実データを含まない | PASS | `.gitignore`、git ignore tests、file audit | 別名参考PDFは開かず追跡対象外 |
| UIが日本語である | PASS | QML contract / offscreen生成 | system由来dialogを除く主要業務UI |
| errorが分かりやすい | PARTIAL | 日本語の型付き例外とfailure tests | clean PC、権限、容量不足の実表示は未確認 |
| READMEで利用開始できる | PARTIAL | READMEのsource手順と配布手順review | 実Release URLは未公開 |
| GitHub Actionsが動く | NOT TESTED | GitHub-hosted run URL待ち | workflowのlocal reviewだけでPASSにしない |
| installerまたはportable版で起動できる | PASS | portableとfresh install後のexeをlocal Windowsでoffscreen smoke | clean Windows、Python未導入、offlineは別項目 |

最終source gateはRuff format／lint 215 files、mypy 168 source files、pytest
399 passed in 125.83s、QML lint 23 filesだった。source offscreen smokeはexit 0、
4.415秒で、266,240 bytesのDB、head `20260729_0006`、local logを確認した。
PowerShell 3 files、YAML 4 files、Markdown 39 files内のlocal link 112件も検査済みで
ある。これらをhosted Actionsやclean Windowsの代替にはしない。

## 4. Phase 7必須フロー

| 受入項目 | 状態 | 確認方法 | 備考 |
|---|---|---|---|
| app起動 | PASS | source offscreen smoke | 配布版は別行 |
| 新規project | PASS | lifecycle integration | GUI flowもQML接続済み |
| コマ・開校日 | PASS | master integration | |
| 生徒・講師・科目 | PASS | master integration | |
| 講師対応科目 | PASS | qualification integration | |
| LessonRequest | PASS | service / DB validation | |
| アンケート取込み | PASS | availability integration | |
| 集団授業取込み | PASS | group integration | |
| 入力検証 | PASS | project validation integration | error時に最適化を開始しない |
| 自動最適化 | PASS | scenario / run service | |
| 未配置確認 | PASS | diagnostics / UI / reporting | |
| 手動編集 | PARTIAL | service / ViewModel / QML tests | 実機DnD未確認 |
| lock | PASS | service / validator tests | |
| 再最適化 | PASS | lock保持integration | 部分再最適化ではなく全体 |
| Excel出力 | PASS | openpyxl再読込み | |
| PDF出力 | PASS | QPdfDocument再読込み | 実printer未確認 |
| 保存・終了 | PASS | project / transaction tests | source smoke終了 |
| 再起動・project再読込み | PASS | lifecycle / crash tests | |
| 上記を1つのsource service flowで通す | PASS | `test_phase7_end_to_end.py` | 匿名xlsx／集団取込み、lock保持再最適化、実Excel／PDF、service再生成・再open |
| 上記全20項目を1つの配布版GUIで通す | NOT TESTED | clean Windows end-to-end待ち | 独立testの合算でPASSにしない |

## 5. 性能

| 受入項目 | 状態 | 確認方法 | 備考 |
|---|---|---|---|
| 150生徒・40講師・40日・5コマ・約1,000session | PASS | Phase4 30 / 120 / 600秒benchmark、Phase7 DB通し測定 | 入力条件は`performance.md`参照 |
| 高速30秒 | PASS | E2E 27.179秒、`FEASIBLE` | 1,042配置 / 8未配置 |
| 標準120秒 | PASS | E2E 117.939982秒、`FEASIBLE` | 1,042配置 / 8未配置 |
| 高品質600秒 | PASS | E2E 597.919409秒、`FEASIBLE` | 1,042配置 / 8未配置 |
| 起動・読込み・一覧・取込み・検証 | PASS | 匿名目標規模のWindows source通し測定 | 起動3.355442秒、読込み＋backup 0.110093秒、取込み5.268852秒 |
| 実GUI scroll | NOT TESTED | 40講師×5コマ×40日で測定 | Python model testはPASS |
| Excel / PDF生成時間 | PASS | 匿名目標規模、各100ページ | Excel 7.102307秒、PDF 6.141343秒 |
| process memory | PASS | Windows process peak working set | 全通しprocessのpeak 978.605 MiB |

純粋solverの30／120／600秒難例と、DB通し測定の入力検証可能な1,050配置／0未配置
シナリオは別入力である。DB通し入力は優先度5の指定講師と共通枠を補強しており、
結果件数を相互に置き換えない。詳細とQt font警告は
[`performance.md`](performance.md)を参照する。

## 6. データ安全性

| 受入項目 | 状態 | 確認方法 | 備考 |
|---|---|---|---|
| 原子的project / output保存 | PASS | ProjectService / atomic renderer tests | 同一directoryのtemp後にreplace |
| 保存前backup | PASS | 手動保存点 / 再最適化checkpoint tests | |
| 自動backup世代管理 | PASS | `test_project_recovery.py` / QML contract | 設定世代をproject別に保持 |
| DB破損検出 | PASS | `PRAGMA integrity_check` integration / UI contract | 自動修復せず復旧候補を表示 |
| migration前backup | PASS | project open / migration tests | backup失敗時はmigration中止 |
| 異常終了復旧 | PARTIAL | session marker / 候補 / QML integration | 実process強制終了は手動確認待ち |
| 読取り専用file | PASS | Windows read-only integration | 組織ACLは手動確認対象 |
| OneDrive同期中失敗 | PARTIAL | lock fault injection | 実同期競合は手動確認待ち |
| disk容量不足 | PASS | `ENOSPC` fault injection | 元fileのSHA-256保持 |
| 権限不足 | PASS | `EACCES` fault injection / output tests | 実Program Files ACLは手動確認対象 |
| 同名上書き | PASS | overwrite / race tests | 明示確認が必要 |
| 長いpath | PARTIAL | `ENAMETOOLONG` fault injection / packaged installer実測 | 最深部約264文字ではinstaller exit 5。rollbackは成功し、短い日本語pathではPASS |
| 日本語path | PASS | DB / Excel / PDF / CSV tests | |
| backup復元 | PASS | 有効・破損元・破損backup integration / QML | 復元前backup必須 |

## 7. 個人情報と通信

| 受入項目 | 状態 | 確認方法 | 備考 |
|---|---|---|---|
| 外部通信なし | PARTIAL | source dependency / import監査 | packet captureによる配布版offline確認は未実施 |
| telemetryなし | PASS | source / config / UI文言review | |
| 実データをGitへ含めない | PASS | ignore rule tests / file audit | |
| logへ氏名を必要以上に書かない | PASS | redacted logging tests | tracebackはpathを伏せる |
| crash log内容 | PARTIAL | logging tests | packaged crash実機未確認 |
| sampleは架空名 | PASS | sample / benchmark tests | |
| READMEの個人情報注意 | PASS | README review | DB、backup、outputも対象 |
| backupに個人情報がある旨 | PASS | UI / docs contract | |

## 8. 配布必須テスト

| 受入項目 | 状態 | 確認方法 | 備考 |
|---|---|---|---|
| clean Windows環境相当で起動 | NOT TESTED | 別VM / PC待ち | build PCの実行では代替しない |
| Pythonなし | NOT TESTED | clean Windows待ち | PATHからPythonを除いたportable / installed smokeはPASSしたが、未導入PCの代替にはしない |
| Node.jsなし | NOT TESTED | clean Windows待ち | runtime依存にしない設計 |
| 日本語user名path | PARTIAL | packaged exeを日本語・空白入りpathでsmoke | 実Windows accountのuser名が日本語の環境は未確認 |
| 日本語project名 | PASS | DB / import / output integration | |
| offline | NOT TESTED | network遮断したpackaged exe待ち | |
| 新規projectからPDFまで | NOT TESTED | packaged GUI E2E待ち | service別testsはPASS |
| 保存・再読込み | PASS | source integration | packaged GUIは未確認 |
| install・uninstall | PASS | local fresh install / smoke / uninstall | install 19.192秒、smoke 8.057秒、全exit 0。DB・log・sentinel保持 |
| portable起動 | PASS | 日本語・空白入り展開先、制限PATH、offscreen | exit 0、4.111秒。clean Windowsは別項目 |
| 旧版からmigration | PASS | `0001`からheadの自動test | packaged exeでも再確認 |
| backup復元 | PASS | `test_project_recovery.py` | packaged GUIでは再確認 |
| GitHub Actions | NOT TESTED | hosted run待ち | |
| SHA-256一致 | PASS | `SHA256SUMS.txt`生成後、別directoryへcopyして再検証 | portable ZIP / installerの両方が一致 |

### ローカル配布成果物の実測

| 成果物 | size | SHA-256 |
|---|---:|---|
| `SummerCourseScheduler-Portable-1.0.0-rc.1.zip` | 143,564,844 bytes | `5611f8e62b6e7e8e9ac456ca91186f5a52e207573fb866b377ccbaf0796eba2f` |
| `SummerCourseScheduler-Setup-1.0.0-rc.1.exe` | 90,164,009 bytes | `98601a138cdda25a088c93bf2c96e93338098788de31fac2ff5bb8ac33d1dc89` |

portableは日本語・空白入りpathへ展開し、`PATH`をWindows system directoryだけに
制限したoffscreen smokeがexit 0、4.111秒で完了した。配布treeのfile件数は
3,494件から3,494件、hash差分0件で、`__pycache__`／`.pyc`は0件だった。
初回起動で266,240 bytesのSQLite DB、Alembic head `20260729_0006`、local logを
確認した。

installerは同じく日本語・空白入りの短いpathへfresh installし、install 19.192秒、
installed smoke 8.057秒、uninstallの各終了コードは0だった。uninstall registryは
1件から0件、Start Menu shortcutは1件から0件、desktop shortcutは全工程0件だった。
DB、log、事前sentinelはuninstall後も保持された。最深部が約264文字になる過長pathの
試行はinstaller exit 5だったが、rollbackに成功し、残留したinstallを成功扱いして
いない。

最終成果物を別directoryへcopyした後のchecksum再検証はPASSし、個人情報markerは
0件だった。生成installerは未署名であり、公開時はSmartScreenの可能性を既知事項として
扱う。buildは成功したが、project file不在、`dumpbin`不在、data file不在の警告が
記録されている。

## 9. 公開判定

現時点の判定は **リリース候補成果物のlocal受入は進んだが、本番公開はBLOCKED** である。
少なくとも次が未完了である。

- GPL-3.0-onlyは採用済み。Qt完成artifactの対応ソース・notice監査と、Inno Setupの
  配布条件確認。コード署名は採用せず、未署名表示とSHA-256確認を必須とする。
- portable / installerのclean Windows、Python未導入、offline環境での起動。
- installerの旧版からの上書きupgrade。local fresh install / uninstallはPASS済み。
- packaged GUIで新規projectからPDF、終了、再読込みまでのend-to-end。
- GitHub-hosted通常CIはPASS済み。tag起動のrelease workflowとartifact再downloadは未確認。
- 配布版の実GUI性能、scroll、中止操作、viewer／printer確認。
- 未署名成果物の配布判断と、約264文字のinstall pathでexit 5となる既知制限の扱い。

repositoryはGitHubへ公開済みで、通常CIのlint・型検査・testは成功した。tagを
triggerとするrelease workflowは未実行で、tagとGitHub Releaseは作成していない。
FAIL / PARTIAL / NOT TESTEDをRelease noteへ転記し、license、clean Windows等の受入、
repository初期化方針、配布責任者の明示承認が揃うまでtagや本番Releaseを作成しない。
