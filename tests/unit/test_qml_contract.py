"""Phase 1のQML表示要件を固定する小さな契約テスト。"""

from __future__ import annotations

from pathlib import Path


def test_main_qml_contains_all_required_navigation_labels() -> None:
    qml_path = Path(__file__).parents[2] / "src" / "summer_scheduler" / "ui" / "qml" / "Main.qml"
    source = qml_path.read_text(encoding="utf-8")

    required_labels = {
        "ホーム",
        "生徒の基本情報",
        "講師の基本情報",
        "アンケート取込み",
        "アンケート作成",
        "事前確定",
        "時間割",
        "未配置・警告",
        "出力",
        "設定",
    }
    assert all(f'title: "{label}"' in source for label in required_labels)
    assert "季節講習 時間割作成" in source
    assert "workspace.currentProjectTitle" in source
