# ADR 0005: プロジェクトSQLiteとマスター取込みのライフサイクルを分離する

- 状態: 採用
- 日付: 2026-07-28
- 対象: Phase 2

## コンテキスト

Phase 2では、利用者が講習ごとのデータを通常の文書ファイルのように作成、移動、
別名保存、複製、バックアップできる必要がある。一方、アプリ自身は最近使用した
プロジェクト等の状態を、プロジェクトを開く前から保持する必要がある。

マスター仕様はプロジェクトをSQLite内包の単一ファイルまたはフォルダとしてよいと
しているが、Phase 0では次が未決だった。

- `.jukuschedule` の具体的な内部形式
- Student、Teacher、Subjectの所属範囲
- 外部IDと科目コードの一意性の範囲
- schema migration前のバックアップ
- 削除時に参照データを残すか削除するか
- Excelの複数シートを途中失敗なく反映するtransaction境界

実データには個人情報が含まれるため、アプリ状態と業務データを混ぜず、コピーや
取込みの失敗で元ファイルを破損させない必要がある。

## 決定

### 1. 1 `.jukuschedule` = 1 SQLite = 1 CourseProject

`.jukuschedule` はSQLiteデータベースそのものとし、1ファイルに
`CourseProject` をちょうど1件保持する。Phase 2では添付ファイルを内包する
コンテナ形式にしない。

ファイル内には、その講習を再現するためのCampus、TimeSlot、OpenDate、Student、
Teacher、Subject、TeacherQualification、LessonRequestを保存する。Student、
Teacher、Subjectには`project_id`を追加せず、ファイル境界を所属範囲とする。

この結果、次をファイル内で一意にする。

- Studentの`external_id`
- Teacherの`external_id`
- Subjectの`code`
- TimeSlotの`(project_id, code)`と`(project_id, sort_order)`
- OpenDateの`(project_id, date)`
- LessonRequestの`(project_id, student_id, subject_id)`
- TeacherQualificationの`(teacher_id, subject_id)`

過年度や別講習へデータを引き継ぐ場合は、プロジェクト複製または
`master_data.xlsx` の出力・取込みを利用する。複数プロジェクト間で同じ
Student ORM行を共有しないため、過去のプロジェクトは後日のマスター変更から
独立して再読込みできる。

### 2. アプリ管理DBとプロジェクトDBを分離する

`%LOCALAPPDATA%\SummerScheduler\data\summer_scheduler.db` はアプリ管理DBとし、
`application_metadata` と最近使用したプロジェクトの参照を保持する。生徒、講師、
受講希望等の業務データは保存しない。

利用者が選択した `.jukuschedule` だけを現在のプロジェクトDBとして開く。
SQLAlchemyのSessionはQMLへ公開せず、Project Service、Application Service、
Repositoryの境界内で扱う。

### 3. ファイル作成・コピーとmigrationを安全な経路へ集約する

- 新規作成は同じディレクトリの一時SQLiteへmigrationと初期データ登録を行い、
  成功後に`os.replace`で目的ファイルへ置き換える。
- 別名保存、複製、手動バックアップはSQLite backup APIで整合したsnapshotを
  一時ファイルへ作り、成功後に`os.replace`する。
- 別名保存はコピー後に新しいファイルへ切り替える。
- 複製とバックアップは、現在開いているファイルを切り替えない。
- 既存ファイルを開く前にSQLite形式、`course_projects`、
  `alembic_version`を検証する。
- DB revisionがアプリのheadと異なる場合は、migrationを適用する前にアプリの
  ローカルバックアップ領域へsnapshotを作る。バックアップに失敗した場合は
  migrationを開始しない。
- schema変更はAlembic revisionだけで行い、起動時の`create_all()`を既存DBの
  更新手段にしない。

`.jukuschedule` を同期中のOneDriveやネットワーク共有で直接編集することは推奨
しない。Windowsのファイルロック、空き容量不足、同期競合は利用者へ明示し、例外を
握り潰さない。

### 4. 削除と使用停止を区別する

参照整合性と利用者の意図を次のように扱う。

| 対象 | 方針 |
|---|---|
| CourseProject → TimeSlot / OpenDate / LessonRequest | CourseProject行の削除時は`CASCADE`。Phase 2 UIは行削除を提供せず、プロジェクトを閉じる操作とファイル管理を分ける |
| Campus → CourseProject | `RESTRICT`。使用中のプロジェクトから校舎を孤立させない |
| Student → LessonRequest | DBは`RESTRICT`。UIで明示削除を確認した場合だけ、同じtransactionで依存LessonRequestを先に削除 |
| Subject → LessonRequest | `RESTRICT`。Phase 2 UIは物理削除ではなく使用停止を基本とし、既存受講希望を保持 |
| Teacher → TeacherQualification | `CASCADE`。講師削除時に資格だけを孤立させない |
| Teacher → LessonRequestの通常担当・希望1〜3 | `SET NULL`。受講希望そのものを消さず、講師参照を解除 |
| TimeSlot | Phase 2 UIで確認後に削除可能。将来のAssignment導入時は参照方針を再検討 |

生徒・講師・科目の通常運用では`active = false`による使用停止を提供し、履歴や
既存参照を不用意に失わない。無効化済み講師を新しいLessonRequestへ選択することは
禁止する。

### 5. Excelは検証・プレビュー・一括transactionを分ける

`master_data.xlsx` は「生徒」「講師」「科目」「講師対応科目」「受講希望」の
5シートを1つの取込み単位とする。

処理は次の2段階に分ける。

1. 読取り専用のプレビューで、必須シート・列、セル型、重複、参照ID、資格、
   優先度等を検証し、正規化済み行、新規／更新件数、警告、エラーを返す。
2. 利用者が確認した同じプレビューを、1つのSQLAlchemy transactionで反映する。

エラーを含むプレビューは反映しない。反映中に1行でも例外が発生した場合は全シートを
rollbackし、一部だけ更新された状態を残さない。警告だけの場合は反映可能だが、
利用者が内容を確認する。`例示行 = はい`の行は説明専用として無視する。

Excel adapterはQMLとDB modelを直接結ばず、Application/ViewModelから呼び出す。
入力エラーはシート名、Excel上の行番号、列名を保持する。ログへ行全体や氏名を
安易に記録しない。

## 根拠

- 単一SQLiteはWindows上で移動・バックアップしやすく、Phase 2の添付物を必要と
  しない。
- プロジェクトごとのsnapshotは過年度データの再現性を保ち、アプリ管理DBの破損や
  削除が業務データへ波及する範囲を小さくする。
- SQLite backup APIは、接続中DBの単純なファイルコピーより整合したsnapshotを
  作りやすい。
- migration前バックアップと原子的な置換は、schema更新・保存途中の失敗から復旧
  できる可能性を高める。
- 使用停止、`RESTRICT`、`SET NULL`、`CASCADE`を関係ごとに選ぶことで、履歴保持と
  孤立データ防止を両立する。
- Excel全体を1transactionにすれば、5シート間の参照関係を一貫して反映できる。

## 影響

良い影響:

- `.jukuschedule` を別PCや別フォルダへ移動して再読込みできる。
- アプリ設定と実業務データのバックアップ方針を分けられる。
- 同じ外部IDを別プロジェクトで独立して使える。
- Excel取込みエラーをDB変更前に確認できる。
- Phase 3以降のavailability、集団授業、Phase 4以降のAssignmentも同じ
  プロジェクトDBへmigrationで追加できる。

注意点:

- 同じ人物を複数プロジェクトで編集しても自動同期されない。初期版の複数校舎共有・
  クラウド同期は対象外である。
- ファイル内1プロジェクトという不変条件を、open時とtestで継続して検証する必要が
  ある。
- `.jukuschedule` はSQLiteなので、利用者が汎用SQLiteツールで直接変更すると
  整合性を壊し得る。
- migration前バックアップにも個人情報が含まれる。Git、CI artifact、クラウドへ
  無断で置かない。
- ディスク障害、同期競合、OSクラッシュに対する完全な耐久性を保証するものではない。
  自動バックアップの世代管理と復元UIは後続フェーズで追加する。
- 将来Subjectを校舎共通マスターにする場合は、ファイル間の明示的なimport/export
  または別schemaを新しいADRで設計する。

## 採用しなかった案

- すべてのプロジェクトをアプリ管理DBへ保存する: 文書ファイルとしての移動、
  別名保存、過年度snapshot、障害範囲の分離が難しい。
- 1つの`.jukuschedule`へ複数CourseProjectを保存する: ファイル名と現在の講習の
  対応が曖昧になり、Phase 2の操作を不必要に複雑化する。
- SQLiteと添付物をZIPコンテナにする: Phase 2には添付物がなく、更新ごとの再梱包と
  crash recoveryの複雑さが先行する。
- 接続中のDBファイルを通常のファイルコピーで複製する: journalや書込み中状態を含む
  不整合snapshotになり得る。
- Excelを行ごとにcommitする: 後続シートで失敗した際に部分反映が残り、
  参照整合性を利用者が手作業で復旧する必要が生じる。
- エラー行だけを除外して残りを自動反映する: 利用者が確認した差分と実際の反映結果が
  変わり、誤更新を見落としやすい。

## 検証方針

- 新規作成、再読込み、日本語ファイル名、既定5コマ、23科目を結合テストする。
- 別名保存、複製、バックアップが有効なSQLite snapshotであることを確認する。
- 空DBおよび旧revisionからheadへのmigrationを確認する。
- 外部ID、科目コード、生徒×科目の一意制約と外部キー削除方針をテストする。
- 5シートの出力、正常取込み、行・列エラー、参照エラー、警告を検証する。
- 反映途中に例外を注入し、transaction全体がrollbackされることを確認する。
