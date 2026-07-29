# ADR 0009: プロジェクトのバックアップと復旧を原子的なローカル処理にする

- 状態: 採用
- 日付: 2026-07-29

## 背景

`.jukuschedule`はSQLiteであり、生徒、講師、希望日時、時間割などの個人情報と業務
データを含む。Phase 2までにSQLite backup APIによる手動コピーとmigration前退避は
あったが、次は未実装だった。

- 自動バックアップの世代管理
- SQLite破損の明示的な検出
- 異常終了またはopen失敗後の復旧候補
- 現在ファイルを失わないバックアップからの復元
- 読取専用、同期ロック、容量不足、権限、長いpathの区別

SQLiteを開いたままExplorerでコピーする運用や、破損DBへ直接SQLを実行する修復は、
整合性とハード制約の保存データを損なうおそれがある。

## 決定

### 整合したsnapshotと世代管理

有効なプロジェクトのsnapshotはSQLite backup APIで同一保存先の一時ファイルへ作り、
`PRAGMA integrity_check`と必須tableを確認してから`os.replace`する。自動backup名は
元pathのSHA-256由来の短いkeyとUTC timestampで構成し、プロジェクトごとに新しい
設定世代数だけを残す。

既定は5世代、5分間隔とする。値は組込みYAMLまたは利用者YAMLの`backup`で変更する。
間隔timerはアプリ起動層、実処理は`ProjectService`に置き、QMLはファイル操作やDB操作を
直接行わない。プロジェクトopen直後にも最初の自動snapshotを作る。

### open前の検査と異常終了marker

プロジェクトopenではmigrationより前に、read-only接続で次を確認する。

1. `PRAGMA integrity_check`が`ok`だけを返す
2. `course_projects`と`alembic_version`が存在する
3. ファイルと親folderに書込み可能である
4. 短い`BEGIN IMMEDIATE`を取得でき、別processや同期処理のlockがない

openしたpathは利用者別backup directoryの`recovery-session.json`へ原子的に記録し、
正常close時だけ削除する。次回起動時にmarkerが残っていれば「正常終了を確認できない」
復旧対象として扱う。open失敗時も、そのpathを復旧対象として保持する。

markerはローカル専用で、ネットワーク送信しない。path自体が業務情報を含む可能性が
あるためGit管理対象外とし、技術logへ値を複製しない。

### 安全な復元

選択backupを直接復元先へ上書きしない。次の順序を固定する。

1. 選択backupを`integrity_check`する
2. 一時SQLiteへcopyし、必要なmigrationと1プロジェクト不変条件を検証する
3. 既存の復元先があれば、必ず`pre_restore` backupを作る
4. 有効な復元先はSQLite backup API、破損した復元先は証跡保全のためbyte単位で退避する
5. 現在接続を閉じてから、検証済み一時SQLiteを`os.replace`する
6. 復元先を通常のopen経路で再検証する

準備、復元前退避、最終replaceのどれかが失敗した場合、その時点より前で処理を止める。
復元前退避を作れない状態で既存ファイルを置き換えない。選択backupが破損していれば、
現在のプロジェクトには一切触れない。

### 利用者向けエラーと個人情報

OS / SQLiteの例外は握り潰さず、次を区別した日本語messageへ変換する。

- ディスク空き容量不足
- 読取専用または権限不足
- OneDrive等の同期・別process lock
- path長超過
- SQLite形式不正または整合性破損

UIには、手動・自動・migration前・復元前のすべてのbackupにも元プロジェクトと同じ
個人情報が含まれることを明示する。外部通信、telemetry、自動uploadは追加しない。

## 結果

- 日本語pathでもプロジェクト単位の自動backupを列挙・世代整理できる。
- 異常終了markerまたはopen失敗後、ホーム画面から候補の整合性を見て復元できる。
- 復元はApplication Service境界からテストでき、QMLへSQLite処理を置かない。
- migration前backupと復元前backupも同じ候補一覧に表示できる。
- backup directoryの必要容量は世代数に比例する。

## 制限

- backupは暗号化しない。Windows accountと保存folderのaccess権で保護する。
- 自動backup間隔timerはアプリが実行中でイベントループが動いている間だけ機能する。
- OneDriveやantivirusの外部lock解除そのものは行わず、明示error後に再試行を求める。
- 任意folderの手動backupは自動候補一覧へ登録しないが、ファイル選択から復元できる。
- SQLite内部の自動修復は行わない。破損元を保全し、整合したbackupへ戻す。

## 却下した案

- 接続中DBの単純なbyte copyだけにする: 有効DBの一貫したsnapshotを保証しにくい。
- 破損DBへ自動修復SQLを実行する: 元データと業務制約を不可逆に変える可能性がある。
- 復元時に現在fileを直接上書きする: 復元失敗時の最後の原本を失う。
- cloudへ自動backupする: 完全local、個人情報を外部送信しない仕様に反する。
