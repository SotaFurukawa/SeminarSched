# 変更履歴

この文書は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) の考え方に沿って、
利用者に影響する変更を記録する。バージョン番号は Semantic Versioning に従う。

## [Unreleased]

- 本番 GitHub Release は未公開。
- SignPath Foundation申請に必要なCode signing policy、プライバシーポリシー、
  役割、申請・有効化手順、Authenticode検証scriptを追加。
- プロジェクト自身はGPL-3.0-only。第三者コンポーネントの公開前確認事項は
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) を参照。

## [1.0.0-rc.1] - 2026-07-29

初回リリース候補。これは最終版の公開を意味せず、受入確認と配布承認のための候補である。

### 追加

- Windows 10 / 11 x64向けの日本語PySide6 / QMLデスクトップUI。
- 講習ごとの単一SQLiteプロジェクトファイル（`.jukuschedule`）。
- プロジェクト、コマ、開校日、科目、生徒、講師、講師対応科目、受講希望の管理。
- マスターExcel、アンケートxlsx / CSV、集団授業xlsxの取込み・検証・差分確認。
- OR-Tools CP-SATによる、未配置を許容しつつハード制約を破らない辞書式最適化。
- 時間割グリッド、手動編集、即時検証、授業単位ロック、Undo / Redo、監査ログ、
  ロックを保持する全体再最適化。
- 全体・生徒別・講師別・未配置／警告のExcel / PDF、割当て生データCSV、
  PDF印刷プレビュー。
- アプリ版とDBスキーマ版を区別するAbout表示および帳票のアプリ版表示。
- Windowsポータブル版、インストーラー、SHA-256一覧を作るための配布基盤。
- CIの品質検査と、タグを入力とするWindows配布ワークフロー。
- 利用者マニュアル、トラブルシューティング、性能記録、受入表、リリースチェックリスト。

### 安全性

- QML、業務ロジック、DB、最適化、取込み、出力を分離。
- 最適化結果と手動編集を独立validatorで再検査し、ハード制約違反を保存・出力しない。
- プロジェクト複製と帳票出力は一時ファイル経由で成功後だけ置換。
- migration前バックアップ、手動バックアップ、監査ログ、ローカル技術ログ。
- テレメトリ、クラウドDB、Google API必須連携を含まない完全ローカル動作。

### 既知の制限

- 本番GitHub Release、タグ、署名済み成果物は作成していない。
- 署名なし実行ファイルはWindows SmartScreenの警告対象になり得る。
- 同一build machineでのfresh install／uninstallは確認済みだが、クリーンな別Windows
  PC、上書きupgrade、offline、実プリンター、OneDrive同期競合、長時間GUI操作は、
  実施結果が受入表で `PASS` になるまで保証しない。
- 最深部がおよそ264文字になる過長なinstall pathではinstallerがrollbackした。
  通常の短い日本語pathは確認済みだが、OS上限近傍のpath対応は保証しない。
- 選択範囲だけの部分再最適化、一括ロック、再起動をまたぐUndo / Redoは未実装。
- 指定参考PDFが不在のため、実帳票との視覚的な直接比較は未実施。
- Qt Community EditionのGPLv3互換性、対応ソース、第三者noticeは完成artifactに対して
  公開前の最終監査が必要。
