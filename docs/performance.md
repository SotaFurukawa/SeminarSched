# 性能確認記録

最終更新: 2026-07-29

## 1. 判定方法

マスター仕様の初期目標規模は、生徒150名、講師40名、期間40日、1日5コマ、
授業希望約1,000sessionである。本書は実測した値と未測定項目を分ける。

- `PASS`: 記載した環境、入力、コマンドで実測済み。
- `PARTIAL`: 一部の経路または近似規模だけを実測済み。
- `NOT TESTED`: 未測定。推定値を記入しない。
- 自動テストの5秒閾値と、Windows実機で人が感じる応答性を混同しない。
- OR-Toolsの`FEASIBLE`はハード制約を満たす実行可能解であり、全辞書式段階の
  最適証明を意味しない。

## 2. 測定環境

2026-07-29に既存のPhase 4計測を行い、後述のportable／installerローカル検証にも
使用したbuild machine:

| 項目 | 値 |
|---|---|
| OS | Microsoft Windows 10 Pro 22H2相当、10.0.19045 |
| CPU | Intel Core i7-10700K 3.80 GHz |
| logical processor | 16 |
| memory | 31.8 GiB |
| Python | 3.12.4 |
| OR-Tools | 9.14.6206 |
| solver worker | 1（再現性優先の既定値） |
| ストレージ、電源mode | 記録なし |

ストレージ、バックグラウンドprocess、Windows電源modeが未記録のため、別PCとの厳密な
比較には使わない。氏名や入力snapshotを結果JSONへ記録しない架空データだけを使用した。
配布候補の値もこの同一build machineだけで測定したものであり、PATHを制限したことを
Python未導入のclean Windowsやoffline環境での測定と読み替えない。

## 3. 目標規模の最適化実測

共通入力:

- 生徒150名
- 講師40名
- 40日
- 5コマ
- LessonRequest 300件
- 必要session 1,050件
- candidate 73,440件

### 高速preset（30秒）

実行コマンド:

```powershell
python .\tools\benchmark_phase4.py --time-limit 30
```

| 項目 | 実測 |
|---|---:|
| candidate生成（単独計測） | 3.369秒 |
| end-to-end | 27.179秒 |
| solver報告 | 27.015秒 |
| 全benchmark process | 30.595秒 |
| status | `FEASIBLE` |
| 配置 / 未配置 | 1,042 / 8 |
| requested wall time内 | true |
| 判定 | PASS |

全benchmark processにはcandidate生成の単独計測と、candidate生成を再度含む
end-to-end計測がある。30.595秒をアプリ1回の待ち時間として扱わない。

### 標準preset（120秒）

実行コマンド:

```powershell
python .\tools\benchmark_phase4.py --time-limit 120
```

| 項目 | 実測 |
|---|---:|
| candidate生成（単独計測） | 3.451292秒 |
| end-to-end | 117.939982秒 |
| solver報告 | 117.765秒 |
| 全benchmark process | 121.440812秒 |
| status | `FEASIBLE` |
| 配置 / 未配置 | 1,042 / 8 |
| warning | 1 |
| requested wall time内 | true |
| 判定 | PASS |

全benchmark processの意味は高速presetと同じで、120秒のアプリ実行が超過した値ではない。

### 高品質preset（600秒）

実行コマンド:

```powershell
.\.venv\Scripts\python.exe -m tools.benchmark_phase4 --time-limit 600
```

| 項目 | 実測 |
|---|---:|
| candidate生成（単独計測） | 3.487012秒 |
| end-to-end | 597.919409秒 |
| solver報告 | 597.734秒 |
| 全benchmark process | 601.454458秒 |
| status | `FEASIBLE` |
| 配置 / 未配置 | 1,042 / 8 |
| warning | 1 |
| requested wall time内 | true |
| 判定 | PASS |

全benchmark processにはcandidate生成の単独計測と、candidate生成を再度含む
end-to-end計測がある。600秒内に返った実行可能解であり、全辞書式段階の
`OPTIMAL`証明や、実GUIでの中止操作を確認した結果ではない。

## 4. Phase 5 / 6の既存性能回帰

| 項目 | 入力 | 証拠 | 状態 |
|---|---|---|---|
| 時間割model構築 | 40講師×5コマ×20日、1,000card | 当日200セルだけをmaterializeし5秒未満の自動test | PASS |
| 日付切替・filter | 同上 | 20日分の操作を5秒未満の自動test | PASS |
| 大人数Excel | 150生徒、40講師、40日 | 全4帳票を生成しopenpyxlで再読込み | PASS |
| 大人数PDF | 匿名大規模帳票 | 32ページ / 7ページを実PDF生成・再読込み | PASS |
| 実GUIスクロール | 40講師×5コマ | Windows実画面で未測定 | NOT TESTED |
| Phase 6時点の実Excel / PDF生成時間 | 目標規模 | 当時は所要時間未記録。Phase 7のsource通し実測は次節 | NOT TESTED |

自動model testはQML delegate描画、GPU、DPI、マウス操作の体感を測っていない。

## 5. Phase 7のsource版end-to-end計測

次のコマンドで、入力検証を通る匿名プロジェクトを一時ディレクトリへ作り、主要操作を
1 processで通し測定した。

```powershell
.\.venv\Scripts\python.exe -m tools.benchmark_phase7_operations --time-limit 30
```

入力は生徒150名、講師40名、40日、5コマ、8使用科目、LessonRequest 300件、
必要session 1,050件である。project生成直後に生徒availability 1,555行、
講師availability 3,621行を保存し、測定対象の生徒xlsx取込みで716行を追加した。
したがって最適化時は生徒2,271行、講師3,621行で、優先度5の指定講師と共通候補を
持つ。これは、未配置を含む難例を維持した前節の純粋solver入力とは別シナリオである。
両方とも固定seed`20260729`、1 worker、架空データだけを使用した。

| 測定 | 実測 | 補足 |
|---|---:|---|
| source版offscreen初回起動 | 3.355442秒 | 一時app DB、`--smoke-test` |
| 目標規模project生成・投入 | 2.030360秒 | 152文字の日本語path |
| project再読込み＋自動backup | 0.110093秒 | SQLite backupを含む |
| 生徒・講師・科目・受講希望一覧 | 0.406920秒 | 150生徒、40講師、23登録科目 |
| 生徒xlsx preview＋反映 | 5.268852秒 | 150入力行、availabilityは1,555→2,271行 |
| 入力検証 | 0.103011秒 | error 0、warning 0 |
| 最適化prepare | 0.289986秒 | DBから不変DTOを構築 |
| 最適化solve | 29.267505秒 | `FEASIBLE`、1,050配置／0未配置 |
| 最適化finalize | 3.817850秒 | 独立検証とtransaction保存 |
| 時間割board query | 3.697225秒 | 1,050 card |
| ViewModelの日付40回切替 | 3.887716秒 | QML delegate描画は含まない |
| 全体Excel | 7.102307秒 | 100ページ、80,126 bytes |
| 全体PDF | 6.141343秒 | 100ページ、1,669,076 bytes |
| 全通しbenchmark | 65.771140秒 | 上記を同一processで順次実行 |
| process peak working set | 978.605 MiB | Windows `GetProcessMemoryInfo` |
| project DB | 2,600,960 bytes | 一時ファイル、Git非追跡 |

最適化結果のwarningは1件で、入力検証のwarningは0件である。PDF生成時にQtが
PySide6 package内のfont directoryを見つけられない旨をstderrへ出したが、Windowsの
system fontで100ページのPDF生成と再読込みは成功した。この警告を「配布版でfontが
同梱済み」と読み替えない。

### 配布版・実GUIで未測定の項目

| 測定 | 入力・開始点 | 状態 | 備考 |
|---|---|---|---|
| portable対話GUIの初回／2回目起動 | ZIP展開後 | NOT TESTED | Python / Node.jsなしのclean PC待ち。ローカルsmokeは次節 |
| installer版の対話GUI起動 | fresh install後 | NOT TESTED | ローカルoffscreen smokeは次節 |
| 実GUIスクロール | 40講師×5コマ×40日 | NOT TESTED | frame落ち・freezeを観察していない |
| 実GUIでの600秒中止 | 高品質preset | NOT TESTED | source benchmarkはUIを持たない |
| 実viewer／printer | 100ページExcel / PDF | NOT TESTED | 生成・再読込みとは別確認 |

peak working setはnative OR-Tools / Qtを含むprocess値であるが、全操作を1 processで
順次実行した最大値であり、各操作単独のpeakではない。

## 6. Phase 7配布候補のローカル実測

次は2026-07-29に同一build machineで行った、未署名・未公開成果物の測定である。
日本語と空白を含む展開先、制限したPATH、Qt offscreenで`--smoke-test`を実行した。
実GUI操作、Python未導入のclean Windows、offlineを測った値ではない。

| 測定 | 実測 | 結果・補足 |
|---|---:|---|
| portable ZIP | 143,564,844 bytes | SHA-256 `5611f8e62b6e7e8e9ac456ca91186f5a52e207573fb866b377ccbaf0796eba2f` |
| portable offscreen smoke | 4.111秒 | exit 0、日本語＋空白path、制限PATH |
| application tree | 3,494 files | 実行前後同数、差分0、`__pycache__`／`.pyc` 0 |
| portable利用者領域 | app DB 266,240 bytes | Alembic head `20260729_0006`、log作成 |
| installer | 90,164,009 bytes | SHA-256 `98601a138cdda25a088c93bf2c96e93338098788de31fac2ff5bb8ac33d1dc89` |
| fresh install | 19.192秒 | 短いlocal path、exit 0 |
| installed app offscreen smoke | 8.057秒 | exit 0 |
| uninstall | 所要時間未記録 | exit 0、registry 1→0、Start menu 1→0、desktop 0 |
| uninstall後の利用者data | 時間対象外 | app DB、log、sentinel保持 |

最深pathがおよそ264文字になる過長なinstall先ではinstallerがexit 5となりrollbackした。
短いpathでは成功したため標準的なlocal install経路の技術確認には使えるが、長いpath
全般の合格とはしない。上書きupgrade、署名済み成果物、clean Windowsでの測定も
`NOT TESTED`である。

## 7. 再測定手順

1. Release候補と同じcommit、version、dependency、Windows buildを使用する。
2. 電源mode、CPU、memory、ストレージ、Windows build、display scalingを記録する。
3. 実在人物を含まない固定seedの架空データを使う。
4. cold startとwarm startを分け、最低3回の個別値と中央値を残す。
5. GUI操作は計測開始・終了条件を固定し、応答不能時間も記録する。
6. solverはstatus、配置／未配置、目的内訳、time limit内判定も記録する。
7. Excel / PDFは生成完了だけでなく、再読込み、page / sheet数、file sizeを検証する。
8. 結果に氏名、入力snapshot、絶対プロジェクトpathを残さない。

## 8. 現在の評価

Phase 4の30秒／120秒／600秒、Phase 5 model、Phase 6大規模帳票に加え、Phase 7では
source版で起動、読込み、一覧、取込み、検証、最適化、board query、Excel、PDF、
process peak working setを同一の匿名目標規模で実測した。いずれも完了し、最適化は
ハード制約を満たす`FEASIBLE`を返した。

同一build machineではportable offscreen smoke、fresh install、installed smoke、
uninstallも実測し、短いlocal pathでは成功した。一方、Python未導入のclean Windows、
offline、上書きupgrade、実QMLのスクロール、600秒中止、viewer／printerの体感確認は
未完了である。したがって、Phase 7全体の性能受入は現時点で `PARTIAL` とする。
