"""Phase 3 可用性取込の統合テスト。"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from summer_scheduler.application.availability_import_service import (
    AvailabilityImportError,
    AvailabilityImportService,
)
from summer_scheduler.application.master_data_service import MasterDataService
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    AuditLog,
    ImportBatch,
    ImportSourceSnapshot,
    LessonRequest,
    StudentAvailability,
    TeacherAvailability,
)
from summer_scheduler.infrastructure.repositories.master_repository import (
    MasterRepository,
)

_DAY = date(2026, 8, 1)
_STUDENT_HEADERS = (
    "生徒ID",
    "生徒名",
    "科目コード",
    "日付",
    "Y",
    "Z",
    "A",
    "B",
    "C",
    "第1希望講師ID",
    "第2希望講師ID",
    "第3希望講師ID",
    "備考",
)
_TEACHER_HEADERS = (
    "講師ID",
    "講師名",
    "日付",
    "Y",
    "Z",
    "A",
    "B",
    "C",
    "備考",
)


@pytest.fixture
def import_service(tmp_path: Path) -> Iterator[AvailabilityImportService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    projects = ProjectService(registry, tmp_path / "backups")
    projects.create_project(
        tmp_path / "summer.jukuschedule",
        title="夏期講習",
        campus_name="テスト校",
        start_date=_DAY,
        end_date=date(2026, 8, 3),
    )
    master = MasterDataService(projects)
    student_id = master.save_student(
        record_id=None,
        external_id="S001",
        name="生徒 太郎",
        grade="中1",
        default_max_consecutive_slots=2,
        allow_gap=False,
        note="",
        active=True,
    ).record_id
    teacher_id = master.save_teacher(
        record_id=None,
        external_id="T001",
        name="講師 花子",
        allow_gap=False,
        note="",
        active=True,
    ).record_id
    inactive_teacher_id = master.save_teacher(
        record_id=None,
        external_id="T002",
        name="講師 休職中",
        allow_gap=False,
        note="",
        active=False,
    ).record_id
    unqualified_teacher_id = master.save_teacher(
        record_id=None,
        external_id="T003",
        name="講師 未資格",
        allow_gap=False,
        note="",
        active=True,
    ).record_id
    subject = next(item for item in master.list_subjects() if item.code == "JH_MATH")
    master.set_qualification(teacher_id, subject.id, can_teach=True)
    master.save_lesson_request(
        record_id=None,
        student_id=student_id,
        subject_id=subject.id,
        required_sessions=2,
        regular_teacher_id=teacher_id,
        regular_teacher_priority=3,
        preferred_teacher_1_id=None,
        preferred_teacher_2_id=None,
        preferred_teacher_3_id=None,
        one_to_one_required=False,
        max_consecutive_slots_override=None,
        allow_gap_override=None,
        note="",
    )
    # inactive teacher は参照整合性テスト用。fixture 内で未使用警告を防ぐ。
    assert inactive_teacher_id > 0 and unqualified_teacher_id > 0
    yield AvailabilityImportService(projects)
    projects.close_project()
    registry.dispose()


def test_student_import_updates_cells_and_preferences(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "生徒可用性.csv"
    _write_csv(
        source,
        _STUDENT_HEADERS,
        [("S001", "生徒 太郎", "JH_MATH", _DAY.isoformat(), 2, 1, 0, 1, 2, "T001", "", "", "確認")],
    )

    preview = import_service.prepare_import("student", source)
    assert not preview.has_errors
    assert {row.operation for row in preview.diffs} == {"add"}

    result = import_service.apply_import(preview)
    assert (result.added, result.changed, result.deleted) == (5, 0, 0)

    projects = import_service._projects
    database = projects.require_database()
    with database.session_factory() as session:
        levels = list(session.scalars(select(StudentAvailability.availability_level)))
        request = session.scalar(select(LessonRequest))
        batch = session.scalar(select(ImportBatch))
        snapshot = session.scalar(select(ImportSourceSnapshot))
    assert sorted(levels) == [0, 1, 1, 2, 2]
    assert request is not None and request.preferred_teacher_1_id_optional is not None
    assert batch is not None and batch.source_file_name == source.name
    assert snapshot is not None
    assert snapshot.source_file_name == source.name
    assert snapshot.content == source.read_bytes()
    assert snapshot.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_manual_student_availability_editor_updates_multiple_students_and_slots(
    import_service: AvailabilityImportService,
) -> None:
    master = MasterDataService(import_service._projects)
    second_student_id = master.save_student(
        record_id=None,
        external_id="S002",
        name="生徒 次郎",
        grade="中1",
        default_max_consecutive_slots=2,
        allow_gap=False,
        note="",
        active=True,
    ).record_id
    options = import_service.student_editor_options()
    first_student_id = next(
        cast(int, row["id"]) for row in options["students"] if row["externalId"] == "S001"
    )
    assert {row["value"] for row in options["grades"]} == {"中1"}
    assert options["dates"][0]["isOpen"] is True
    first_slot_id = cast(int, options["slots"][0]["id"])

    changed = import_service.update_student_availability(
        [first_student_id, second_student_id],
        _DAY,
        {first_slot_id: 0},
    )
    assert changed == 2
    summary = import_service.summarize_student_availability(
        [first_student_id, second_student_id],
        _DAY,
    )
    assert summary[0]["currentLabel"] == "全員参加不可"
    assert summary[0]["unavailableCount"] == 2

    assert (
        import_service.update_student_availability(
            [first_student_id],
            _DAY,
            {first_slot_id: 1},
        )
        == 1
    )
    mixed = import_service.summarize_student_availability(
        [first_student_id, second_student_id],
        _DAY,
    )
    assert mixed[0]["currentLabel"] == "参加可・不可が混在"

    with import_service._projects.require_database().session_factory() as session:
        audit = list(session.scalars(select(AuditLog).order_by(AuditLog.id.desc())))[0]
    payload = json.loads(audit.after_json or "{}")
    assert audit.action == "student_availability_manually_updated"
    assert payload["student_count"] == 1
    assert payload["slot_levels"] == {str(options["slots"][0]["code"]): 1}
    assert "生徒 太郎" not in (audit.after_json or "")
    assert "S001" not in (audit.after_json or "")


def test_manual_student_availability_editor_rejects_closed_date(
    import_service: AvailabilityImportService,
) -> None:
    master = MasterDataService(import_service._projects)
    closed_day = date(2026, 8, 2)
    master.set_open_date(closed_day, is_open=False, note="休校")
    options = import_service.student_editor_options()
    student_id = cast(int, options["students"][0]["id"])
    slot_id = cast(int, options["slots"][0]["id"])

    summary = import_service.summarize_student_availability([student_id], closed_day)
    assert summary[0]["currentLabel"] == "休校日のため編集不可"
    with pytest.raises(AvailabilityImportError, match="休校日"):
        import_service.update_student_availability(
            [student_id],
            closed_day,
            {slot_id: 1},
        )


def test_new_import_replaces_embedded_source_snapshot(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    row = ("S001", "生徒 太郎", "JH_MATH", _DAY.isoformat(), 1, 1, 1, 1, 1, "", "", "", "")
    _write_csv(first, _STUDENT_HEADERS, [row])
    import_service.apply_import(import_service.prepare_import("student", first))

    changed_row = ("S001", "生徒 太郎", "JH_MATH", _DAY.isoformat(), 2, 1, 1, 1, 1, "", "", "", "")
    _write_csv(second, _STUDENT_HEADERS, [changed_row])
    import_service.apply_import(import_service.prepare_import("student", second))

    database = import_service._projects.require_database()
    with database.session_factory() as session:
        snapshots = list(session.scalars(select(ImportSourceSnapshot)))
    assert len(snapshots) == 1
    assert snapshots[0].source_file_name == "second.csv"
    assert snapshots[0].content == second.read_bytes()


def test_successful_import_persists_mapping_and_minimal_non_sensitive_audit(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "availability-safe.csv"
    student_name = "生徒 太郎"
    private_note = "保護者確認済みの個人メモ"
    _write_csv(
        source,
        _STUDENT_HEADERS,
        [
            (
                "S001",
                student_name,
                "JH_MATH",
                _DAY.isoformat(),
                2,
                1,
                0,
                1,
                2,
                "T001",
                "",
                "",
                private_note,
            )
        ],
    )

    preview = import_service.prepare_import("student", source)
    result = import_service.apply_import(preview)

    with import_service._projects.require_database().session_factory() as session:
        batch = session.scalar(select(ImportBatch))
        audit = session.scalar(select(AuditLog))
    assert batch is not None
    assert audit is not None

    mapping_payload = json.loads(batch.mapping_json)
    assert mapping_payload == {
        "mapping": preview.mapping,
        "sheet_name": preview.sheet_name,
        "encoding": preview.encoding,
    }
    audit_payload = json.loads(audit.after_json or "{}")
    assert audit.before_json is None
    assert audit.action == "availability_imported"
    assert audit_payload == {
        "added": result.added,
        "changed": result.changed,
        "unchanged": result.unchanged,
        "deleted": result.deleted,
        "source_file_name": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }

    persisted_payloads = (batch.mapping_json, audit.after_json or "")
    for sensitive_value in (
        "S001",
        student_name,
        private_note,
        str(source.resolve()),
        str(source.parent.resolve()),
    ):
        assert all(sensitive_value not in payload for payload in persisted_payloads)


def test_latest_successful_import_manual_mapping_is_reused(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    headers = (
        "識別列",
        "氏名列",
        "科目列",
        "日付列",
        "枠Y",
        "枠Z",
        "枠A",
        "枠B",
        "枠C",
        "連絡欄",
    )
    manual_mapping = {
        "student_id": "識別列",
        "student_name": "氏名列",
        "subject_code": "科目列",
        "date": "日付列",
        "slot:Y": "枠Y",
        "slot:Z": "枠Z",
        "slot:A": "枠A",
        "slot:B": "枠B",
        "slot:C": "枠C",
        "note": "連絡欄",
    }
    source = tmp_path / "manual-columns.csv"
    _write_csv(
        source,
        headers,
        [
            (
                "S001",
                "生徒 太郎",
                "JH_MATH",
                _DAY.isoformat(),
                1,
                1,
                1,
                1,
                1,
                "初回",
            )
        ],
    )
    first_preview = import_service.prepare_import(
        "student",
        source,
        mapping=manual_mapping,
    )
    assert first_preview.mapping == manual_mapping
    import_service.apply_import(first_preview)

    _write_csv(
        source,
        headers,
        [
            (
                "S001",
                "生徒 太郎",
                "JH_MATH",
                _DAY.isoformat(),
                2,
                2,
                2,
                2,
                2,
                "再取込み",
            )
        ],
    )
    inspection = import_service.inspect_source("student", source)
    assert inspection.suggested_mapping == manual_mapping

    reused_preview = import_service.prepare_import("student", source)
    assert reused_preview.mapping == manual_mapping
    assert not reused_preview.has_errors
    result = import_service.apply_import(reused_preview)
    assert (result.added, result.changed, result.unchanged) == (0, 5, 0)


def test_delete_candidates_require_explicit_confirmation(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "availability.csv"
    _write_csv(
        source,
        _STUDENT_HEADERS,
        [("S001", "生徒 太郎", "JH_MATH", _DAY.isoformat(), 1, 1, 1, 1, 1, "", "", "", "")],
    )
    import_service.apply_import(import_service.prepare_import("student", source))
    _write_csv(source, _STUDENT_HEADERS, [])

    preview = import_service.prepare_import("student", source)
    assert len(preview.diffs) == 5
    assert {row.operation for row in preview.diffs} == {"delete_candidate"}
    assert import_service.apply_import(preview).deleted == 0
    assert import_service.apply_import(preview, include_deletes=True).deleted == 5


def test_unmapped_preference_columns_preserve_existing_lesson_request(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    database = import_service._projects.require_database()
    with database.session_factory.begin() as session:
        request = session.scalar(select(LessonRequest))
        assert request is not None
        assert request.regular_teacher_id_optional is not None
        request.preferred_teacher_1_id_optional = request.regular_teacher_id_optional
        expected_teacher_id = request.regular_teacher_id_optional

    headers_without_preferences = (
        "生徒ID",
        "生徒名",
        "科目コード",
        "日付",
        "Y",
        "Z",
        "A",
        "B",
        "C",
        "備考",
    )
    source = tmp_path / "希望講師列なし.csv"
    _write_csv(
        source,
        headers_without_preferences,
        [
            (
                "S001",
                "生徒 太郎",
                "JH_MATH",
                _DAY.isoformat(),
                1,
                1,
                1,
                1,
                1,
                "既存希望を保持",
            )
        ],
    )

    preview = import_service.prepare_import("student", source)
    assert not preview.has_errors
    assert preview.rows[0].preferred_teacher_fields_supplied == (
        False,
        False,
        False,
    )
    import_service.apply_import(preview)

    with database.session_factory() as session:
        persisted = session.scalar(select(LessonRequest))
        assert persisted is not None
        assert persisted.preferred_teacher_1_id_optional == expected_teacher_id


def test_invalid_identity_qualification_and_protected_columns_are_rejected(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "invalid.csv"
    headers = (*_STUDENT_HEADERS, "通常担当講師ID")
    _write_csv(
        source,
        headers,
        [
            (
                "S001",
                "別人",
                "JH_MATH",
                _DAY.isoformat(),
                1,
                1,
                1,
                1,
                1,
                "T003",
                "",
                "",
                "",
                "T002",
            ),
            ("UNKNOWN", "不明", "JH_MATH", _DAY.isoformat(), 1, 1, 1, 1, 1, "", "", "", "", ""),
        ],
    )

    preview = import_service.prepare_import("student", source)
    codes = {issue.code for issue in preview.issues}
    assert {
        "name_mismatch",
        "unknown_id",
        "unqualified_preferred_teacher",
        "protected_field",
    } <= codes
    with pytest.raises(AvailabilityImportError):
        import_service.apply_import(preview)


def test_teacher_unknown_id_and_name_mismatch_are_rejected_without_writes(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "講師ID照合.csv"
    _write_csv(
        source,
        _TEACHER_HEADERS,
        [
            ("UNKNOWN", "未登録 講師", _DAY.isoformat(), 1, 1, 1, 1, 1, ""),
            ("T001", "別の 氏名", _DAY.isoformat(), 1, 1, 1, 1, 1, ""),
        ],
    )

    preview = import_service.prepare_import("teacher", source)
    assert {issue.code for issue in preview.issues} >= {"unknown_id", "name_mismatch"}
    with pytest.raises(AvailabilityImportError):
        import_service.apply_import(preview)

    with import_service._projects.require_database().session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TeacherAvailability)) == 0
        assert session.scalar(select(func.count()).select_from(ImportBatch)) == 0


def test_reimport_reports_changed_and_unchanged_cells_and_persists_only_changes(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "差分確認.csv"
    _write_csv(
        source,
        _STUDENT_HEADERS,
        [("S001", "生徒 太郎", "JH_MATH", _DAY.isoformat(), 1, 1, 1, 1, 1, "", "", "", "")],
    )
    import_service.apply_import(import_service.prepare_import("student", source))
    _write_csv(
        source,
        _STUDENT_HEADERS,
        [("S001", "生徒 太郎", "JH_MATH", _DAY.isoformat(), 2, 1, 1, 1, 1, "", "", "", "")],
    )

    preview = import_service.prepare_import("student", source)
    assert [row.operation for row in preview.diffs].count("change") == 1
    assert [row.operation for row in preview.diffs].count("unchanged") == 4
    result = import_service.apply_import(preview)

    assert (result.added, result.changed, result.unchanged, result.deleted) == (0, 1, 4, 0)
    with import_service._projects.require_database().session_factory() as session:
        levels = list(session.scalars(select(StudentAvailability.availability_level)))
    assert sorted(levels) == [1, 1, 1, 1, 2]


def test_teacher_cp932_and_xlsx_sources_can_be_imported(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    csv_source = tmp_path / "講師可用性_cp932.csv"
    _write_csv(
        csv_source,
        _TEACHER_HEADERS,
        [("T001", "講師 花子", _DAY.isoformat(), 0, 1, 2, 1, 0, "CP932")],
        encoding="cp932",
    )
    inspection = import_service.inspect_source("teacher", csv_source)
    assert inspection.encoding == "cp932"
    assert inspection.headers == _TEACHER_HEADERS
    assert inspection.mapping_fields[0][0] == "teacher_id"
    assert not import_service.prepare_import("teacher", csv_source).has_errors

    workbook_source = tmp_path / "講師可用性.xlsx"
    workbook = Workbook()
    worksheet = workbook.create_sheet("入力")
    worksheet.append(_TEACHER_HEADERS)
    worksheet.append(("T001", "講師 花子", _DAY, 2, 2, 2, 2, 2, "xlsx"))
    workbook.save(workbook_source)
    workbook.close()
    result = import_service.apply_import(
        import_service.prepare_import("teacher", workbook_source, sheet_name="入力")
    )
    assert result.added == 5
    with import_service._projects.require_database().session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TeacherAvailability)) == 5


def test_apply_rolls_back_when_import_batch_fails(
    import_service: AvailabilityImportService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "rollback.csv"
    _write_csv(
        source,
        _STUDENT_HEADERS,
        [
            (
                "S001",
                "生徒 太郎",
                "JH_MATH",
                _DAY.isoformat(),
                1,
                1,
                1,
                1,
                1,
                "T001",
                "",
                "",
                "",
            )
        ],
    )
    preview = import_service.prepare_import("student", source)

    def fail_batch(self: MasterRepository, import_batch: ImportBatch) -> ImportBatch:
        raise RuntimeError("batch failed")

    monkeypatch.setattr(MasterRepository, "create_import_batch", fail_batch)
    with pytest.raises(RuntimeError, match="batch failed"):
        import_service.apply_import(preview)
    with import_service._projects.require_database().session_factory() as session:
        assert session.scalar(select(func.count()).select_from(StudentAvailability)) == 0
        request = session.scalar(select(LessonRequest))
        assert request is not None
        assert request.preferred_teacher_1_id_optional is None


def test_apply_rejects_source_file_changed_after_preview(
    import_service: AvailabilityImportService,
    tmp_path: Path,
) -> None:
    source = tmp_path / "プレビュー後変更.csv"
    _write_csv(
        source,
        _STUDENT_HEADERS,
        [("S001", "生徒 太郎", "JH_MATH", _DAY.isoformat(), 1, 1, 1, 1, 1, "", "", "", "")],
    )
    preview = import_service.prepare_import("student", source)
    _write_csv(
        source,
        _STUDENT_HEADERS,
        [("S001", "生徒 太郎", "JH_MATH", _DAY.isoformat(), 2, 2, 2, 2, 2, "", "", "", "")],
    )

    with pytest.raises(AvailabilityImportError, match="変更"):
        import_service.apply_import(preview)

    with import_service._projects.require_database().session_factory() as session:
        assert session.scalar(select(func.count()).select_from(StudentAvailability)) == 0
        assert session.scalar(select(func.count()).select_from(ImportBatch)) == 0


def _write_csv(
    path: Path,
    headers: tuple[str, ...],
    rows: list[tuple[object, ...]],
    *,
    encoding: str = "utf-8",
) -> None:
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)
