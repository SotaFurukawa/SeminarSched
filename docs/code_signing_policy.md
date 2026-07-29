# Code signing policy

Status: **SignPath Foundationへ申請準備中です。現在公開済みの成果物は未署名です。**

申請が承認された後のコード署名には、次の提供元を使用します。

**Free code signing provided by [SignPath.io](https://signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/).**

この表示は申請の承認や現在の成果物の署名済み状態を主張するものではありません。
署名済み成果物は、Windowsのプロパティで署名状態と署名者を確認できるものだけを、
リリースページで明確に「署名済み」と表示します。

## 担当者と役割

現在のプロジェクトチームは1名です。

- Authors / Committers: [@SotaFurukawa](https://github.com/SotaFurukawa)
- Reviewers: [@SotaFurukawa](https://github.com/SotaFurukawa)
- Approvers: [@SotaFurukawa](https://github.com/SotaFurukawa)

外部からのPull Requestは、上記Reviewerのレビュー後に取り込みます。署名要求は、
上記Approverが対象commit、CI、テスト、成果物、バージョン、ライセンスを確認して、
SignPath上で毎回手動承認します。GitHubとSignPathの両方で多要素認証を使用します。

## 署名対象と信頼境界

- 署名対象は、このリポジトリのソースからGitHub-hosted runnerで生成した
  `SummerCourseScheduler.exe`だけです。
- Qt、CPython、OR-Tools等の上流DLL/PYD/EXEを、このプロジェクトの証明書では
  署名しません。未署名の上流OSSバイナリは配布物に含まれる場合があります。
- Inno Setup製インストーラーは、SignPath Foundationの適格性確認が取れるまで
  初回申請の署名対象外です。インストーラーを対象へ追加する場合も、内部の上流
  バイナリは署名せず、プロジェクトが生成した外側のセットアップEXEだけを対象にします。
- 秘密鍵や証明書はリポジトリ、GitHub Secrets、成果物へ保存しません。署名鍵は
  SignPathの管理下に置き、GitHub Actionsには署名要求用API tokenだけを登録します。

## ビルド、版、承認

署名要求は、保護されたタグと完全一致する`pyproject.toml`の版から生成します。
実行ファイルのProduct nameは`SummerCourseScheduler`とします。Windowsの数値版である
Product versionとFile versionは、Semantic Version（例: `1.0.0-rc.1`）から
`1.0.0.0`へ変換し、同一ビルド内で一致させます。表示用のProduct text versionは
元のSemantic Versionと一致させます。GitHub Actionsで品質検査、固定依存の検証、
standalone smoke、配布内容検査を通し、unsigned artifactをGitHubへ保存してから
SignPath connectorへ渡します。署名後にAuthenticode、署名者、timestampを検証し、
最後にSHA-256を計算します。署名前のchecksumを署名後へ流用しません。

署名構成を含むbuild scriptとworkflowの変更は、アプリコードと同じレビュー対象です。
失敗、拒否、timeout、署名者不一致を成功として扱わず、未署名成果物へ自動的に
フォールバックして「署名済み」と公開することはありません。

## プライバシー

[プライバシーポリシー](../PRIVACY.md)を参照してください。

> This program will not transfer any information to other networked systems unless
> specifically requested by the user or the person installing or operating it.

## 利用者による確認

署名後のPowerShell確認例です。

```powershell
$signature = Get-AuthenticodeSignature .\SummerCourseScheduler.exe
$signature.Status
$signature.SignerCertificate.Subject
$signature.TimeStamperCertificate.Subject
```

`Status`が`Valid`で、署名者が`SignPath Foundation`を含み、timestamp証明書が存在する
ことを確認します。GitHub Releaseの`SHA256SUMS.txt`も併せて照合してください。
