# ADR 0010: 単一standalone treeからportable・installerを作り公開を承認gateで止める

- 状態: 採用・Phase 7検証中
- 日付: 2026-07-29
- 対象: Windows standalone build、portable ZIP、installer、checksum、GitHub Release、
  license、個人情報、署名

## コンテキスト

マスター仕様は、PythonやNode.jsを導入していないWindows 10 / 11 x64でも利用できる
portable版とinstallerを要求する。実行時にはPySide6 / Qt Quick / QtQuick.Pdf、QML、
OR-Tools native library、SQLite、Alembic migration、YAML resource等が必要である。
source環境で起動するだけでは、これらが配布物へ正しく入ったことを保証できない。

配布物をinstaller用とportable用に別々に組み立てると、片方だけにQML、plugin、migration、
licenseが欠ける危険がある。またproject、backup、input / output、logは個人情報を
含み得るため、build contextやinstallerへ混入させてはならない。

本番GitHub Releaseの公開、Qt Community Editionの完成artifact監査、
code-signing certificateは技術実装だけでは決められない。プロジェクト自身は
GPL-3.0-onlyを採用する。自動workflowが成功したことを所有者の公開承認として
扱うこともできない。

## 決定

### 1. Release候補とversion境界

最初のRelease候補を`1.0.0-rc.1`とする。

- Python package metadata、`summer_scheduler.__version__`、Qt application version、
  About、log、帳票に同じapp versionを表示する。
- DB schemaはAlembic head revisionであり、app versionと別に表示する。
- `1.0.0-rc.1`を正式版`1.0.0`や本番公開済みと表現しない。

### 2. 1つのstandalone directoryを配布内容の正本とする

Windows buildはPython 3.12系の隔離環境でNuitka系のstandalone compilationを行い、
まず実行可能なapplication directoryを1つ作る。採用する具体的なcommandとversionは
Phase 7のbuild scriptと検証結果を正本とし、このADRへ検証完了後に追記する。

Nuitka 4.0以降のcompilerはAGPL-3.0である。生成runtimeには
`Nuitka Runtime Library Exception`があり、その追加許可は通常のcompilation processで
作ったtarget codeを任意条件で配布できると説明する。従来版のApache-2.0という記憶に
依存せず、Release環境へ実際に導入した版の`METADATA`、compiler license、
runtime exceptionを確認する。compilerそのものをapplicationへ不要に同梱しない。

standalone treeには最低限次を含める。

- application executableとPython runtime
- 使用するQt DLL、QPA / image / TLS等の必要plugin
- Qt Quick / Controls / Layouts / QtQuick.PdfのQML import
- OR-Toolsと推移的native runtime
- SQLite
- package内QML、既定YAML、Alembic環境と全revision
- `THIRD_PARTY_NOTICES.md`と必要な全文license / notice

portable ZIPはこのtreeをそのままarchiveする。installerも同じtreeだけをinstallする。
installer用に別のPython package解決やresource copyを行わない。

### 3. user dataをapplication treeから分離する

installer版とportable版のどちらも、app管理DB、config、log、migration前backup等の既定値を
`%LOCALAPPDATA%\SummerScheduler`以下へ置く。利用者が選ぶ`.jukuschedule`と出力fileも
application directoryへ強制しない。

- Program Filesやread-only portable directoryへruntime dataを書かない。
- uninstallはapplication binaryとshortcutを削除するが、利用者project、backup、
  config、logを自動削除しない。
- installerの上書きupgradeは同じapplication IDを維持し、旧版のuser dataを移動・
  削除しない。
- `.jukuschedule`関連付けは、実行fileへの安全な引用符付きopen commandと旧versionの
  upgradeを検証できる場合だけ有効にする。

### 4. quality gate後にだけartifactを作る

Release workflowはWindows上で次の順を守る。

1. checkout
2. Python 3.12環境
3. dependency install
4. Ruff lint / format
5. mypy
6. pytest
7. standalone build
8. portable ZIP
9. installer
10. SHA-256
11. CI artifact upload、再download、checksum再検証
12. 明示承認済みtagに対し、repository書込み権限を分離した最終jobでdraft Release添付

quality gateまたはbuildが失敗した場合に、古いartifactを新しいversion名で公開しない。
GitHub-hosted workflowを実行していない状態は `NOT TESTED` とする。tag patternだけで
無条件に公開せず、environment approval、draft / prerelease、手動dispatch等の
承認境界を使う。

### 5. checksumとartifact検査

portable ZIPとinstallerを最終形にした後でSHA-256を計算し、
`SHA256SUMS.txt`へfile名とhashを固定する。checksum生成前のdirectoryや中間binaryを
Releaseへ添付しない。

CI artifactを再downloadし、hash一致、ZIP展開、portable起動、installer起動を確認する。
build machine上のstandalone directoryだけを試してportable成功としない。

### 6. licenseをbuild inputと受入gateにする

Runtime dependencyのlicense metadataと実際に同梱したfileをReleaseごとに棚卸しする。
GPL-3.0-onlyで配布するQt Community Editionの対応ソース・noticeと、Inno Setup
利用条件が承認されるまで、本番Releaseを公開しない。

`THIRD_PARTY_NOTICES.md`は一覧であり、全文licenseの代替ではない。Python、Qt、
推移的Python package、Qt third-party componentの必要な全文をstandalone treeへ
含め、portable / installerの両方で確認する。

### 7. offlineと個人情報

Runtimeへtelemetry、crash upload、update check、license check、cloud conversionを
追加しない。GitHub Actionsやdependency downloadはbuild時の外部通信であり、
配布appのruntime通信とは区別する。

build contextとartifactへ次を含めない。

- `.jukuschedule`、SQLite DB / sidecar
- log、optimization log
- input / output / backup
- user `config.yaml`
- 参考PDF、screen shot等の実データ
- certificate、private key、token、license key
- local absolute pathを含む不要なbuild report

### 8. SmartScreenとcode signing

初期Release候補は未署名でもよいが、SmartScreen警告とSHA-256確認をREADMEへ明示する。
利用者へOS保護の恒久無効化を案内しない。

SignPath Foundationの無料OSS署名を申請する。証明書とprivate keyをrepository、
GitHub Secrets、artifactへ置かず、署名鍵はSignPathの管理下に置く。GitHub-hosted
runnerが作ったunsigned artifactだけをconnectorへ渡し、毎回SignPath上で手動承認する。
自作の`SummerCourseScheduler.exe`だけを署名し、上流DLL/PYD/EXEはプロジェクト証明書で
署名しない。Inno Setup生成installerはSignPathから適格性の確認を得るまで対象外とする。

署名後は`Valid`、署名者`SignPath Foundation`、timestampを機械検証し、その後に
portable smokeとchecksum生成をやり直す。申請・承認前の候補は`RequireUnsigned`で
予期しない署名がないことを確認し、「unsigned」と明記する。詳細は
`docs/code_signing_policy.md`と`docs/signpath_application.md`を正本とする。

## 根拠

- 1つのstandalone treeから2形式を作るとresource、native DLL、licenseの差を減らせる。
- user dataを`%LOCALAPPDATA%`と明示project pathへ分けると、Program Filesの権限、
  portable移動、uninstallによるdata lossを避けやすい。
- quality→build→checksumの順で、失敗したsourceから配布物を作りにくくなる。
- checksumは破損・取り違えの検出に使え、code signing未導入時の確認手段になる。
- 公開承認とlicense判断をCI successから分けることで、不可逆な本番公開を自動化しない。

## 影響

良い影響:

- portableとinstallerで同じapp本体を検査できる。
- 利用者側にPython、Node.js、Qt SDKを要求しない。
- uninstall、upgrade、read-only install directoryからuser dataを分離できる。
- license、PII、checksumがRelease checklistの必須項目になる。

注意点:

- Qt / OR-Toolsを含むstandalone treeは大きくなり、buildにも時間がかかる。
- source smokeが成功しても、QML importやQt pluginの収集漏れはpackaged appで初めて
  見つかるため、clean Windows testが必要である。
- dependencyにversion rangeがあるため、同じsourceでも将来のbuildで内容が変わり得る。
  Releaseごとにversionとlicenseを記録する。
- unsigned binaryはSmartScreen警告が出る可能性がある。
- GPL-3.0-onlyは採用済みだが、Qt完成artifactとInno Setupの利用・署名条件は
  所有者の確認が必要で、技術的にbuildできることを配布可能の根拠にしない。
- GitHub-hosted Actions、clean Windows、installer upgrade / uninstallを実行していない
  場合は、workflowやscriptの存在だけでPASSにしない。

## 採用しなかった案

- Python sourceと`pip install`手順だけを利用者へ渡す: 利用者側Python不要の要件に反する。
- one-file executableだけを正本にする: 起動時展開、plugin、virus scanner、
  license確認が複雑になり、portable directoryの検査性が下がる。
- portableとinstallerを別dependency解決で作る: 内容差とlicense漏れを生む。
- user dataをapplication directoryへ保存する: Program Files権限、portableのread-only、
  uninstallによるdata lossにつながる。
- tag pushだけでproduction Releaseを自動公開する: 明示承認、license、clean PC受入を
  迂回し得る。
- certificateやInno license keyをrepositoryへ置く: secret漏えいになる。

## 検証方針

- versionがpackage metadata、About、log、帳票で一致し、DB revisionと別表示される。
- clean buildからstandalone treeを作り、resource / DLL / QML / migrationをinventoryする。
- portable ZIPを別directoryへ展開し、Python / Node.jsなし・offlineで起動する。
- installerのfresh install、上書きupgrade、shortcut、任意file association、
  uninstall、user data保持を確認する。
- 日本語user path、日本語project名、read-only app directory、long pathを確認する。
- 新規projectからPDF出力、終了、再起動、再openまでをpackaged GUIで実施する。
- portable / installerを再downloadし、`SHA256SUMS.txt`と照合する。
- artifactを展開して実データ、secret、local config、不要reportがないことを確認する。
- Runtime dependencyと全文license / noticeを完成artifactから再監査する。
- GitHub-hosted workflowのrun URL、commit、artifact IDs、結果を記録する。

未実施項目は
[`../acceptance_test_phase7.md`](../acceptance_test_phase7.md)へ `PARTIAL` または
`NOT TESTED` として残し、本番公開を行わない。
