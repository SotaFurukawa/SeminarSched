# Release前チェックリスト

このチェックリストは `v1.0.2` Releaseを検証するためのものです。
チェックが埋まっただけで本番公開を許可しません。本番タグとGitHub Releaseには
リポジトリ所有者の明示承認が必要です。

## 1. 変更範囲と版

- [ ] `docs/specification.md`と対象機能の受入基準を再確認した。
- [ ] `CHANGELOG.md`が実装と一致し、存在しない機能を記載していない。
- [ ] `pyproject.toml`、`summer_scheduler.__version__`、About、ログ、帳票のapp versionが一致する。
- [ ] DB schema revisionとapp versionを別々に表示している。
- [ ] Release tagはソース内versionと一致する `v1.0.2` である。
- [ ] git statusとdiffを確認し、無関係な変更、生成物、実データがない。

## 2. ライセンス・権利

- [ ] 権利者がプロジェクト自身のlicenseを選択し、正式な`LICENSE`を承認した。
- [ ] Qt Community EditionをGPL-3.0-only経路で配布し、完成artifactの全module、
  対応ソース、noticeを確認した。
- [ ] 使用Qt moduleと完成artifactに対応するQt third-party notice / SBOMを確認した。
- [ ] Inno Setup採用versionの`LICENSE.TXT`条件、commercial user該当性、公式の
  購入要請への対応方針を記録した。購入要請と、商用利用も許可する基礎ライセンスの
  使用許諾を混同していない。
- [ ] 完成portableからruntime依存を再棚卸しし、`THIRD_PARTY_NOTICES.md`を更新した。
- [ ] Python、Qt、各Python packageの全文license / noticeがportableとinstallerに入っている。
- [ ] 法務または配布責任者の承認記録がある。

1件でも未完了なら本番公開しない。詳細は
[`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)を参照します。

## 3. 個人情報・秘密情報・外部通信

- [ ] `git ls-files`と履歴を確認し、実DB、`.jukuschedule`、log、入力、出力、backup、
  参考PDF、screen shotに実データがない。
- [ ] test / sample / docsの氏名、ID、校舎名はすべて架空である。
- [ ] build context、portable ZIP、installerを展開し、実データやlocal設定がない。
- [ ] API key、token、certificate、private key、Inno license key、絶対user pathがない。
- [ ] 通常ログとcrash logに氏名、回答行、帳票本文、snapshotが記録されない。
- [ ] アプリruntimeにテレメトリ、update check、クラウド送信、必須network通信がない。
- [ ] GitHub Actionsのrelease権限は該当jobだけ、必要最小限である。

## 4. 品質ゲート

Release buildと同じcommitで実行します。

```powershell
python -m pip check
ruff check .
ruff format --check .
mypy src tests
pytest
```

- [ ] `pip check`: broken requirementsなし。
- [ ] `ruff check .`: 成功。
- [ ] `ruff format --check .`: 成功。
- [ ] `mypy src tests`: 成功。
- [ ] `pytest`: skip / xfailで失敗を隠さず成功。
- [ ] 全QMLを`qmllint`で検査。
- [ ] source版のoffscreen smokeが成功。
- [ ] Phase 4中核シナリオがすべて成功。
- [ ] Phase 5編集・lock・Undo / Redo・transaction testが成功。
- [ ] Phase 6 Excel / PDF / CSVと原子的保存testが成功。
- [ ] Phase 7 backup / recovery / version / packaging testが成功。

各コマンド、件数、所要時間、warningをReleaseの検証記録へ残します。実データ、
個人名、ローカルパス、ログ本文は公開記録へ転載しません。

## 5. DBとデータ安全性

- [ ] 空DBへAlembic `head`を適用できる。
- [ ] 旧schema `0001`から現行headまでupgradeできる。
- [ ] 直前schemaからupgrade / downgrade / upgradeを確認した。
- [ ] migration前backupが成功しない場合、migrationを開始しない。
- [ ] project作成、別名保存、複製、backupが原子的に完了する。
- [ ] 保存失敗時に元ファイルと既存出力を保持する。
- [ ] 自動backupの世代数、復元方法、個人情報注意が実装どおりである。
- [ ] 破損DB、read-only、権限不足、容量不足、同名上書き、長いpath、日本語pathを確認した。
- [ ] OneDrive同期中の競合を成功扱いせず、日本語エラーと復旧案を表示する。
- [ ] uninstall時に`.jukuschedule`、backup、config、logを勝手に削除しない。

## 6. 性能

- [ ] `docs/performance.md`の環境と入力条件を記録した。
- [ ] 起動、読込み、一覧、取込み、検証、scroll、Excel、PDF、memoryを目標規模で測定した。
- [ ] 30秒、120秒、600秒presetを測定し、statusと配置／未配置も記録した。
- [ ] 実GUIが長時間処理中に固まらず、中止操作を確認した。
- [ ] 未測定値を推測で補っていない。

未測定項目はRelease受入表で `NOT TESTED` のままにします。

## 7. Windows portable build

- [ ] repository、`.venv-release`、`build`、`dist`の実体パスがASCIIのみで、
  `subst`／junction／symbolic linkで非ASCII実体パスを隠していない。
- [ ] 清潔なbuild directoryからportableを生成した。
- [ ] QML、QtQuick / QtQuick.Controls / QtQuick.Pdf、Qt plugin、SQLite、OR-Tools、
  migration、YAML resourceを含む。
- [ ] source、test、cache、build report、実データを不要に含めていない。
- [ ] `THIRD_PARTY_NOTICES.md`と全文license directoryを含む。
- [ ] artifact名が `SummerCourseScheduler-Portable-1.0.2.zip` と一致する。
- [ ] ZIPを日本語名の別directoryへ展開して起動した。
- [ ] Python、Node.js、Qt、Visual StudioのないWindows x64で起動した。
- [ ] 管理者権限なし、offline、USB相当の別driveで確認した。
- [ ] app本体の隣ではなく、利用者別local領域へconfig / log / app DBを保存した。
- [ ] 展開後のapplication treeをread-onlyにしても、書込み可能な利用者別local領域と
  project／出力先を使って動作する。

## 8. Windows installer

- [ ] artifact名が `SummerCourseScheduler-Setup-1.0.2.exe` と一致する。
- [ ] app名、version、publisher、install先が正しい。
- [ ] Start menu shortcutと任意desktop shortcutが正しい。
- [ ] `.jukuschedule`関連付けを採用する場合、引用符・icon・open動作を確認した。
- [ ] fresh installと上書きupgradeが成功する。
- [ ] 旧版を検出し、別製品として二重登録しない。
- [ ] uninstallがapp本体とshortcutを削除する。
- [ ] uninstallがproject、backup、config、logを削除しない。
- [ ] installer / uninstallerの再起動要求、権限、残留fileを記録した。
- [ ] 署名なしの場合のSmartScreen手順をREADMEとtroubleshootingへ記載した。

## 9. end-to-end受入

クリーンWindows環境で次を1つの架空プロジェクトとして通します。

- [ ] 起動。
- [ ] 新規プロジェクト。
- [ ] コマ・開校日。
- [ ] 生徒・講師・科目・講師対応科目・LessonRequest。
- [ ] 生徒・講師アンケート。
- [ ] 集団授業。
- [ ] 入力検証。
- [ ] 自動最適化。
- [ ] 未配置・理由。
- [ ] 手動編集。
- [ ] lock。
- [ ] lockを保持する再最適化。
- [ ] Excel / PDF / CSV。
- [ ] 手動保存 / backup。
- [ ] 終了、再起動、再読込み。
- [ ] backup復元。
- [ ] uninstall後もproject fileが残る。

実在する個人情報は使いません。

## 10. checksumとartifact検査

- [ ] installerとportable ZIPを最終形にした後でSHA-256を計算した。
- [ ] `SHA256SUMS.txt`のfile名、hash、改行を確認した。
- [ ] 別directoryへdownload / copyしたartifactでSHA-256一致を再確認した。
- [ ] ZIPのCRC / 展開に失敗がない。
- [ ] installerをWindows Defender等でscanし、結果を記録した。
- [ ] artifact retentionとRelease添付対象が同じfileである。

## 11. GitHub Actions

- [ ] branch / pull requestのCIが成功した。
- [ ] release workflowを手動dry-runまたはpre-release tagで検証した。
- [ ] checkout、Python 3.12、dependency install、Ruff、format、mypy、pytestを実行した。
- [ ] Windows build、portable ZIP、installer、SHA-256を生成した。
- [ ] artifact upload後に再downloadしてchecksumを確認した。
- [ ] failure時にReleaseを作成しない。
- [ ] production environment / approval gateを設定した。
- [ ] action versionとpermissionをreviewした。

GitHub-hosted Actionsを実行していない場合、workflow fileの存在だけで `PASS` にしません。

## 12. SmartScreenと署名

- [ ] 未署名成果物でpublisherが「不明」となり得ることをRelease noteに明記した。
- [ ] 「詳細情報」から進む前に、公式Release URLとSHA-256確認を案内した。
- [ ] 利用者へSmartScreen、antivirus、組織policyの無効化を推奨していない。
- [ ] 署名する場合、秘密鍵をhardware / secret storeで管理し、repositoryへ置いていない。
- [ ] executableとinstallerの両方へtimestamp付き署名を行い、検証した。

### SignPath Foundationを使用する場合

- [ ] GitHubとSignPathの多要素認証を有効にした。
- [ ] READMEから`Code signing policy`と`PRIVACY.md`へ到達できる。
- [ ] Authors / Reviewers / Approversと毎回の手動承認をSignPathへ設定した。
- [ ] GitHub-hosted runnerが生成してuploadしたunsigned artifactから署名要求した。
- [ ] 自作の`SummerCourseScheduler.exe`だけを署名し、上流DLL/PYD/EXEを
  プロジェクト証明書で署名していない。
- [ ] `scripts/verify_authenticode.ps1 -RequireSigned`が、`Valid`、
  `SignPath Foundation`、timestampを確認した。
- [ ] 署名をすべて終えた後でsmoke testとSHA-256生成をやり直した。
- [ ] Inno Setup生成installerを対象にする場合、SignPathから適格性の確認を得た。

承認前の具体的な申請内容と承認後のCI設定は
[`signpath_application.md`](signpath_application.md)を参照します。

## 13. 公開承認

- [ ] [`acceptance_test_phase7.md`](acceptance_test_phase7.md)のFAIL / PARTIAL /
  NOT TESTEDを配布責任者が確認した。
- [ ] 既知の制限と回避策をRelease noteへ転記した。
- [ ] Release候補のartifact、checksum、test結果、licenseを責任者へ提示した。
- [ ] 本番公開の明示承認を得た。
- [ ] 承認後だけ正式tag / GitHub Releaseを作成した。

最後の2項目は今回の自動作業ではチェックしません。
