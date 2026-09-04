"""SQLiteとAlembicの統合テスト。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from pytest import MonkeyPatch
from sqlalchemy import inspect, text

import summer_scheduler.infrastructure.db.migration_runner as migration_runner
from summer_scheduler.infrastructure.db import (
    Database,
    create_database,
    get_current_revision,
    get_head_revision,
    upgrade_database,
)

_PHASE5_REVISION = "20260729_0005"
_PHASE6_REVISION = "20260729_0006"
_IMPORT_SNAPSHOT_REVISION = "20260807_0007"
_REGULAR_LESSON_REVISION = "20260818_0008"
_HEAD_REVISION = "20260904_0010"


def test_first_migration_creates_unicode_path_database(tmp_path: Path) -> None:
    database_path = tmp_path / "日本語データ" / "時間割.db"
    database = create_database(database_path)

    try:
        upgrade_database(database.engine)
        database.verify_connection()

        tables = set(inspect(database.engine).get_table_names())
        assert database_path.is_file()
        assert tables == {
            "alembic_version",
            "application_metadata",
            "assignments",
            "audit_logs",
            "campuses",
            "course_projects",
            "group_lesson_students",
            "group_lessons",
            "import_batches",
            "import_source_snapshots",
            "lesson_requests",
            "open_dates",
            "optimization_runs",
            "output_settings",
            "regular_lesson_profiles",
            "student_availabilities",
            "students",
            "subjects",
            "teacher_availabilities",
            "teacher_qualifications",
            "teachers",
            "time_slots",
            "validation_issues",
        }

        with database.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            foreign_keys_enabled = connection.execute(text("PRAGMA foreign_keys")).scalar_one()

        assert revision == get_head_revision() == _HEAD_REVISION
        assert foreign_keys_enabled == 1
    finally:
        database.dispose()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    database = create_database(tmp_path / "repeat.db")

    try:
        upgrade_database(database.engine)
        upgrade_database(database.engine)
        assert "application_metadata" in inspect(database.engine).get_table_names()
    finally:
        database.dispose()


def test_migration_runtime_does_not_write_bytecode_cache(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    source = Path(migration_runner.__file__).resolve().parent / "alembic"
    copied = tmp_path / "frozen-alembic"
    shutil.copytree(
        source,
        copied,
        ignore=shutil.ignore_patterns("__pycache__", "*.py[co]"),
    )
    monkeypatch.setattr(migration_runner, "_migration_directory", lambda: copied)
    database = create_database(tmp_path / "no-cache.db")
    previous = sys.dont_write_bytecode

    try:
        upgrade_database(database.engine)
        assert get_head_revision() == _HEAD_REVISION
        assert sys.dont_write_bytecode is previous
        assert not list(copied.rglob("__pycache__"))
        assert not list(copied.rglob("*.py[co]"))
    finally:
        database.dispose()


def test_phase6_migration_round_trip_preserves_assignment_and_audit_log(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "日本語データ" / "保持確認.jukuschedule")

    try:
        _migrate_to(database, _PHASE5_REVISION)
        _seed_phase5_business_rows(database)
        expected = _phase5_business_rows(database)

        _migrate_to(database, _PHASE6_REVISION)
        assert get_current_revision(database.engine) == _PHASE6_REVISION
        assert "output_settings" in inspect(database.engine).get_table_names()
        assert _phase5_business_rows(database) == expected

        _migrate_to(database, _PHASE5_REVISION, downgrade=True)
        assert get_current_revision(database.engine) == _PHASE5_REVISION
        assert "output_settings" not in inspect(database.engine).get_table_names()
        assert _phase5_business_rows(database) == expected

        _migrate_to(database, _PHASE6_REVISION)
        assert get_current_revision(database.engine) == _PHASE6_REVISION
        assert "output_settings" in inspect(database.engine).get_table_names()
        assert _phase5_business_rows(database) == expected
    finally:
        database.dispose()


def test_regular_lesson_profile_migration_round_trip_preserves_existing_data(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "通常授業_migration.jukuschedule")
    try:
        _migrate_to(database, _IMPORT_SNAPSHOT_REVISION)
        _seed_phase5_business_rows(database)
        expected = _phase5_business_rows(database)

        _migrate_to(database, _REGULAR_LESSON_REVISION)
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO regular_lesson_profiles
                        (project_id, student_id, subject_id,
                         regular_teacher_id_optional, regular_teacher_priority,
                         one_to_one_required)
                    VALUES (1, 40, 30, 20, 4, 0)
                    """
                )
            )
        assert _phase5_business_rows(database) == expected

        _migrate_to(database, _IMPORT_SNAPSHOT_REVISION, downgrade=True)
        assert "regular_lesson_profiles" not in inspect(database.engine).get_table_names()
        assert _phase5_business_rows(database) == expected

        _migrate_to(database, _REGULAR_LESSON_REVISION)
        assert "regular_lesson_profiles" in inspect(database.engine).get_table_names()
        assert _phase5_business_rows(database) == expected
    finally:
        database.dispose()


def test_subject_split_migration_preserves_ids_and_does_not_infer_qualifications(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "科目分割_migration.jukuschedule")
    try:
        _migrate_to(database, _REGULAR_LESSON_REVISION)
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO teachers (id, external_id, name)
                    VALUES (20, 'T-0001', '架空 講師')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO subjects
                        (id, code, display_name, school_level, sort_order, active)
                    VALUES
                        (31, 'ES_MATH', '小学校・算数', 'elementary', 2, 1),
                        (32, 'ES_JPN', '小学校・国語', 'elementary', 3, 1),
                        (33, 'HS_MATH_GENERAL', '高校・数学一般', 'high_school', 14, 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO teacher_qualifications
                        (teacher_id, subject_id, can_teach)
                    VALUES (20, 31, 1)
                    """
                )
            )

        _migrate_to(database, _HEAD_REVISION)
        with database.engine.connect() as connection:
            subjects = {
                row.code: (row.id, row.display_name, row.active)
                for row in connection.execute(
                    text(
                        """
                        SELECT id, code, display_name, active
                        FROM subjects
                        ORDER BY sort_order
                        """
                    )
                )
            }
            qualification_codes = (
                connection.execute(
                    text(
                        """
                    SELECT subjects.code
                    FROM teacher_qualifications
                    JOIN subjects ON subjects.id = teacher_qualifications.subject_id
                    WHERE teacher_qualifications.teacher_id = 20
                      AND teacher_qualifications.can_teach = 1
                    """
                    )
                )
                .scalars()
                .all()
            )

        assert subjects["ES_MATH"] == (
            31,
            "小学校・算数（中学受験以外なら可能）",
            1,
        )
        assert subjects["ES_JPN"] == (
            32,
            "小学校・国語（中学受験以外なら可能）",
            1,
        )
        assert subjects["HS_MATH_GENERAL"] == (33, "高校・数学IA", 1)
        assert subjects["ES_MATH_ENTRANCE"][1:] == ("小学校・算数（中学受験）", 1)
        assert subjects["ES_JPN_ENTRANCE"][1:] == ("小学校・国語（中学受験）", 1)
        assert subjects["HS_MATH_IIBC"][1:] == ("高校・数学IIBC", 1)
        assert qualification_codes == ["ES_MATH"]

        _migrate_to(database, _REGULAR_LESSON_REVISION, downgrade=True)
        with database.engine.connect() as connection:
            legacy_subjects = {
                row.code: (row.id, row.display_name)
                for row in connection.execute(text("SELECT id, code, display_name FROM subjects"))
            }
        assert legacy_subjects == {
            "ES_MATH": (31, "小学校・算数"),
            "ES_JPN": (32, "小学校・国語"),
            "HS_MATH_GENERAL": (33, "高校・数学一般"),
        }

        _migrate_to(database, _HEAD_REVISION)
        assert get_current_revision(database.engine) == _HEAD_REVISION
    finally:
        database.dispose()


def _migrate_to(
    database: Database,
    revision: str,
    *,
    downgrade: bool = False,
) -> None:
    config = Config()
    migration_directory = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "summer_scheduler"
        / "infrastructure"
        / "db"
        / "alembic"
    )
    config.set_main_option("script_location", str(migration_directory))
    with database.engine.begin() as connection:
        config.attributes["connection"] = connection
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)


def _seed_phase5_business_rows(database: Database) -> None:
    statements = (
        """
        INSERT INTO campuses (id, name)
        VALUES (1, '架空みらい校')
        """,
        """
        INSERT INTO course_projects
            (id, campus_id, title, start_date, end_date, status)
        VALUES
            (1, 1, 'Phase 6 migration保持確認', '2026-08-01', '2026-08-01', 'confirmed')
        """,
        """
        INSERT INTO time_slots
            (id, project_id, code, display_name, start_time, end_time, sort_order)
        VALUES
            (10, 1, 'Y', 'Yコマ', '09:00:00', '10:20:00', 1)
        """,
        """
        INSERT INTO teachers (id, external_id, name)
        VALUES (20, '00042', '架空 講師')
        """,
        """
        INSERT INTO subjects
            (id, code, display_name, school_level, sort_order)
        VALUES
            (30, 'JH_MATH_TEST', '中学校・架空数学', '中学校', 1)
        """,
        """
        INSERT INTO students (id, external_id, name, grade)
        VALUES (40, '00123', '架空 生徒', '中学1年')
        """,
        """
        INSERT INTO lesson_requests
            (
                id,
                project_id,
                student_id,
                subject_id,
                required_sessions,
                regular_teacher_id_optional,
                regular_teacher_priority
            )
        VALUES
            (50, 1, 40, 30, 1, 20, 5)
        """,
        """
        INSERT INTO assignments
            (
                id,
                project_id,
                lesson_request_id,
                session_index,
                date,
                time_slot_id,
                teacher_id,
                is_locked,
                is_manual,
                created_by,
                note
            )
        VALUES
            (
                60,
                1,
                50,
                1,
                '2026-08-01',
                10,
                20,
                1,
                1,
                'manual',
                '保持対象の割当'
            )
        """,
    )
    with database.engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                """
                INSERT INTO audit_logs
                    (
                        id,
                        project_id,
                        action,
                        entity_type,
                        entity_id,
                        before_json,
                        after_json,
                        reason,
                        source,
                        operation_id_optional
                    )
                VALUES
                    (
                        70,
                        1,
                        'assignment_updated',
                        'AssignmentSession',
                        '50:1',
                        :before_json,
                        :after_json,
                        'Phase 6 migration保持確認',
                        'manual',
                        'phase6-migration-retention'
                    )
                """
            ),
            {
                "before_json": '{"teacher_id":19}',
                "after_json": '{"teacher_id":20}',
            },
        )


def _phase5_business_rows(
    database: Database,
) -> tuple[dict[str, object], dict[str, object]]:
    with database.engine.connect() as connection:
        assignment = (
            connection.execute(
                text(
                    """
                SELECT
                    id,
                    project_id,
                    lesson_request_id,
                    session_index,
                    date,
                    time_slot_id,
                    teacher_id,
                    is_locked,
                    is_manual,
                    created_by,
                    note
                FROM assignments
                WHERE id = 60
                """
                )
            )
            .mappings()
            .one()
        )
        audit_log = (
            connection.execute(
                text(
                    """
                SELECT
                    id,
                    project_id,
                    action,
                    entity_type,
                    entity_id,
                    before_json,
                    after_json,
                    reason,
                    source,
                    operation_id_optional
                FROM audit_logs
                WHERE id = 70
                """
                )
            )
            .mappings()
            .one()
        )
    return dict(assignment), dict(audit_log)
