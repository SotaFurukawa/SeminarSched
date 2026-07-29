"""Phase 7の目標規模を、匿名データだけで通し計測する。"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from sqlalchemy import select

from summer_scheduler.application.availability_import_service import (
    AvailabilityImportService,
)
from summer_scheduler.application.master_data_service import MasterDataService
from summer_scheduler.application.optimization_run_service import (
    OptimizationRunService,
)
from summer_scheduler.application.output_service import OutputService
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.application.project_validation_service import (
    ProjectValidationService,
)
from summer_scheduler.application.schedule_edit_service import ScheduleEditService
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    LessonRequest,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TeacherQualification,
    TimeSlot,
)
from summer_scheduler.infrastructure.importing import (
    STUDENT_AVAILABILITY_SHEET,
    write_student_availability_template,
)
from summer_scheduler.optimization.dto import LessonRequestData, OptimizationInput
from summer_scheduler.optimization.solver import solve_optimization
from summer_scheduler.shared.settings import load_settings
from summer_scheduler.ui.viewmodels.schedule_editor_view_model import (
    ScheduleEditorViewModel,
)
from tools.benchmark_phase4 import BenchmarkConfig, build_synthetic_input

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Phase7OperationConfig:
    """目標規模と通し計測の実行条件。"""

    students: int = 150
    teachers: int = 40
    days: int = 40
    slots_per_day: int = 5
    subjects: int = 8
    requests_per_student: int = 2
    optimization_time_limit_seconds: float = 30.0
    seed: int = 20260729

    def validate(self) -> None:
        positive = {
            "students": self.students,
            "teachers": self.teachers,
            "days": self.days,
            "slots_per_day": self.slots_per_day,
            "subjects": self.subjects,
            "requests_per_student": self.requests_per_student,
        }
        if invalid := [name for name, value in positive.items() if value <= 0]:
            raise ValueError(f"正の整数が必要です: {', '.join(sorted(invalid))}")
        if self.slots_per_day != 5:
            raise ValueError("DB通し計測では既定の5コマを指定してください")
        if self.subjects > 23:
            raise ValueError("DB通し計測の科目数は既定科目数23以下にしてください")
        if self.requests_per_student > self.subjects:
            raise ValueError("生徒ごとの希望数は科目数以下にしてください")
        if self.optimization_time_limit_seconds <= 0:
            raise ValueError("最適化上限秒数は正数で指定してください")


def run_phase7_operations(config: Phase7OperationConfig) -> dict[str, JsonValue]:
    """匿名DBを生成し、Phase 7で求められた主要操作を同一processで計測する。"""
    config.validate()
    started = time.perf_counter()
    synthetic_config = BenchmarkConfig(
        students=config.students,
        teachers=config.teachers,
        days=config.days,
        slots_per_day=config.slots_per_day,
        subjects=config.subjects,
        requests_per_student=config.requests_per_student,
        student_available_days=min(5, config.days),
        student_slots_per_day=min(2, config.slots_per_day),
        teacher_slots_per_day=min(3, config.slots_per_day),
        qualifications_per_teacher=min(3, config.subjects),
        time_limit_seconds=config.optimization_time_limit_seconds,
        seed=config.seed,
    )
    synthetic = build_synthetic_input(synthetic_config)
    session_count = sum(row.required_sessions for row in synthetic.lesson_requests)

    with tempfile.TemporaryDirectory(prefix="summer-scheduler-phase7-") as raw_directory:
        working_directory = Path(raw_directory).resolve()
        startup_seconds = _measure_startup(working_directory)
        registry_path = working_directory / "アプリ管理" / "registry.db"
        project_path = (
            working_directory
            / ("日本語の長いパス-" + "あ" * 48)
            / "Phase 7 匿名性能確認.jukuschedule"
        )
        backup_directory = working_directory / "バックアップ"
        registry = create_database(registry_path)
        upgrade_database(registry.engine)
        projects = ProjectService(registry, backup_directory)
        try:
            seed_started = time.perf_counter()
            projects.create_project(
                project_path,
                title="Phase 7 匿名性能確認",
                campus_name="架空目標規模校",
                start_date=synthetic.open_dates[0],
                end_date=synthetic.open_dates[-1],
            )
            seeded_student_availability, seeded_teacher_availability = _seed_project(
                projects,
                synthetic,
            )
            seed_seconds = time.perf_counter() - seed_started

            projects.close_project()
            load_started = time.perf_counter()
            projects.open_project(project_path)
            project_load_seconds = time.perf_counter() - load_started

            list_started = time.perf_counter()
            master = MasterDataService(projects)
            listed_students = master.list_students()
            listed_teachers = master.list_teachers()
            listed_subjects = master.list_subjects()
            listed_requests = master.list_lesson_requests()
            master_list_seconds = time.perf_counter() - list_started

            import_source = working_directory / "匿名アンケート150名.xlsx"
            _write_import_source(projects, synthetic, import_source)
            import_service = AvailabilityImportService(projects)
            import_started = time.perf_counter()
            preview = import_service.prepare_import(
                "student",
                import_source,
                sheet_name=STUDENT_AVAILABILITY_SHEET,
            )
            if preview.has_errors:
                codes = ",".join(sorted({row.code for row in preview.issues}))
                raise RuntimeError(f"匿名アンケートの検証に失敗しました: {codes}")
            import_result = import_service.apply_import(preview)
            availability_import_seconds = time.perf_counter() - import_started

            validation_started = time.perf_counter()
            issues = ProjectValidationService(projects).run_validation()
            input_validation_seconds = time.perf_counter() - validation_started
            error_count = sum(row.severity == "error" for row in issues)
            if error_count:
                codes = ",".join(
                    sorted({row.issue_type for row in issues if row.severity == "error"})
                )
                raise RuntimeError(f"目標規模入力に検証エラーが{error_count}件あります: {codes}")

            app_settings = load_settings()
            optimization_settings = replace(
                app_settings.optimization,
                fast_time_limit_seconds=config.optimization_time_limit_seconds,
            )
            run_service = OptimizationRunService(projects, optimization_settings)
            prepare_started = time.perf_counter()
            prepared = run_service.prepare(
                "fast",
                log_directory=working_directory / "最適化ログ",
            )
            optimization_prepare_seconds = time.perf_counter() - prepare_started
            solve_started = time.perf_counter()
            result = solve_optimization(prepared.input)
            optimization_solve_seconds = time.perf_counter() - solve_started
            finalize_started = time.perf_counter()
            finalized = run_service.finalize(prepared, result)
            optimization_finalize_seconds = time.perf_counter() - finalize_started

            board_started = time.perf_counter()
            board = ScheduleEditService(projects, optimization_settings).load_board()
            schedule_board_seconds = time.perf_counter() - board_started

            view_started = time.perf_counter()
            view_model = ScheduleEditorViewModel(
                ScheduleEditService(projects, optimization_settings),
                projects,
            )
            for row in board.dates:
                if not view_model.selectDate(row.day.isoformat()):
                    raise RuntimeError("時間割の日付切替に失敗しました")
            schedule_view_updates_seconds = time.perf_counter() - view_started

            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtGui import QGuiApplication

            gui_application = QGuiApplication.instance()
            if gui_application is None:
                gui_application = QGuiApplication(["phase7-performance", "-platform", "offscreen"])
            output = OutputService(
                projects,
                optimization_settings,
                output_defaults=app_settings.output,
            )
            output_directory = working_directory / "匿名出力"
            excel_started = time.perf_counter()
            excel = output.export_excel(
                "overall",
                output_directory / "目標規模時間割.xlsx",
            )
            excel_seconds = time.perf_counter() - excel_started
            pdf_started = time.perf_counter()
            pdf = output.export_pdf(
                "overall",
                output_directory / "目標規模時間割.pdf",
            )
            pdf_seconds = time.perf_counter() - pdf_started
            gui_application.processEvents()

            peak_working_set = _windows_peak_working_set_bytes()
            database_size = project_path.stat().st_size
            return {
                "schema_version": 1,
                "runtime": {
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                },
                "configuration": _config_json(config),
                "scale": {
                    "students": len(listed_students),
                    "teachers": len(listed_teachers),
                    "days": len(synthetic.open_dates),
                    "slots_per_day": len(synthetic.time_slots),
                    "subjects_used": config.subjects,
                    "subjects_listed": len(listed_subjects),
                    "lesson_requests": len(listed_requests),
                    "requested_sessions": session_count,
                    "student_availability_rows_seeded": (seeded_student_availability),
                    "student_availability_rows_after_import": (
                        seeded_student_availability + import_result.added
                    ),
                    "teacher_availability_rows": seeded_teacher_availability,
                },
                "timings_seconds": {
                    "application_startup_smoke": _rounded(startup_seconds),
                    "target_project_seed": _rounded(seed_seconds),
                    "target_project_load_with_automatic_backup": _rounded(project_load_seconds),
                    "master_lists_total": _rounded(master_list_seconds),
                    "student_availability_prepare_and_apply": _rounded(availability_import_seconds),
                    "input_validation": _rounded(input_validation_seconds),
                    "optimization_prepare": _rounded(optimization_prepare_seconds),
                    "optimization_solve": _rounded(optimization_solve_seconds),
                    "optimization_finalize": _rounded(optimization_finalize_seconds),
                    "schedule_board_query": _rounded(schedule_board_seconds),
                    "schedule_view_model_40_date_updates": _rounded(schedule_view_updates_seconds),
                    "overall_excel_generation": _rounded(excel_seconds),
                    "overall_pdf_generation": _rounded(pdf_seconds),
                    "total_benchmark": _rounded(time.perf_counter() - started),
                },
                "import": {
                    "rows": len(preview.rows),
                    "added_cells": import_result.added,
                    "changed_cells": import_result.changed,
                    "unchanged_cells": import_result.unchanged,
                    "delete_candidates_not_applied": sum(
                        row.operation == "delete_candidate" for row in preview.diffs
                    ),
                },
                "validation": {
                    "errors": error_count,
                    "warnings": sum(row.severity == "warning" for row in issues),
                },
                "optimization": {
                    "status": result.solver_status,
                    "assigned": finalized.assignment_count,
                    "unassigned": finalized.unassigned_count,
                    "warning_count": finalized.warning_count,
                    "requested_time_limit_seconds": (config.optimization_time_limit_seconds),
                    "within_requested_wall_time": (
                        optimization_solve_seconds <= config.optimization_time_limit_seconds
                    ),
                },
                "schedule": {
                    "cards": len(board.cards),
                    "unassigned_sessions": board.unassigned_count,
                    "date_updates": len(board.dates),
                    "teacher_columns": len(board.teachers),
                    "slot_rows": len(board.slots),
                },
                "output": {
                    "excel_bytes": excel.path.stat().st_size,
                    "excel_pages": excel.page_count_optional,
                    "pdf_bytes": pdf.path.stat().st_size,
                    "pdf_pages": pdf.page_count_optional,
                },
                "storage": {
                    "project_database_bytes": database_size,
                    "long_japanese_project_path_characters": len(str(project_path)),
                },
                "memory": {
                    "method": (
                        "Windows GetProcessMemoryInfo PeakWorkingSetSize"
                        if peak_working_set is not None
                        else "not available on this platform"
                    ),
                    "peak_working_set_bytes": peak_working_set,
                    "peak_working_set_mib": (
                        _mib(peak_working_set) if peak_working_set is not None else None
                    ),
                },
            }
        finally:
            projects.close_project()
            registry.dispose()


def _seed_project(
    projects: ProjectService,
    synthetic: OptimizationInput,
) -> tuple[int, int]:
    data = synthetic
    project_id = projects.require_project().project_id
    student_availability = {
        (row.owner_id, row.day, row.time_slot_id): row.level
        for row in data.availabilities
        if row.owner_type == "student"
    }
    teacher_availability = {
        (row.owner_id, row.day, row.time_slot_id): row.level
        for row in data.availabilities
        if row.owner_type == "teacher"
    }
    # Application Serviceは優先度5の指定講師との共通候補不足を入力エラーにする。
    # 純粋solverベンチの難しさを保ちつつ、通し業務計測だけは開始可能な入力にする。
    for request in data.lesson_requests:
        if request.regular_teacher_priority != 5 or request.regular_teacher_id is None:
            continue
        base = request.id // 20
        for index in range(request.required_sessions):
            day = data.open_dates[(base + index) % len(data.open_dates)]
            slot_id = data.time_slots[(base + index) % len(data.time_slots)].id
            student_availability[(request.student_id, day, slot_id)] = 1
            teacher_availability[(request.regular_teacher_id, day, slot_id)] = 1
    database = projects.require_database()
    with database.session_factory.begin() as session:
        subject_ids = tuple(session.scalars(select(Subject.id).order_by(Subject.id)))
        slot_ids = tuple(
            session.scalars(
                select(TimeSlot.id)
                .where(TimeSlot.project_id == project_id)
                .order_by(TimeSlot.sort_order)
            )
        )
        required_subject_ids = tuple(row.id for row in data.subjects)
        required_slot_ids = tuple(row.id for row in data.time_slots)
        if subject_ids[: len(required_subject_ids)] != required_subject_ids:
            raise RuntimeError("既定科目IDが匿名入力と一致しません")
        if slot_ids != required_slot_ids:
            raise RuntimeError("既定コマIDが匿名入力と一致しません")
        session.add_all(
            Student(
                id=row.id,
                external_id=f"SYNTHETIC-STUDENT-{row.id:04d}",
                name=f"架空 生徒{row.id:04d}",
                grade=f"中{(row.id - 1) % 3 + 1}",
                default_max_consecutive_slots=row.default_max_consecutive_slots,
                allow_gap=row.allow_gap,
                note="匿名性能データ",
                active=True,
            )
            for row in data.students
        )
        session.add_all(
            Teacher(
                id=row.id,
                external_id=f"SYNTHETIC-TEACHER-{row.id:03d}",
                name=f"架空 講師{row.id:03d}",
                allow_gap=row.allow_gap,
                note="匿名性能データ",
                active=True,
            )
            for row in data.teachers
        )
        session.flush()
        session.add_all(
            TeacherQualification(
                teacher_id=teacher.id,
                subject_id=subject_id,
                can_teach=True,
                note="匿名性能データ",
            )
            for teacher in data.teachers
            for subject_id in teacher.qualified_subject_ids
        )
        session.add_all(
            LessonRequest(
                id=row.id,
                project_id=project_id,
                student_id=row.student_id,
                subject_id=row.subject_id,
                required_sessions=row.required_sessions,
                regular_teacher_id_optional=row.regular_teacher_id,
                regular_teacher_priority=row.regular_teacher_priority,
                preferred_teacher_1_id_optional=row.preferred_teacher_ids[0],
                preferred_teacher_2_id_optional=row.preferred_teacher_ids[1],
                preferred_teacher_3_id_optional=row.preferred_teacher_ids[2],
                one_to_one_required=row.one_to_one_required,
                max_consecutive_slots_override_optional=(row.max_consecutive_slots_override),
                allow_gap_override_optional=row.allow_gap_override,
                note="匿名性能データ",
            )
            for row in data.lesson_requests
        )
        session.add_all(
            StudentAvailability(
                project_id=project_id,
                student_id=student_id,
                date=day,
                time_slot_id=time_slot_id,
                availability_level=level,
            )
            for (student_id, day, time_slot_id), level in student_availability.items()
        )
        session.add_all(
            TeacherAvailability(
                project_id=project_id,
                teacher_id=teacher_id,
                date=day,
                time_slot_id=time_slot_id,
                availability_level=level,
            )
            for (teacher_id, day, time_slot_id), level in teacher_availability.items()
        )
    return len(student_availability), len(teacher_availability)


def _write_import_source(
    projects: ProjectService,
    synthetic: OptimizationInput,
    path: Path,
) -> None:
    data = synthetic
    database = projects.require_database()
    with database.session_factory() as session:
        subject_codes: dict[int, str] = {
            row.id: row.code for row in session.scalars(select(Subject))
        }
        slot_codes = tuple(
            session.scalars(
                select(TimeSlot.code)
                .where(TimeSlot.project_id == projects.require_project().project_id)
                .order_by(TimeSlot.sort_order)
            )
        )
    request_by_student: dict[int, LessonRequestData] = {}
    for request in data.lesson_requests:
        request_by_student.setdefault(request.student_id, request)
    first_day = data.open_dates[0]
    rows = [
        {
            "student_id": f"SYNTHETIC-STUDENT-{student.id:04d}",
            "student_name": f"架空 生徒{student.id:04d}",
            "subject_code": subject_codes[request_by_student[student.id].subject_id],
            "date": first_day,
            **{
                f"slot:{code}": 2 if index == student.id % len(slot_codes) else 1
                for index, code in enumerate(slot_codes)
            },
            "preferred_teacher_1": "",
            "preferred_teacher_2": "",
            "preferred_teacher_3": "",
            "note": "匿名性能データ",
        }
        for student in data.students
    ]
    write_student_availability_template(path, slot_codes, rows)


def _measure_startup(working_directory: Path) -> float:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONUTF8": "1",
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QSG_RHI_BACKEND": "software",
            "SUMMER_SCHEDULER_DATA_DIR": str(working_directory / "起動データ"),
            "SUMMER_SCHEDULER_LOG_DIR": str(working_directory / "起動ログ"),
        }
    )
    environment.pop("SUMMER_SCHEDULER_CONFIG", None)
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-m", "summer_scheduler", "--smoke-test"],
        env=environment,
        capture_output=True,
        timeout=60,
        check=False,
    )
    elapsed = time.perf_counter() - started
    if completed.returncode:
        raise RuntimeError(
            f"オフスクリーン起動確認に失敗しました: returncode={completed.returncode}"
        )
    return elapsed


def _windows_peak_working_set_bytes() -> int | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = ()
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernel32.GetCurrentProcess()
    succeeded = psapi.GetProcessMemoryInfo(
        process,
        ctypes.byref(counters),
        counters.cb,
    )
    return int(counters.PeakWorkingSetSize) if succeeded else None


def _config_json(config: Phase7OperationConfig) -> dict[str, JsonValue]:
    return {key: value for key, value in asdict(config).items()}


def _rounded(seconds: float) -> float:
    return round(seconds, 6)


def _mib(byte_count: int) -> float:
    return round(byte_count / (1024 * 1024), 3)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 7の匿名目標規模DBと主要操作をJSON計測します",
    )
    parser.add_argument("--students", type=int, default=150)
    parser.add_argument("--teachers", type=int, default=40)
    parser.add_argument("--days", type=int, default=40)
    parser.add_argument("--slots", type=int, default=5)
    parser.add_argument("--subjects", type=int, default=8)
    parser.add_argument("--requests-per-student", type=int, default=2)
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=20260729)
    return parser


def main() -> int:
    parser = _argument_parser()
    args = parser.parse_args()
    try:
        report = run_phase7_operations(
            Phase7OperationConfig(
                students=args.students,
                teachers=args.teachers,
                days=args.days,
                slots_per_day=args.slots,
                subjects=args.subjects,
                requests_per_student=args.requests_per_student,
                optimization_time_limit_seconds=args.time_limit,
                seed=args.seed,
            )
        )
    except ValueError as exc:
        parser.error(str(exc))
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
