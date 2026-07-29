# ADR 0003: 設定、DB、ログを利用者別ローカル領域へ置く

- 状態: 採用
- 日付: 2026-07-28
- 対象: Phase 0 / Phase 1

## コンテキスト

アプリは完全ローカルで動作し、個人情報を外部送信しない。開発リポジトリ、Windows のインストール先、OneDrive 同期フォルダへ実運用 DB やログを書き込むと、権限エラー、同期競合、誤 commit、配布物への混入につながる。既定設定は配布物に含めつつ、利用者が必要な項目だけを上書きできる必要がある。

## 決定

`platformdirs` と `pathlib.Path` を使い、Phase 1 の既定保存先を次のようにする。

| 種別 | 場所 |
|---|---|
| 内蔵既定設定 | package resource `src/summer_scheduler/resources/default_settings.yaml` |
| 利用者設定 | `%LOCALAPPDATA%\SummerScheduler\config.yaml` |
| SQLite DB | `%LOCALAPPDATA%\SummerScheduler\data\summer_scheduler.db` |
| アプリログ | `%LOCALAPPDATA%\SummerScheduler\logs\summer_scheduler.log` |

設定は内蔵 YAML を先に読み、利用者 YAML を重ね、保存先を指定する環境変数を最後に反映する。利用者設定が存在しないことは正常とする。明示指定した設定ファイルの欠落や、利用する値の型・値が不正な場合は起動エラーとして扱う。内蔵設定は実行時に変更しない。

テスト、CI、障害調査で保存先を安全に差し替えられるよう、`SUMMER_SCHEDULER_CONFIG`、`SUMMER_SCHEDULER_DATA_DIR`、`SUMMER_SCHEDULER_DATABASE_PATH`、`SUMMER_SCHEDULER_LOG_DIR` を用意する。

ログは Python 標準 `logging` のローテーションを使用する。利用者向けエラーは日本語、技術情報はローカルログに記録する。氏名、アンケート回答、授業内容などの個人情報を必要以上にログへ残さない。最適化ログは Phase 4 で別ファイルに分ける。

実データ、DB、SQLite sidecar、設定上書き、ログ、入力、出力、バックアップ、参考 PDF は Git の管理対象外とする。

## 根拠

- Windows の利用者別書込み可能領域を使い、Program Files 等の権限問題を避けられる。
- source tree と実運用データを分離し、誤 commit と配布物への混入を防ぎやすい。
- 稼働 DB を OneDrive 同期の既定対象から外し、同期中の SQLite 競合リスクを下げる。
- YAML は人が編集でき、最上位仕様が設定形式として認めている。
- platformdirs により将来 macOS を追加するときも OS 固有パスを一か所に閉じ込められる。

## 影響

良い影響:

- 通常起動で source tree を変更しない。
- 設定、DB、ログの場所を利用者へ案内しやすい。
- テストでは path resolution を一時ディレクトリへ差し替えられる。

注意点:

- `%LOCALAPPDATA%` は通常 roaming 対象ではない。複数校舎共有やクラウド同期は初期版の対象外である。
- 利用者が DB を別場所へ移す機能と `.jukuschedule` 形式は将来別途設計する。
- 設定ファイル破損時は黙って全項目を既定値に戻さず、日本語エラーとログを出す必要がある。
- ログ保存期間とサイズ上限を設定可能にし、個人情報を含み得ることを利用者へ案内する必要がある。
- プロジェクトの明示保存では、一時ファイルと atomic replace、保存前 backup を採用する必要がある。

## 採用しなかった案

- リポジトリ直下へ DB / log を保存: 誤 commit と書込み権限、OneDrive 同期の問題がある。
- current working directory 基準: ショートカットや配布版の起動場所により保存先が変わる。
- Windows Registry だけに設定を保存: バックアップ・移動・検証が難しく、マスター仕様のローカルファイル運用と合いにくい。
- 利用者設定を必須にする: 初回起動を不必要に複雑にする。
- telemetry / 外部 error reporting: 個人情報を外部へ送らない要件とテレメトリ禁止に反する。

## セキュリティとプライバシーの規則

- password、API key、個人データを内蔵 YAML や source code に入れない。
- 実ファイルを test fixture にコピーしない。架空データと一時ディレクトリを使う。
- 例外ログに record 全体や Excel 行全体を安易に出さない。
- 将来の backup / export UI では、ファイルに個人情報が含まれることを明示する。
