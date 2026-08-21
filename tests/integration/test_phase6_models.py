"""Phase 6 OutputSetting ORMと0005→0006 migrationの結合テスト。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from summer_scheduler.infrastructure.db import (
    Database,
    create_database,
    get_head_revision,
    migration_runner,
    upgrade_database,
)
from summer_scheduler.infrastructure.db.models import (
    Campus,
    CourseProject,
    OutputSetting,
)


def _alembic_config(engine: Engine) -> Config:
    config = Config()
    migration_directory = Path(migration_runner.__file__).resolve().parent / "alembic"
    config.set_main_option("script_location", str(migration_directory))
    config.attributes["connection"] = engine.connect()
    return config


def _run_alembic(engine: Engine, revision: str, *, downgrade: bool = False) -> None:
    config = _alembic_config(engine)
    connection = config.attributes["connection"]
    try:
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)
    finally:
        connection.close()


def _assert_no_metadata_diff(engine: Engine) -> None:
    config = _alembic_config(engine)
    connection = config.attributes["connection"]
    try:
        command.check(config)
    finally:
        connection.close()


def _add_project(database_path: Path) -> tuple[Database, int]:
    database = create_database(database_path)
    _run_alembic(database.engine, "20260729_0005")
    with database.session_factory.begin() as session:
        campus = Campus(
            name="架空みなと校",
            logo_path_optional=r"C:\架空校\ロゴ.png",
        )
        session.add(campus)
        session.flush()
        project = CourseProject(
            campus_id=campus.id,
            title="Phase 6 migration確認",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            status="editing",
            file_version=1,
        )
        session.add(project)
        session.flush()
        project_id = project.id
    return database, project_id


def _setting(project_id: int, *, paper_size: str = "A3") -> OutputSetting:
    return OutputSetting(
        project_id=project_id,
        paper_size=paper_size,
        orientation="landscape",
        visible_fields_json='["grade","subject"]',
        days_per_page=2,
        teacher_columns_per_page=8,
        font_size=8.0,
        margin_mm=8.0,
        file_name_pattern="{project}_{report}",
        default_output_directory_optional=r"C:\架空出力",
        student_page_mode="one_per_page",
        csv_with_bom=True,
        style_rules_json=(
            '[{"code":"one_to_one","label":"1対1","marker":"[1対1]",'
            '"fill_color":"#FFFFFF","text_color":"#000000"}]'
        ),
    )


def test_upgrade_from_0005_adds_output_settings_without_changing_campus_logo(
    tmp_path: Path,
) -> None:
    database, project_id = _add_project(tmp_path / "日本語フォルダー" / "Phase6移行.jukuschedule")
    try:
        upgrade_database(database.engine)

        assert get_head_revision() == "20260822_0009"
        assert "output_settings" in inspect(database.engine).get_table_names()
        columns = {
            column["name"] for column in inspect(database.engine).get_columns("output_settings")
        }
        assert {
            "project_id",
            "paper_size",
            "orientation",
            "visible_fields_json",
            "days_per_page",
            "teacher_columns_per_page",
            "font_size",
            "margin_mm",
            "file_name_pattern",
            "default_output_directory_optional",
            "student_page_mode",
            "csv_with_bom",
            "style_rules_json",
            "created_at",
            "updated_at",
        } == columns
        assert "logo_path_optional" not in columns

        with database.session_factory.begin() as session:
            session.add(_setting(project_id))
        with database.session_factory() as session:
            campus = session.scalar(select(Campus))
            stored = session.get(OutputSetting, project_id)
            assert campus is not None
            assert campus.logo_path_optional == r"C:\架空校\ロゴ.png"
            assert stored is not None
            assert stored.default_output_directory_optional == r"C:\架空出力"

        with database.session_factory() as session:
            stored = session.get(OutputSetting, project_id)
            assert stored is not None
            stored.paper_size = "LETTER"
            with pytest.raises(IntegrityError):
                session.flush()

        _assert_no_metadata_diff(database.engine)
    finally:
        database.dispose()


def test_downgrade_drops_only_phase6_table_and_preserves_project(
    tmp_path: Path,
) -> None:
    database, project_id = _add_project(tmp_path / "Phase6_downgrade.jukuschedule")
    try:
        upgrade_database(database.engine)
        with database.session_factory.begin() as session:
            session.add(_setting(project_id))

        _run_alembic(database.engine, "20260729_0005", downgrade=True)

        assert "output_settings" not in inspect(database.engine).get_table_names()
        with database.engine.connect() as connection:
            assert connection.execute(
                text(
                    """
                    SELECT course_projects.title, campuses.name, campuses.logo_path_optional
                    FROM course_projects
                    JOIN campuses ON campuses.id = course_projects.campus_id
                    """
                )
            ).one() == (
                "Phase 6 migration確認",
                "架空みなと校",
                r"C:\架空校\ロゴ.png",
            )
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260729_0005"
            )
    finally:
        database.dispose()
