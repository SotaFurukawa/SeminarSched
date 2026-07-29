# ADR 0004: OR-Tools を独立境界に置き、辞書式最適化を行う

- 状態: 採用・Phase 4実装済み
- 日付: 2026-07-28
- 更新: 2026-07-29
- 対象: Phase 4の最適化境界、ハード制約、辞書式Solve、中断、結果保存

## コンテキスト

時間割には、受講・出勤可能日時、科目資格、重複禁止、最大2名、1対1必須、優先度5、
固定、集団授業、連続数、空きコマなど、破ってはならない条件がある。同時に、未配置、
講師希望、1対2、希望日時、再最適化時の変更量など、優先順位の異なる品質目標がある。

単一の大きな重み付き和では、重みの設定ミスにより、上位目的の小さな悪化と下位目的の
大きな改善が交換されるおそれがある。またORM modelをsolverへ直接渡すと、DB schemaと
最適化modelが密結合する。長時間のCP-SAT SolveをUI threadで実行したり、解が保証され
ないstatusで変数値を読んだりすることも、停止不能、無効結果保存、データ破損の原因に
なる。

## 決定

Google OR-Tools CP-SAT `9.14.6206`を採用し、最適化をUIとSQLAlchemyから独立した
package境界に置く。

```text
Repository / ORM
  → Application Service
  → immutable OptimizationInput DTO
  → solver非依存の疎なcandidate generation
  → greedy initial feasible solution + independent validation
  → CP-SAT hard constraints / objectives
  → complete hint + staged solver + verified feasible incumbent
  → OptimizationResult / Diagnostics DTO
  → 独立result validator
  → Application Service
  → OptimizationRun / Assignment transaction
```

OR-Toolsのmodel builderはSQLAlchemy Session、ORM model、QML objectを参照しない。
Application Serviceは短いtransactionでORM行を`frozen=True`のDTOへコピーし、
DB資源を閉じてからworkerへ渡す。DTOのversion付きJSONはkey順を正規化して
SHA-256 fingerprintを作る。

### ハード制約

各必要授業回を1始まりのsessionへ展開し、各sessionを「ちょうど1候補または未配置」
とする。次を候補除外またはCP-SAT制約として実装し、目的関数のpenaltyへ置き換えない。

1. 各sessionはちょうど1候補または未配置
2. 生徒の同時刻重複禁止
3. 同一講師・同一コマの生徒数は最大2名
4. 1対1必須を含む講師・コマは他生徒0名
5. 優先度5は通常担当講師だけ
6. 講師科目資格
7. 生徒availability 0の除外
8. 講師availability 0の除外
9. 開校日・有効コマだけを使用
10. 集団授業と受講生の重複禁止
11. 集団授業と担当講師の重複禁止
12. ロック済みAssignmentの日時・コマ・講師保持
13. 同一LessonRequestの同一日複数回は許すが、他のハード制約を適用
14. 生徒の最大連続コマ数
15. `allow_gap=false`の生徒の空きコマ禁止
16. `allow_gap=false`の講師の空きコマ禁止
17. 必要回数超過禁止
18. 無効な生徒・講師・科目を使用しない

空きコマは、生徒・講師・日付ごとに`sort_order`順のactive列と0→1のstart変数を作り、
start合計を1以下にする。これにより使用コマ集合を空集合または1つの連続区間にする。
コマ数を5固定と仮定しない。固定集団授業もactiveへ含める。

同一生徒・同一日時の重複禁止と、同一講師・同一日時の容量・1対1制約は、候補の
組合せごとに重複した制約を作らず、`生徒／講師 × 日付 × コマ`のoccupancyへ候補を
集約して表現する。これによりハード制約の意味を変えずmodelサイズを抑える。

生徒の`allow_gap_override`と`max_consecutive_slots_override`は、値が指定されていれば
Student標準値より優先し、nullならStudent値を用いる。連続上限は`limit + 1`個の各窓の
active合計を`limit`以下にする。空きコマ許可と連続上限を別の制約として扱う。

### 辞書式目的

1. 未配置授業数の最小化
2. 優先度1〜4、通常担当、第1〜3希望講師の違反最小化
3. 稼働する`講師 × 日付 × コマ`数の最小化
4. 生徒・講師の希望日時の最大化
5. 既存時間割からの変更最小化
6. 偏り、分散、負荷集中、1 名授業等の追加評価

各段階を別Solveとし、候補生成開始からmodel構築、全Solveまで、高速30秒／
標準120秒／高品質600秒の単一deadlineを共有する。候補生成とハード制約構築には
中止または期限到達を返すcallbackを渡し、Solveごとに残り時間だけを渡す。

候補生成後、ロック済み授業を先に保持し、候補数、優先度5、1対1必須等を考慮した
決定論的greedy初期解を構築する。各追加時のschedule解析と完成後の独立validatorの
両方で全ハード制約を確認し、通過した解だけをincumbentとして採用する。CP-SATには
配置・未配置、occupancy、start、補助indicator等を含む全非固定変数のcomplete hintを
与える。2026-07-29の既定規模では153,221個の非固定変数をhintし、partial hint補完の
探索時間を避けた。初期解採用時と公開結果返却直前の二重validatorを通し、Application
Serviceの保存前validatorも独立して維持する。

各段階にはincumbentの現在目的値より悪化させない不等式cutoffを追加する。前段階が
`OPTIMAL`のときだけ目的値を等式固定する原則は変えない。検証済みincumbentがあり、
残り時間が5秒未満なら次段階を開始しない。各Solveの制限から残り時間の15%、
最大3秒をsnapshot抽出、独立検証、診断、返却の余白として確保する。

- 候補生成中の期限到達: 利用者キャンセルとは区別した`UNKNOWN`とし、
  solver valueやAssignmentを使用しない。
- 初期解・model構築中の期限到達: 独立検証済みincumbentがあれば`FEASIBLE`として
  復帰し、なければ`UNKNOWN`とする。
- `OPTIMAL`: 整数目的値を等式で固定して次段階へ進む。
- `FEASIBLE`: 実行可能snapshotを保持するが、未証明の目的値を固定せず停止する。
- `UNKNOWN`: solverの変数値を読まない。greedy初期解または以前の段階で得た検証済み
  incumbentがあれば`FEASIBLE`として復帰する。
- `INFEASIBLE` / `MODEL_INVALID`: solverの変数値を読まず、以前のsnapshotで
  fatal statusを隠さない。
- deadline到達: 以前の検証可能snapshotだけを`FEASIBLE`として返す。

段階内weight、時間上限、乱数seed、search worker数はYAML設定からDTOへ注入し、
solverへマジックナンバーを直書きしない。同一講師が通常担当と希望順位の複数区分へ
現れる場合は最大点だけを採用し、重複加点しない。

### version固定

OR-Toolsは`9.14.6206`へ完全固定する。CP-SATのstatus、`stop_search()`、変数値取得、
seedによる再現性はversion差の影響を受け得るため、依存解決のたびに無検証で更新
しない。更新時は、全ハード制約、辞書式順序、deadline、`FEASIBLE` snapshot、
`UNKNOWN` value禁止、中断、同一seedのscenario testを通してから固定versionを変更する。

### 中断とUI境界

不変DTOだけをQThread上のworkerへ渡し、workerは`solve_optimization()`だけを実行する。
prepare、finalize、DB操作はworkerへ持ち込まない。`CancellationToken`は
`threading.Event`で要求を保持し、候補生成・モデル構築の安全点で確認し、Solve中は
束縛した`CpSolver.stop_search()`を呼ぶ。`QThread.terminate()`は使用しない。
中止された結果はAssignmentへ保存しない。

### 保存と履歴

Alembic revision `20260728_0004`でAssignmentとOptimizationRunを追加する。
prepare時に入力snapshot、seed、時間上限、開始statusを保存する。finalize時は同じ
project IDと正規化pathを確認し、次の3つのfingerprintを再照合する。

1. OptimizationRunへ保存した入力JSON
2. workerへ渡したprepare済み不変DTO
3. 現在のDBから同じ設定で再構築した入力

続いて候補を再生成し、solverと独立したvalidatorでsession過不足、候補一致、固定、
重複、容量、1対1、集団授業、空きコマ、連続上限を再検査する。非中止の`OPTIMAL`
または`FEASIBLE`だけを保存する。

既存Assignmentは結果snapshotへ含め、既存のrunning OptimizationRunをcompletedへ
更新し、ロック済みAssignmentを保持した現在時間割の置換を同一transactionで行う。
入力変更、validator違反、保存例外はrollbackしてrunをfailedにし、キャンセルは
cancelledにする。いずれも現在のAssignmentを部分更新しない。

## 根拠

- CP-SATは0/1配置、容量、排他、固定、連続パターンを1つのmodelで表現できる。
- 未配置変数により、配置不能な授業でもハード制約を破らず理由を返せる。
- 複数Solveと`OPTIMAL`だけの目的固定は、マスター仕様の優先順位を保持する。
- DTO境界により、DBなしのscenario test、将来のsolver変更、migrationからの独立が
  可能になる。
- 独立validatorとtransactionは、solver実装バグや実行中の入力変更から現在時間割を
  保護する。

## 影響

良い影響:

- ハード制約とソフト制約の混同をコード構造とtestで防げる。
- solverをGUI、DBなしで実行できる。
- 目的関数の内訳を利用者へ説明できる。
- 候補除外理由と未配置診断を再現可能にできる。
- キャンセル、timeout、status遷移で未検証Assignmentを保存しない。

注意点:

- 最大6回Solveするため単一Solveより時間がかかる。2026-07-29に
  `python .\tools\benchmark_phase4.py --time-limit 30`で行った通常経路の
  既定規模・高速30秒benchmarkは、候補73,440件、独立候補生成3.369秒、
  end-to-end 27.179秒（solver報告27.015秒）、`FEASIBLE`、配置1,042件／未配置8件、
  時間内判定`true`だった。全benchmark 30.595秒は候補生成単独と、候補生成を再実行
  するend-to-endの二重測定であり、アプリ1回の待ち時間ではない。
- 同じ既定規模を`python .\tools\benchmark_phase4.py --time-limit 120`で測定した
  標準120秒の正式値は、独立候補生成3.451292秒、end-to-end 117.939982秒
  （solver報告117.765秒）、`FEASIBLE`、配置1,042件／未配置8件、警告1件、
  時間内判定`true`だった。全benchmark 121.440812秒も二重測定であり、アプリの
  120秒実行が超過した値ではない。
- 高速presetは初期規模で実用的な`FEASIBLE`を確保し、標準presetは後段目的の改善に
  用いる。ただし入力・環境によって全辞書式段階の`OPTIMAL`完了は保証しない。
- 通常benchmarkでは`tracemalloc`を無効にする。`--trace-memory`はPython allocationの
  参考測定だけに用い、計測負荷を含む時間やnative memoryを含まないpeak値を
  性能合否へ使用しない。
- CP-SAT constraintだけでは利用者向け理由にならないため、候補除外理由と解後の
  競合診断を別に保守する。
- QThread内のCPU負荷とWindows配布時のメモリはPhase 7まで継続して観測する。
- 入力・結果snapshotは個人情報を含み得るため、ローカルプロジェクトDBの外へ
  送信せず、GitやCI artifactへ含めない。

## 採用しなかった案

- ハード制約を大きな penalty にする: 条件によって違反解が選ばれ、最上位仕様に反する。
- 全目的の単一重み付き和: 上位目的の優先を保証しにくく、weight の桁あふれや調整困難を招く。
- ORM object を model builder へ直接渡す: persistence と solver の変更が密結合する。
- QML から solver を直接呼ぶ: UI thread、test、error handling、再利用性の要件を満たさない。
- 各段階へ固定秒数を割り当てる: 全体上限を超えるか、未使用時間を後段へ回せない。
- `FEASIBLE`目的値を固定して次段階へ進む: 未証明値を最適値として扱うため採用しない。
- `UNKNOWN`でsolver valueを読む: OR-Toolsが解を保証していないため採用しない。
- `QThread.terminate()`で強制停止する: solverとPythonの状態を安全に解放できないため
  採用しない。

## 検証方針

次の自動テストをPhase 4の品質ゲートに含める。Release時のテスト件数と全体ゲートの
結果は、個人情報を含まない検証記録へ残す。

- `tests/unit/test_candidate_generation.py`
- `tests/unit/test_result_validation.py`
- `tests/unit/test_optimization_objectives.py`
- `tests/unit/test_initial_solution.py`
- `tests/unit/test_solver_initial_hint.py`
- `tests/unit/test_optimization_diagnostics.py`
- `tests/unit/test_optimization_dto_serialization.py`
- `tests/integration/test_optimization_input_builder.py`
- `tests/integration/test_optimization_run_service.py`
- `tests/integration/test_optimization_view_model.py`
- `tests/integration/test_phase4_models.py`
- `tests/scenarios/test_phase4_optimizer.py`
- `tests/scenarios/test_phase4_optimizer_edges.py`

Windows実機の実行・中止・結果・ログ・再最適化・不正入力・日本語DPIは
[`manual_test_phase4.md`](../manual_test_phase4.md)で確認する。Phase 5の時間割
グリッドやPhase 6の出力を、このADRの検証済み範囲へ含めない。
