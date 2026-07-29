"""最適化入出力DTOのversion付き安全なJSON snapshot codec。"""

from __future__ import annotations

from typing import cast

from summer_scheduler.optimization._serialization_helpers import (
    JsonObject,
    SnapshotDecodeError,
    decode_document,
    encode_document,
    exact_int_tuple,
    exact_optional_int_tuple,
    int_tuple,
    map_array,
    require_bool,
    require_date,
    require_fields,
    require_float,
    require_int,
    require_object,
    require_optional_bool,
    require_optional_int,
    require_str,
    require_time,
)
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    AvailabilityOwner,
    DiagnosticCode,
    DiagnosticReason,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    ObjectiveBreakdown,
    OptimizationInput,
    OptimizationResult,
    OptimizationSettings,
    ScheduledAssignment,
    SolverStatus,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
    UnassignedLesson,
)

_INPUT_SCHEMA = "summer_scheduler.optimization_input"
_RESULT_SCHEMA = "summer_scheduler.optimization_result"
_SCHEMA_VERSION = 1


def optimization_input_to_json(value: OptimizationInput) -> str:
    """個人情報を含み得る入力を、file IOなしでJSON文字列へ変換する。"""
    return encode_document(_INPUT_SCHEMA, _SCHEMA_VERSION, _input_to_object(value))


def optimization_input_from_json(payload: str) -> OptimizationInput:
    """固定schemaのJSONだけをOptimizationInputへ復元する。"""
    return _input_from_object(
        decode_document(payload, _INPUT_SCHEMA, _SCHEMA_VERSION),
        "$.data",
    )


def optimization_result_to_json(value: OptimizationResult) -> str:
    return encode_document(_RESULT_SCHEMA, _SCHEMA_VERSION, _result_to_object(value))


def optimization_result_from_json(payload: str) -> OptimizationResult:
    return _result_from_object(
        decode_document(payload, _RESULT_SCHEMA, _SCHEMA_VERSION),
        "$.data",
    )


def _input_to_object(value: OptimizationInput) -> JsonObject:
    return {
        "project_id": value.project_id,
        "open_dates": [item.isoformat() for item in value.open_dates],
        "time_slots": [_slot_to_object(item) for item in value.time_slots],
        "students": [_student_to_object(item) for item in value.students],
        "teachers": [_teacher_to_object(item) for item in value.teachers],
        "subjects": [_subject_to_object(item) for item in value.subjects],
        "lesson_requests": [_request_to_object(item) for item in value.lesson_requests],
        "availabilities": [_availability_to_object(item) for item in value.availabilities],
        "group_blocks": [_group_to_object(item) for item in value.group_blocks],
        "existing_assignments": [_existing_to_object(item) for item in value.existing_assignments],
        "settings": _settings_to_object(value.settings),
    }


def _input_from_object(value: JsonObject, path: str) -> OptimizationInput:
    fields = {
        "project_id",
        "open_dates",
        "time_slots",
        "students",
        "teachers",
        "subjects",
        "lesson_requests",
        "availabilities",
        "group_blocks",
        "existing_assignments",
        "settings",
    }
    require_fields(value, fields, path)
    return OptimizationInput(
        project_id=require_int(value["project_id"], f"{path}.project_id"),
        open_dates=map_array(value["open_dates"], f"{path}.open_dates", require_date),
        time_slots=map_array(value["time_slots"], f"{path}.time_slots", _slot_from),
        students=map_array(value["students"], f"{path}.students", _student_from),
        teachers=map_array(value["teachers"], f"{path}.teachers", _teacher_from),
        subjects=map_array(value["subjects"], f"{path}.subjects", _subject_from),
        lesson_requests=map_array(
            value["lesson_requests"],
            f"{path}.lesson_requests",
            _request_from,
        ),
        availabilities=map_array(
            value["availabilities"],
            f"{path}.availabilities",
            _availability_from,
        ),
        group_blocks=map_array(
            value["group_blocks"],
            f"{path}.group_blocks",
            _group_from,
        ),
        existing_assignments=map_array(
            value["existing_assignments"],
            f"{path}.existing_assignments",
            _existing_from,
        ),
        settings=_settings_from(value["settings"], f"{path}.settings"),
    )


def _slot_to_object(value: TimeSlotData) -> JsonObject:
    return {
        "id": value.id,
        "code": value.code,
        "display_name": value.display_name,
        "start_time": value.start_time.isoformat(),
        "end_time": value.end_time.isoformat(),
        "sort_order": value.sort_order,
        "enabled": value.enabled,
    }


def _slot_from(raw: object, path: str) -> TimeSlotData:
    value = _typed_object(
        raw,
        path,
        {"id", "code", "display_name", "start_time", "end_time", "sort_order", "enabled"},
    )
    return TimeSlotData(
        id=require_int(value["id"], f"{path}.id"),
        code=require_str(value["code"], f"{path}.code"),
        display_name=require_str(value["display_name"], f"{path}.display_name"),
        start_time=require_time(value["start_time"], f"{path}.start_time"),
        end_time=require_time(value["end_time"], f"{path}.end_time"),
        sort_order=require_int(value["sort_order"], f"{path}.sort_order"),
        enabled=require_bool(value["enabled"], f"{path}.enabled"),
    )


def _student_to_object(value: StudentData) -> JsonObject:
    return {
        "id": value.id,
        "display_name": value.display_name,
        "default_max_consecutive_slots": value.default_max_consecutive_slots,
        "allow_gap": value.allow_gap,
        "active": value.active,
    }


def _student_from(raw: object, path: str) -> StudentData:
    value = _typed_object(
        raw,
        path,
        {"id", "display_name", "default_max_consecutive_slots", "allow_gap", "active"},
    )
    return StudentData(
        id=require_int(value["id"], f"{path}.id"),
        display_name=require_str(value["display_name"], f"{path}.display_name"),
        default_max_consecutive_slots=require_int(
            value["default_max_consecutive_slots"],
            f"{path}.default_max_consecutive_slots",
        ),
        allow_gap=require_bool(value["allow_gap"], f"{path}.allow_gap"),
        active=require_bool(value["active"], f"{path}.active"),
    )


def _teacher_to_object(value: TeacherData) -> JsonObject:
    return {
        "id": value.id,
        "display_name": value.display_name,
        "qualified_subject_ids": sorted(value.qualified_subject_ids),
        "allow_gap": value.allow_gap,
        "active": value.active,
    }


def _teacher_from(raw: object, path: str) -> TeacherData:
    value = _typed_object(
        raw,
        path,
        {"id", "display_name", "qualified_subject_ids", "allow_gap", "active"},
    )
    return TeacherData(
        id=require_int(value["id"], f"{path}.id"),
        display_name=require_str(value["display_name"], f"{path}.display_name"),
        qualified_subject_ids=frozenset(
            int_tuple(value["qualified_subject_ids"], f"{path}.qualified_subject_ids")
        ),
        allow_gap=require_bool(value["allow_gap"], f"{path}.allow_gap"),
        active=require_bool(value["active"], f"{path}.active"),
    )


def _subject_to_object(value: SubjectData) -> JsonObject:
    return {
        "id": value.id,
        "code": value.code,
        "display_name": value.display_name,
        "active": value.active,
    }


def _subject_from(raw: object, path: str) -> SubjectData:
    value = _typed_object(
        raw,
        path,
        {"id", "code", "display_name", "active"},
    )
    return SubjectData(
        id=require_int(value["id"], f"{path}.id"),
        code=require_str(value["code"], f"{path}.code"),
        display_name=require_str(value["display_name"], f"{path}.display_name"),
        active=require_bool(value["active"], f"{path}.active"),
    )


def _request_to_object(value: LessonRequestData) -> JsonObject:
    return {
        "id": value.id,
        "student_id": value.student_id,
        "subject_id": value.subject_id,
        "required_sessions": value.required_sessions,
        "regular_teacher_id": value.regular_teacher_id,
        "regular_teacher_priority": value.regular_teacher_priority,
        "preferred_teacher_ids": list(value.preferred_teacher_ids),
        "one_to_one_required": value.one_to_one_required,
        "max_consecutive_slots_override": value.max_consecutive_slots_override,
        "allow_gap_override": value.allow_gap_override,
    }


def _request_from(raw: object, path: str) -> LessonRequestData:
    fields = {
        "id",
        "student_id",
        "subject_id",
        "required_sessions",
        "regular_teacher_id",
        "regular_teacher_priority",
        "preferred_teacher_ids",
        "one_to_one_required",
        "max_consecutive_slots_override",
        "allow_gap_override",
    }
    value = _typed_object(raw, path, fields)
    return LessonRequestData(
        id=require_int(value["id"], f"{path}.id"),
        student_id=require_int(value["student_id"], f"{path}.student_id"),
        subject_id=require_int(value["subject_id"], f"{path}.subject_id"),
        required_sessions=require_int(
            value["required_sessions"],
            f"{path}.required_sessions",
        ),
        regular_teacher_id=require_optional_int(
            value["regular_teacher_id"],
            f"{path}.regular_teacher_id",
        ),
        regular_teacher_priority=require_int(
            value["regular_teacher_priority"],
            f"{path}.regular_teacher_priority",
        ),
        preferred_teacher_ids=cast(
            tuple[int | None, int | None, int | None],
            exact_optional_int_tuple(
                value["preferred_teacher_ids"],
                f"{path}.preferred_teacher_ids",
                3,
            ),
        ),
        one_to_one_required=require_bool(
            value["one_to_one_required"],
            f"{path}.one_to_one_required",
        ),
        max_consecutive_slots_override=require_optional_int(
            value["max_consecutive_slots_override"],
            f"{path}.max_consecutive_slots_override",
        ),
        allow_gap_override=require_optional_bool(
            value["allow_gap_override"],
            f"{path}.allow_gap_override",
        ),
    )


def _availability_to_object(value: AvailabilityData) -> JsonObject:
    return {
        "owner_type": value.owner_type,
        "owner_id": value.owner_id,
        "day": value.day.isoformat(),
        "time_slot_id": value.time_slot_id,
        "level": value.level,
    }


def _availability_from(raw: object, path: str) -> AvailabilityData:
    value = _typed_object(
        raw,
        path,
        {"owner_type", "owner_id", "day", "time_slot_id", "level"},
    )
    owner = require_str(value["owner_type"], f"{path}.owner_type")
    if owner not in ("student", "teacher"):
        raise SnapshotDecodeError(f"{path}.owner_type が不正です")
    return AvailabilityData(
        owner_type=cast(AvailabilityOwner, owner),
        owner_id=require_int(value["owner_id"], f"{path}.owner_id"),
        day=require_date(value["day"], f"{path}.day"),
        time_slot_id=require_int(value["time_slot_id"], f"{path}.time_slot_id"),
        level=require_int(value["level"], f"{path}.level"),
    )


def _group_to_object(value: GroupBlockData) -> JsonObject:
    return {
        "id": value.id,
        "day": value.day.isoformat(),
        "start_time": value.start_time.isoformat(),
        "end_time": value.end_time.isoformat(),
        "teacher_id": value.teacher_id,
        "student_ids": sorted(value.student_ids),
    }


def _group_from(raw: object, path: str) -> GroupBlockData:
    value = _typed_object(
        raw,
        path,
        {"id", "day", "start_time", "end_time", "teacher_id", "student_ids"},
    )
    return GroupBlockData(
        id=require_int(value["id"], f"{path}.id"),
        day=require_date(value["day"], f"{path}.day"),
        start_time=require_time(value["start_time"], f"{path}.start_time"),
        end_time=require_time(value["end_time"], f"{path}.end_time"),
        teacher_id=require_optional_int(value["teacher_id"], f"{path}.teacher_id"),
        student_ids=frozenset(int_tuple(value["student_ids"], f"{path}.student_ids")),
    )


def _existing_to_object(value: ExistingAssignmentData) -> JsonObject:
    return {
        "id": value.id,
        "lesson_request_id": value.lesson_request_id,
        "session_index": value.session_index,
        "day": value.day.isoformat(),
        "time_slot_id": value.time_slot_id,
        "teacher_id": value.teacher_id,
        "is_locked": value.is_locked,
        "is_manual": value.is_manual,
    }


def _existing_from(raw: object, path: str) -> ExistingAssignmentData:
    fields = {
        "id",
        "lesson_request_id",
        "session_index",
        "day",
        "time_slot_id",
        "teacher_id",
        "is_locked",
        "is_manual",
    }
    value = _typed_object(raw, path, fields)
    return ExistingAssignmentData(
        id=require_int(value["id"], f"{path}.id"),
        lesson_request_id=require_int(
            value["lesson_request_id"],
            f"{path}.lesson_request_id",
        ),
        session_index=require_int(value["session_index"], f"{path}.session_index"),
        day=require_date(value["day"], f"{path}.day"),
        time_slot_id=require_int(value["time_slot_id"], f"{path}.time_slot_id"),
        teacher_id=require_int(value["teacher_id"], f"{path}.teacher_id"),
        is_locked=require_bool(value["is_locked"], f"{path}.is_locked"),
        is_manual=require_bool(value["is_manual"], f"{path}.is_manual"),
    )


def _settings_to_object(value: OptimizationSettings) -> JsonObject:
    return {
        "time_limit_seconds": value.time_limit_seconds,
        "random_seed": value.random_seed,
        "num_search_workers": value.num_search_workers,
        "regular_teacher_priority_weights": list(value.regular_teacher_priority_weights),
        "preferred_teacher_rank_weights": list(value.preferred_teacher_rank_weights),
        "student_preferred_time_weight": value.student_preferred_time_weight,
        "teacher_preferred_time_weight": value.teacher_preferred_time_weight,
        "preserve_existing_assignment_weight": (value.preserve_existing_assignment_weight),
        "optional_balance_weight": value.optional_balance_weight,
    }


def _settings_from(raw: object, path: str) -> OptimizationSettings:
    fields = {
        "time_limit_seconds",
        "random_seed",
        "num_search_workers",
        "regular_teacher_priority_weights",
        "preferred_teacher_rank_weights",
        "student_preferred_time_weight",
        "teacher_preferred_time_weight",
        "preserve_existing_assignment_weight",
        "optional_balance_weight",
    }
    value = _typed_object(raw, path, fields)
    regular = exact_int_tuple(
        value["regular_teacher_priority_weights"],
        f"{path}.regular_teacher_priority_weights",
        4,
    )
    preferred = exact_int_tuple(
        value["preferred_teacher_rank_weights"],
        f"{path}.preferred_teacher_rank_weights",
        3,
    )
    return OptimizationSettings(
        time_limit_seconds=require_float(
            value["time_limit_seconds"],
            f"{path}.time_limit_seconds",
        ),
        random_seed=require_int(value["random_seed"], f"{path}.random_seed"),
        num_search_workers=require_int(
            value["num_search_workers"],
            f"{path}.num_search_workers",
        ),
        regular_teacher_priority_weights=cast(tuple[int, int, int, int], regular),
        preferred_teacher_rank_weights=cast(tuple[int, int, int], preferred),
        student_preferred_time_weight=require_int(
            value["student_preferred_time_weight"],
            f"{path}.student_preferred_time_weight",
        ),
        teacher_preferred_time_weight=require_int(
            value["teacher_preferred_time_weight"],
            f"{path}.teacher_preferred_time_weight",
        ),
        preserve_existing_assignment_weight=require_int(
            value["preserve_existing_assignment_weight"],
            f"{path}.preserve_existing_assignment_weight",
        ),
        optional_balance_weight=require_int(
            value["optional_balance_weight"],
            f"{path}.optional_balance_weight",
        ),
    )


def _result_to_object(value: OptimizationResult) -> JsonObject:
    return {
        "solver_status": value.solver_status,
        "assignments": [_scheduled_to_object(item) for item in value.assignments],
        "unassigned_lessons": [_unassigned_to_object(item) for item in value.unassigned_lessons],
        "objective_breakdown": _objective_to_object(value.objective_breakdown),
        "elapsed_seconds": value.elapsed_seconds,
        "warnings": list(value.warnings),
        "cancelled": value.cancelled,
    }


def _result_from_object(value: JsonObject, path: str) -> OptimizationResult:
    fields = {
        "solver_status",
        "assignments",
        "unassigned_lessons",
        "objective_breakdown",
        "elapsed_seconds",
        "warnings",
        "cancelled",
    }
    require_fields(value, fields, path)
    status = require_str(value["solver_status"], f"{path}.solver_status")
    valid_statuses = {
        "OPTIMAL",
        "FEASIBLE",
        "INFEASIBLE",
        "UNKNOWN",
        "MODEL_INVALID",
    }
    if status not in valid_statuses:
        raise SnapshotDecodeError(f"{path}.solver_status が不正です")
    return OptimizationResult(
        solver_status=cast(SolverStatus, status),
        assignments=map_array(
            value["assignments"],
            f"{path}.assignments",
            _scheduled_from,
        ),
        unassigned_lessons=map_array(
            value["unassigned_lessons"],
            f"{path}.unassigned_lessons",
            _unassigned_from,
        ),
        objective_breakdown=_objective_from(
            value["objective_breakdown"],
            f"{path}.objective_breakdown",
        ),
        elapsed_seconds=require_float(
            value["elapsed_seconds"],
            f"{path}.elapsed_seconds",
        ),
        warnings=map_array(value["warnings"], f"{path}.warnings", require_str),
        cancelled=require_bool(value["cancelled"], f"{path}.cancelled"),
    )


def _scheduled_to_object(value: ScheduledAssignment) -> JsonObject:
    return {
        "lesson_request_id": value.lesson_request_id,
        "session_index": value.session_index,
        "student_id": value.student_id,
        "subject_id": value.subject_id,
        "teacher_id": value.teacher_id,
        "day": value.day.isoformat(),
        "time_slot_id": value.time_slot_id,
        "is_locked": value.is_locked,
    }


def _scheduled_from(raw: object, path: str) -> ScheduledAssignment:
    fields = {
        "lesson_request_id",
        "session_index",
        "student_id",
        "subject_id",
        "teacher_id",
        "day",
        "time_slot_id",
        "is_locked",
    }
    value = _typed_object(raw, path, fields)
    return ScheduledAssignment(
        lesson_request_id=require_int(
            value["lesson_request_id"],
            f"{path}.lesson_request_id",
        ),
        session_index=require_int(value["session_index"], f"{path}.session_index"),
        student_id=require_int(value["student_id"], f"{path}.student_id"),
        subject_id=require_int(value["subject_id"], f"{path}.subject_id"),
        teacher_id=require_int(value["teacher_id"], f"{path}.teacher_id"),
        day=require_date(value["day"], f"{path}.day"),
        time_slot_id=require_int(value["time_slot_id"], f"{path}.time_slot_id"),
        is_locked=require_bool(value["is_locked"], f"{path}.is_locked"),
    )


def _unassigned_to_object(value: UnassignedLesson) -> JsonObject:
    return {
        "lesson_request_id": value.lesson_request_id,
        "session_index": value.session_index,
        "student_id": value.student_id,
        "subject_id": value.subject_id,
        "reasons": [_reason_to_object(reason) for reason in value.reasons],
    }


def _unassigned_from(raw: object, path: str) -> UnassignedLesson:
    fields = {
        "lesson_request_id",
        "session_index",
        "student_id",
        "subject_id",
        "reasons",
    }
    value = _typed_object(raw, path, fields)
    return UnassignedLesson(
        lesson_request_id=require_int(
            value["lesson_request_id"],
            f"{path}.lesson_request_id",
        ),
        session_index=require_int(value["session_index"], f"{path}.session_index"),
        student_id=require_int(value["student_id"], f"{path}.student_id"),
        subject_id=require_int(value["subject_id"], f"{path}.subject_id"),
        reasons=map_array(value["reasons"], f"{path}.reasons", _reason_from),
    )


def _reason_to_object(value: DiagnosticReason) -> JsonObject:
    return {
        "code": value.code.value,
        "message": value.message,
        "excluded_candidate_count": value.excluded_candidate_count,
        "details": [[key, detail] for key, detail in value.details],
    }


def _reason_from(raw: object, path: str) -> DiagnosticReason:
    fields = {"code", "message", "excluded_candidate_count", "details"}
    value = _typed_object(raw, path, fields)
    code_text = require_str(value["code"], f"{path}.code")
    try:
        code = DiagnosticCode(code_text)
    except ValueError as exc:
        raise SnapshotDecodeError(f"{path}.code が不正です") from exc

    def detail_from(detail_raw: object, detail_path: str) -> tuple[str, str]:
        pair = map_array(detail_raw, detail_path, require_str)
        if len(pair) != 2:
            raise SnapshotDecodeError(f"{detail_path} は2要素である必要があります")
        return (pair[0], pair[1])

    return DiagnosticReason(
        code=code,
        message=require_str(value["message"], f"{path}.message"),
        excluded_candidate_count=require_int(
            value["excluded_candidate_count"],
            f"{path}.excluded_candidate_count",
        ),
        details=map_array(value["details"], f"{path}.details", detail_from),
    )


def _objective_to_object(value: ObjectiveBreakdown) -> JsonObject:
    return {
        "unassigned_count": value.unassigned_count,
        "teacher_preference_penalty": value.teacher_preference_penalty,
        "active_teacher_slot_count": value.active_teacher_slot_count,
        "availability_preference_score": value.availability_preference_score,
        "changed_assignment_count": value.changed_assignment_count,
        "optional_balance_score": value.optional_balance_score,
    }


def _objective_from(raw: object, path: str) -> ObjectiveBreakdown:
    fields = {
        "unassigned_count",
        "teacher_preference_penalty",
        "active_teacher_slot_count",
        "availability_preference_score",
        "changed_assignment_count",
        "optional_balance_score",
    }
    value = _typed_object(raw, path, fields)
    return ObjectiveBreakdown(
        unassigned_count=require_int(
            value["unassigned_count"],
            f"{path}.unassigned_count",
        ),
        teacher_preference_penalty=require_int(
            value["teacher_preference_penalty"],
            f"{path}.teacher_preference_penalty",
        ),
        active_teacher_slot_count=require_int(
            value["active_teacher_slot_count"],
            f"{path}.active_teacher_slot_count",
        ),
        availability_preference_score=require_int(
            value["availability_preference_score"],
            f"{path}.availability_preference_score",
        ),
        changed_assignment_count=require_int(
            value["changed_assignment_count"],
            f"{path}.changed_assignment_count",
        ),
        optional_balance_score=require_int(
            value["optional_balance_score"],
            f"{path}.optional_balance_score",
        ),
    )


def _typed_object(
    raw: object,
    path: str,
    fields: set[str],
) -> JsonObject:
    value = require_object(raw, path)
    require_fields(value, fields, path)
    return value


__all__ = [
    "SnapshotDecodeError",
    "optimization_input_from_json",
    "optimization_input_to_json",
    "optimization_result_from_json",
    "optimization_result_to_json",
]
