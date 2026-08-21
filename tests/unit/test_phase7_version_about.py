"""Phase 7の版表示・About・帳票メタデータ契約。"""

from __future__ import annotations

import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

from summer_scheduler import __version__
from summer_scheduler.reporting.common import updated_text
from summer_scheduler.reporting.data import OutputSnapshot, ProjectRecord
from summer_scheduler.ui.viewmodels.app_view_model import AppViewModel

ROOT = Path(__file__).parents[2]


def test_release_candidate_version_is_consistent_in_package_and_metadata() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == "1.3.3"
    assert metadata["project"]["version"] == __version__


def test_app_view_model_distinguishes_application_and_database_versions() -> None:
    view_model = AppViewModel(__version__, "20260729_0006", database_ready=True)

    assert view_model._get_app_version() == "1.3.3"
    assert view_model._get_schema_version() == "20260729_0006"
    assert view_model._get_database_ready() is True


def test_main_qml_has_real_about_dialog_with_both_versions() -> None:
    source = (ROOT / "src/summer_scheduler/ui/qml/Main.qml").read_text(encoding="utf-8")

    assert "id: aboutDialog" in source
    assert "onClicked: aboutDialog.open()" in source
    assert "root.viewModel.appVersion" in source
    assert "root.viewModel.schemaVersion" in source
    assert "アプリの版とDBスキーマの版は別々" in source
    assert "テレメトリや外部送信は行いません" in source


def test_report_metadata_contains_application_version() -> None:
    snapshot = OutputSnapshot(
        project=ProjectRecord(
            id=1,
            title="架空講習",
            campus_name="架空校舎",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            status="confirmed",
            generated_at=datetime(2026, 7, 29, 12, tzinfo=UTC),
        ),
        dates=(),
        slots=(),
        students=(),
        teachers=(),
        subjects=(),
        lesson_requests=(),
        assignments=(),
        group_lessons=(),
        unassigned=(),
        warnings=(),
    )

    assert updated_text(snapshot).endswith("／アプリ v1.3.3")
