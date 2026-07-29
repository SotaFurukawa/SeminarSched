"""設定読込みの単体テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from summer_scheduler.reporting.settings import OutputSettings
from summer_scheduler.shared.settings import SettingsError, load_settings


def test_environment_paths_override_packaged_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_directory = tmp_path / "日本語データ"
    log_directory = tmp_path / "日本語ログ"
    monkeypatch.setenv("SUMMER_SCHEDULER_DATA_DIR", str(data_directory))
    monkeypatch.setenv("SUMMER_SCHEDULER_LOG_DIR", str(log_directory))

    settings = load_settings()

    assert settings.application_name == "夏期講習 時間割作成"
    assert settings.data_directory == data_directory.resolve()
    assert settings.database_path == (data_directory / "summer_scheduler.db").resolve()
    assert settings.logging.directory == log_directory.resolve()
    assert settings.backup.automatic_generations == 5
    assert settings.backup.automatic_interval_minutes == 5
    assert settings.optimization.default_preset == "standard"
    assert settings.optimization.time_limit_for("fast") == 30.0
    assert settings.optimization.regular_teacher_priority_weights == (1, 3, 6, 10)
    assert settings.output.for_project(1) == OutputSettings(project_id=1)


def test_user_yaml_is_merged_and_relative_paths_use_config_directory(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "設定.yaml"
    config_path.write_text(
        """
application:
  name: "テスト用 時間割"
storage:
  data_directory: "相対データ"
  database_filename: "テスト.db"
logging:
  level: "DEBUG"
  backup_count: 2
backup:
  automatic_generations: 7
  automatic_interval_minutes: 12
optimization:
  default_preset: "fast"
  fast_time_limit_seconds: 1.5
  random_seed: 42
output:
  paper_size: "A4"
  orientation: "portrait"
  days_per_page: 3
  teacher_columns_per_page: 6
  font_size: 9.5
  margin_mm: 10
  csv_with_bom: false
  visible_fields: ["subject", "grade", "warning"]
  file_name_pattern: "{project}_{report}_{date}"
  default_output_directory: "帳票出力"
  student_page_mode: "combined"
  style_rules:
    warning:
      marker: "[要確認]"
      fill_color: "#AABBCC"
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.application_name == "テスト用 時間割"
    assert settings.organization_name == "SummerScheduler"
    assert settings.data_directory == (tmp_path / "相対データ").resolve()
    assert settings.database_path == (tmp_path / "相対データ" / "テスト.db").resolve()
    assert settings.logging.level == "DEBUG"
    assert settings.logging.backup_count == 2
    assert settings.backup.automatic_generations == 7
    assert settings.backup.automatic_interval_minutes == 12
    assert settings.optimization.default_preset == "fast"
    assert settings.optimization.fast_time_limit_seconds == 1.5
    assert settings.optimization.random_seed == 42
    assert settings.output.paper_size == "A4"
    assert settings.output.orientation == "portrait"
    assert settings.output.days_per_page == 3
    assert settings.output.teacher_columns_per_page == 6
    assert settings.output.font_size == 9.5
    assert settings.output.margin_mm == 10.0
    assert settings.output.csv_with_bom is False
    assert settings.output.visible_fields == ("subject", "grade", "warning")
    assert settings.output.file_name_pattern == "{project}_{report}_{date}"
    assert settings.output.default_output_directory_optional == str(
        (tmp_path / "帳票出力").resolve()
    )
    assert settings.output.student_page_mode == "combined"
    warning_style = next(rule for rule in settings.output.style_rules if rule.code == "warning")
    assert warning_style.marker == "[要確認]"
    assert warning_style.fill_color == "#AABBCC"
    assert warning_style.text_color == "#18212F"


def test_missing_explicit_config_is_an_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "存在しない.yaml"

    with pytest.raises(SettingsError, match="見つかりません"):
        load_settings(missing_path)


@pytest.mark.parametrize(
    "invalid_yaml",
    [
        "application: []",
        "logging:\n  level: VERBOSE",
        "storage:\n  database_filename: ../outside.db",
        "backup:\n  automatic_generations: 0",
        "backup:\n  automatic_interval_minutes: -1",
        "optimization:\n  default_preset: unlimited",
        "optimization:\n  fast_time_limit_seconds: .inf",
        "optimization:\n  regular_teacher_priority_weights: [1, 2, -1, 4]",
        "output:\n  paper_size: LETTER",
        "output:\n  days_per_page: 0",
        'output:\n  csv_with_bom: "false"',
        "output:\n  visible_fields: [unknown]",
        'output:\n  file_name_pattern: "../{report}"',
        'output:\n  style_rules:\n    warning:\n      fill_color: "red"',
    ],
)
def test_invalid_settings_are_rejected(tmp_path: Path, invalid_yaml: str) -> None:
    config_path = tmp_path / "不正.yaml"
    config_path.write_text(invalid_yaml, encoding="utf-8")

    with pytest.raises(SettingsError):
        load_settings(config_path)


def test_unknown_optimization_preset_is_rejected() -> None:
    settings = load_settings()

    with pytest.raises(SettingsError, match="preset"):
        settings.optimization.time_limit_for("unknown")
