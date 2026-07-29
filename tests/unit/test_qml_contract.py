"""Phase 1のQML表示要件を固定する小さな契約テスト。"""

from __future__ import annotations

from pathlib import Path


def test_main_qml_contains_all_required_navigation_labels() -> None:
    qml_path = Path(__file__).parents[2] / "src" / "summer_scheduler" / "ui" / "qml" / "Main.qml"
    source = qml_path.read_text(encoding="utf-8")

    required_labels = {
        "ホーム",
        "生徒",
        "講師",
        "集団授業",
        "アンケート取込み",
        "時間割",
        "未配置・警告",
        "出力",
        "設定",
    }
    assert all(f'title: "{label}"' in source for label in required_labels)
    assert "夏期講習時間割作成" in source
    assert "workspace.currentProjectTitle" in source
