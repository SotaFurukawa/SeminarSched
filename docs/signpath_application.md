# SignPath Foundation申請・有効化手順

この文書は申請準備と、承認後に行うGitHub Actions連携を分離する。未取得のIDやtokenを
仮値で有効化せず、未署名成果物を署名済みと表示しない。

## 1. 申請前に完了すること

1. 公開リポジトリ
   [SotaFurukawa/SeminarSched](https://github.com/SotaFurukawa/SeminarSched)で、
   CIが成功している状態を維持する。
2. `v1.0.0-rc.2`等のprereleaseを、将来署名したいportable ZIPと同じ構造で、
   **未署名であることを明記して先に公開**する。SignPathは署名対象の形式で既に
   リリースされているプロジェクトを条件としている。
3. READMEの[Code signing policy](code_signing_policy.md)、`PRIVACY.md`、
   `LICENSE`、機能説明、インストール・アンインストール手順を公開する。
4. GitHubの2要素認証を維持し、SignPathアカウント作成時にも多要素認証を有効にする。
5. 完成artifactの第三者licenseとQt moduleを監査する。未解決項目は
   `docs/release_checklist.md`で未完了のままにする。

## 2. 申請内容

- Project: `SummerCourseScheduler`
- Repository: `https://github.com/SotaFurukawa/SeminarSched`
- License: `GPL-3.0-only`
- Platform / artifact: Windows x64 portable ZIP
- Own binary to sign: `SummerCourseScheduler/SummerCourseScheduler.exe`
- Publisher/product metadata: Product name `SummerCourseScheduler`、タグと一致するversion
- Authors / Reviewers / Approvers: `SotaFurukawa`
- Privacy policy: `https://github.com/SotaFurukawa/SeminarSched/blob/main/PRIVACY.md`
- Code signing policy:
  `https://github.com/SotaFurukawa/SeminarSched/blob/main/docs/code_signing_policy.md`
- Build system: GitHub ActionsのGitHub-hosted Windows runner

初回申請はportable ZIP内の自作EXEだけを対象にする。Inno Setupはbuild toolの
ライセンスがOSI承認ライセンスであるかをこのプロジェクト側で断定できないため、
セットアップEXEも無料OSS署名の対象にできるか、申請時にSignPathへ確認する。
確認が得られるまでinstallerをartifact configurationへ追加しない。

## 3. Artifact configurationで要求する内容

SignPath担当者と次を確認して構成する。

- GitHub `upload-artifact`が作る外側ZIPを展開する。
- portable ZIPを展開し、相対パスが完全一致する
  `SummerCourseScheduler/SummerCourseScheduler.exe`だけをAuthenticode署名する。
- `*.exe`や`*.dll`のワイルドカードで上流バイナリを署名しない。
- Product nameを`SummerCourseScheduler`へ制限する。
- Product/File versionをworkflowのversion parameterへ制限し、同じbuild内で一致させる。
- timestampを必須にする。
- signing policyにApproverの毎回手動承認を必須設定する。

構成slugやIDはSignPathが発行するため、リポジトリへ仮値をコミットしない。

## 4. 承認後のGitHub設定

1. SignPath GitHub Appへ、このリポジトリだけのアクセスを許可する。
2. GitHub Environment `signpath-production`を作り、required reviewerを設定する。
3. Environment secret `SIGNPATH_API_TOKEN`を登録する。
4. 非secretのEnvironment variablesへ、SignPathから通知された
   `SIGNPATH_ORGANIZATION_ID`、`SIGNPATH_PROJECT_SLUG`、
   `SIGNPATH_SIGNING_POLICY_SLUG`、必要なら
   `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG`を登録する。
5. 公式
   `signpath/github-action-submit-signing-request@v2`を、unsigned artifactを
   `actions/upload-artifact@v4`以上で保存した直後に組み込む。
6. 署名済みartifactを別directoryへ出力し、
   `scripts/verify_authenticode.ps1 -RequireSigned`を通す。
7. 署名後のportable ZIPを作り直してsmoke testを行う。installerが承認範囲なら、
   署名済みアプリからinstallerを作成し、外側のsetup EXEも別の署名要求で署名する。
8. 全署名完了後に`SHA256SUMS.txt`を生成し、draft releaseへ添付する。

SignPathのorganization ID、slug、tokenが発行される前はworkflowを有効化しない。
承認後は[公式GitHub connector手順](https://docs.signpath.io/trusted-build-systems/github)
を正本として、その時点のaction versionと入力仕様を再確認する。

## 5. 公開前の停止条件

- SignPath上の要求が手動承認されていない。
- Authenticodeが`Valid`でない、署名者が`SignPath Foundation`でない、timestampがない。
- 自作EXE以外がプロジェクト証明書で署名されている。
- 署名後のsmoke、checksum、license監査、clean Windows受入が失敗した。
- SignPathがInno Setup生成installerの適格性を確認していない。

いずれかに該当する場合は署名済みReleaseとして公開しない。未署名prereleaseを残す場合は
「unsigned」を明記し、署名済み成果物と同じファイル名で置き換えない。
