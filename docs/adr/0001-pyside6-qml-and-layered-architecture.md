# ADR 0001: PySide6 / QML とレイヤー分離を採用する

- 状態: 採用
- 日付: 2026-07-28
- 対象: Phase 0 / Phase 1

## コンテキスト

最上位仕様は、Windows 10 / 11 x64 を優先する完全ローカルの日本語デスクトップアプリを要求している。将来は、高密度な時間割表、ドラッグ＆ドロップ、即時警告、印刷プレビューを扱う。一方で、QML に DB 操作や最適化処理を直接記述せず、画面を開かなくても業務規則と最適化をテストできる必要がある。

## 決定

デスクトップ UI に PySide6、UI 記述に QML / Qt Quick を採用する。

責務を次の層へ分離する。

```text
QML UI
  → ViewModel / Controller
  → Application Service
  → Domain Model / Validation
  → Repository port
  ← Infrastructure adapter / SQLite

Optimization、Excel、PDF は Application から呼ぶ独立 adapter とする。
```

QML は表示状態、選択状態、利用者イベントを担当する。Python オブジェクトは ViewModel として QML へ公開し、SQLAlchemy Session、ORM model、OR-Tools model は公開しない。

Phase 1 は `AppViewModel` だけを `appViewModel` context property として公開する。`Main.qml` が画面メタデータと選択状態を持ち、`Sidebar.qml` と `Loader` で仮画面を切り替える。Phase 2 以降、各画面を専用 QML と ViewModel に置き換える。

## 根拠

- マスター仕様の推奨技術と一致する。
- Qt Quick は将来の高密度グリッド、DPI、入力操作を段階的に実装できる。
- Python の業務処理を QML から分離すると pytest で GUI なしに検証できる。
- Qt のアプリケーション資源として QML を同梱でき、将来の Windows 配布へつなげられる。

## 影響

良い影響:

- UI と業務ロジックを独立して変更・テストできる。
- 将来の CLI、最適化 worker、Excel / PDF adapter から同じ Application Service を利用できる。
- サイドバーの placeholder を段階的に実画面へ置き換えられる。

注意点:

- QML / Python 間の signal、property、object lifetime を明示して管理する必要がある。
- 型境界を越す値は、単純な DTO または表示用 model へ変換する必要がある。
- QML resource を package data と配布物に必ず含める必要がある。
- GUI smoke test とは別に、業務規則を Python 側でテストする必要がある。

## 採用しなかった案

- Qt Widgets のみ: 表中心の画面には利用できるが、最上位仕様が QML / Qt Quick を原則としており、今回変更する理由がない。
- QML 内へ JavaScript の業務処理を実装: DB・最適化との分離、型検査、GUI なしテストを損なう。
- Electron / Web UI: Node.js 系の追加 runtime と配布サイズを増やし、推奨技術から外れる。
- 単一の Python スクリプト: 保守、テスト、将来拡張という要件を満たさない。

## 適用上の規則

- QML から SQL、ファイル取込み、最適化を直接実行しない。
- Domain は PySide6 と SQLAlchemy に依存しない。
- 長時間処理は UI thread で実行しない。
- ハード制約の正本を QML 側へ複製しない。
- 重要な境界変更は新しい ADR で記録する。
