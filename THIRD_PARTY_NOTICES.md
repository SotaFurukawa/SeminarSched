# 第三者ソフトウェアと配布前ライセンス確認

最終監査日: 2026-07-29

## 1. この文書の位置づけ

この文書は、リリース候補を作るWindows環境のインストール済み配布メタデータ
（`*.dist-info/METADATA`、`License-Expression`、`License`、license classifier、
同梱license file）と各プロジェクトの公式文書を照合した技術監査記録である。
法的助言や権利者による許諾を代替しない。

実際に配布するバイナリに含まれる依存はビルド方式、Python patch版、依存解決日時で
変わり得る。各Releaseでは完成したportableディレクトリを正本として再棚卸しし、
この一覧、全文ライセンス、著作権表示、Qtの第三者noticeを更新すること。

## 2. Windowsバイナリ公開前の確認事項

### プロジェクト自身のライセンス

プロジェクトのソースコードは、リポジトリ直下の`LICENSE`に収録した
GNU General Public License version 3（GPL-3.0-only）で公開する。第三者依存、
ビルドツール、画像等にはそれぞれのライセンスが適用されるため、プロジェクトのGPLを
それらのライセンス全文やnoticeの代わりにしてはならない。

### Qt / PySide6

今回のPyPI Community EditionのメタデータはPySide6、PySide6 Essentials/Addons、
Shiboken6を `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` と示す。Qt公式文書も
Qt for PythonをLGPLv3/GPLv3またはQt商用ライセンスで提供すると説明している。

- [Qt for Python公式概要](https://doc.qt.io/qtforpython-6/)
- [Qt Licensing](https://doc.qt.io/qt-6/licensing.html)
- [Qt for Pythonの第三者ライセンス一覧](https://doc.qt.io/qtforpython-6/licenses.html)

完成したWindowsバイナリについて、次を公開前に確認する。

1. Community Editionで完成artifactに含まれる全Qt moduleがGPLv3互換であること。
2. Qt / PySide6のライセンス全文、copyright、Qt第三者notice、SBOM、必要な対応ソース
   または取得案内を同梱していること。
3. 不要なQt moduleをstandalone成果物から除外し、実際の成果物から再棚卸しすること。

ソースコードをGPLv3で公開しても、ライセンス全文やQt SBOM / third-party noticesの
同梱は自動では完了しない。完成artifactから必ず再確認する。

### Inno Setup

Inno Setupはアプリの実行時依存ではなく、インストーラーを生成するbuild toolである。
公式`LICENSE.TXT`は、所定の表示・再配布・出所表示条件の下で、商用を含む任意用途への
利用を許可する。これとは別に、公式購入ページはcommercial userへcommercial license
購入を要請しているが、FAQではstrictly requiredではないと説明している。CIによる
compiler実行も公式上の「using」に含まれ、commercial userには最低single-user license
の購入が期待される一方、license keyをCI machineへ登録する必要はない。

- [Inno Setup概要とライセンス案内](https://jrsoftware.org/ishelp/topic_whatisinnosetup.htm)
- [Inno Setup commercial license Q&A](https://jrsoftware.org/isorder.php)

配布主体はcommercial user該当性と購入・割当方針を記録し、購入要請と基礎ライセンスに
よる使用許諾を混同しない。license key、購入情報、証明書をリポジトリやCI artifactへ
含めない。

## 3. 実行時Python依存の監査結果

次は2026-07-29のPython 3.12仮想環境で、`pyproject.toml`の直接依存から環境markerを
評価してたどった推移的依存である。version rangeを持つ依存は将来同じ版になる保証が
ないため、Releaseごとに再生成する。

| パッケージ | 監査版 | METADATA上のlicense |
|---|---:|---|
| alembic | 1.18.5 | MIT |
| openpyxl | 3.1.5 | MIT |
| ortools | 9.14.6206 | Apache-2.0（metadata表記: Apache 2.0） |
| platformdirs | 4.11.0 | MIT |
| PySide6 | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PyYAML | 6.0.3 | MIT |
| SQLAlchemy | 2.0.51 | MIT |
| Mako | 1.3.12 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |
| et_xmlfile | 2.0.0 | MIT |
| absl-py | 2.5.0 | Apache-2.0 |
| numpy | 2.5.1 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0（vendored codeを含む） |
| pandas | 3.0.5 | BSD-3-Clause |
| protobuf | 6.31.1 | BSD-3-Clause |
| immutabledict | 4.3.1 | MIT |
| PySide6_Essentials | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| PySide6_Addons | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| shiboken6 | 6.11.1 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| greenlet | 3.5.4 | MIT AND PSF-2.0 |
| python-dateutil | 2.9.0.post0 | BSD-3-Clause / Apache-2.0 dual license（metadata表記: Dual License） |
| tzdata | 2026.3 | Apache-2.0 |
| six | 1.17.0 | MIT |

`numpy`等は複数のvendored componentを含む。表の短いlicense名だけを全文licenseの
代替にしない。ビルド成果物へ実際に含まれた各distributionのlicense directoryを収集し、
欠落がないか確認する。

## 4. 同梱runtimeとbuild tool

| 対象 | 位置づけ | 配布時の確認 |
|---|---|---|
| CPython 3.12系 | standalone成果物にPython runtimeを同梱 | PSF License Version 2とPythonに取り込まれた第三者licenseを同梱する。[Python公式license](https://docs.python.org/3/license.html) |
| SQLite | CPython標準`sqlite3`が使用するruntime | SQLite本体はpublic domain。完成artifactの実体とPython側noticeも確認する。[SQLite公式](https://www.sqlite.org/copyright.html) |
| Nuitka / pyside6-deploy | build時と生成runtime | 現在環境のNuitka 4.0はAGPL-3.0で、生成binary向けのRuntime Library Exceptionを同梱する。採用版、compiler license、exception、生成reportをReleaseごとに記録する。[Nuitka公式download / license](https://nuitka.net/doc/download.html) |
| Inno Setup | installer生成時のみ | 採用版の`LICENSE.TXT`とcommercial-use条件を確認する。compilerやlicense key自体を成果物へ含めない |
| GitHub Actions | CIサービス／action | actionを配布バイナリへ同梱しない。使用commitまたはmajor tag、permissions、供給元をレビューする |

## 5. 配布物に必要な構成

portable ZIPとinstallerの双方がインストールするapplication directoryに、最低限
次を含める。実際のbuild scriptがこの文書をコピーするだけでなく、完成artifactを
展開して検査する。

```text
THIRD_PARTY_NOTICES.md
licenses/
  THIRD_PARTY_NOTICES.txt
  CPython-<version>/
    LICENSE.txt
  Nuitka-<version>/
    LICENSE.txt
    LICENSE-RUNTIME.txt
  <Python-distribution>-<version>/
    licenses/ または各distributionのlicense / notice
```

- 選択したプロジェクトlicense（決定後）。
- CPythonの`LICENSE.txt`とincorporated software acknowledgements。
- 使用するQt / PySide6 / Shiboken6のLGPL/GPLまたは商用配布に必要な文書。
- 使用したQt moduleの第三者license / SBOM / notice。
- runtimeに含まれる各Python distributionのlicense、copyright、NOTICE。
- Apache-2.0 componentの必要なNOTICE（上流に存在する場合）。
- Nuitkaで生成した場合は、採用版のAGPL-3.0 compiler licenseと
  `Nuitka Runtime Library Exception`。Nuitka 4.0のexceptionは、対象runtimeと
  independent moduleを通常のcompilation processで組み合わせた生成物を任意条件で
  conveyできる追加許可を示すが、compiler自身を独自条件で再配布する許可ではない。

ライセンスファイルの収集元を開発環境の絶対パスに固定しない。ビルド環境で解決した
distributionと完成portable directoryを照合し、取りこぼしをエラーにする。

## 6. 公開前チェック

- [ ] 権利者がプロジェクトlicenseを決定し、`LICENSE`を承認した。
- [ ] Qt Community Editionの条件またはQt commercial licenseのどちらで配布するか承認した。
- [ ] Inno Setupの利用形態と採用版に対するlicenseを確認した。
- [ ] portable ZIPを展開し、含まれるPython package / DLLを再棚卸しした。
- [ ] Python、Qt、全runtime依存の全文license / noticeがportableとinstallerの双方にある。
- [ ] Qtの第三者SBOM / noticesを採用Qt版と使用moduleに絞って確認した。
- [ ] Nuitkaの採用版、AGPL-3.0、Runtime Library Exception、生成物へ実際に含まれた
  runtime fileを確認した。
- [ ] 秘密鍵、証明書、license key、実データ、個人情報が成果物にない。
- [ ] 法務または配布責任者の承認記録を残した。

これらが完了するまではローカルの技術検証用リリース候補に留め、本番公開しない。
