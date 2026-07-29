"""Phase 4最適化エンジンを匿名合成データで再現可能に計測する。"""

from __future__ import annotations

import argparse
import gc
import json
import math
import platform
import random
import sys
import time
import tracemalloc
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from importlib.metadata import version

from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    LessonRequestData,
    OptimizationInput,
    OptimizationSettings,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
)
from summer_scheduler.optimization.solver import solve_optimization

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

DEFAULT_SEED = 20260729
DEFAULT_SESSION_PATTERN = (3, 4)
BENCHMARK_START_DATE = date(2030, 7, 20)


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """合成データ規模と疎性を明示するベンチマーク設定。"""

    students: int = 150
    teachers: int = 40
    days: int = 40
    slots_per_day: int = 5
    subjects: int = 8
    requests_per_student: int = 2
    sessions_pattern: tuple[int, ...] = DEFAULT_SESSION_PATTERN
    student_available_days: int = 5
    student_slots_per_day: int = 2
    teacher_available_day_ratio: float = 0.75
    teacher_slots_per_day: int = 3
    qualifications_per_teacher: int = 3
    time_limit_seconds: float = 30.0
    seed: int = DEFAULT_SEED

    def validate(self) -> None:
        """生成不能または計測結果を誤解させる設定を拒否する。"""
        positive_integers = {
            "students": self.students,
            "teachers": self.teachers,
            "days": self.days,
            "slots_per_day": self.slots_per_day,
            "subjects": self.subjects,
            "requests_per_student": self.requests_per_student,
            "student_available_days": self.student_available_days,
            "student_slots_per_day": self.student_slots_per_day,
            "teacher_slots_per_day": self.teacher_slots_per_day,
            "qualifications_per_teacher": self.qualifications_per_teacher,
        }
        invalid = [name for name, value in positive_integers.items() if value <= 0]
        if invalid:
            raise ValueError(f"正の整数が必要です: {', '.join(sorted(invalid))}")
        if not self.sessions_pattern or any(value <= 0 for value in self.sessions_pattern):
            raise ValueError("sessions_patternには1以上の整数が必要です")
        if self.student_available_days > self.days:
            raise ValueError("student_available_daysはdays以下にしてください")
        if self.student_slots_per_day > self.slots_per_day:
            raise ValueError("student_slots_per_dayはslots_per_day以下にしてください")
        if self.teacher_slots_per_day > self.slots_per_day:
            raise ValueError("teacher_slots_per_dayはslots_per_day以下にしてください")
        if self.slots_per_day > 12:
            raise ValueError("生成時刻が日付をまたがないようslots_per_dayは12以下にしてください")
        if self.qualifications_per_teacher > self.subjects:
            raise ValueError("qualifications_per_teacherはsubjects以下にしてください")
        if not 0 < self.teacher_available_day_ratio <= 1:
            raise ValueError("teacher_available_day_ratioは0より大きく1以下にしてください")
        if not math.isfinite(self.time_limit_seconds) or self.time_limit_seconds <= 0:
            raise ValueError("time_limit_secondsには有限の正数が必要です")
        if self.seed < 0:
            raise ValueError("seedには0以上の整数が必要です")


def build_synthetic_input(config: BenchmarkConfig) -> OptimizationInput:
    """固定seedとIDだけを用いた匿名の疎なOptimizationInputを生成する。"""
    config.validate()
    rng = random.Random(config.seed)
    days = tuple(BENCHMARK_START_DATE + timedelta(days=offset) for offset in range(config.days))
    slots = _time_slots(config.slots_per_day)
    subjects = tuple(
        SubjectData(
            id=subject_id,
            code=f"SUBJ_{subject_id:02d}",
            display_name=f"SYNTHETIC_SUBJECT_{subject_id:02d}",
        )
        for subject_id in range(1, config.subjects + 1)
    )
    teachers = _teachers(config, rng)
    students = tuple(
        StudentData(
            id=student_id,
            display_name=f"SYNTHETIC_STUDENT_{student_id:04d}",
            default_max_consecutive_slots=3 if student_id % 20 == 0 else 2,
            allow_gap=student_id % 25 == 0,
        )
        for student_id in range(1, config.students + 1)
    )
    requests = _lesson_requests(config, students, teachers)
    availabilities = _availabilities(config, rng, days, slots, students, teachers)
    return OptimizationInput(
        project_id=0,
        open_dates=days,
        time_slots=slots,
        students=students,
        teachers=teachers,
        subjects=subjects,
        lesson_requests=requests,
        availabilities=availabilities,
        group_blocks=(),
        existing_assignments=(),
        settings=OptimizationSettings(
            time_limit_seconds=config.time_limit_seconds,
            random_seed=config.seed,
            num_search_workers=1,
            regular_teacher_priority_weights=(1, 3, 6, 10),
            preferred_teacher_rank_weights=(9, 6, 3),
            student_preferred_time_weight=1,
            teacher_preferred_time_weight=1,
            preserve_existing_assignment_weight=1,
            optional_balance_weight=0,
        ),
    )


def run_benchmark(
    config: BenchmarkConfig,
    *,
    trace_memory: bool = False,
) -> dict[str, JsonValue]:
    """候補生成と公開solver入口を別々に計測し、JSON化可能な結果を返す。

    通常の時間測定では、実アプリに存在しない大きな計測負荷を避けるため
    ``tracemalloc``を無効にする。Python allocationの参考値が必要な場合だけ明示的に
    有効化し、その計測時間を実用性能の合否判定には使わない。
    """
    config.validate()
    benchmark_started = time.perf_counter()
    input_started = time.perf_counter()
    data = build_synthetic_input(config)
    input_seconds = time.perf_counter() - input_started
    session_count = sum(request.required_sessions for request in data.lesson_requests)

    if trace_memory:
        tracemalloc.start()
    try:
        gc.collect()
        if trace_memory:
            tracemalloc.reset_peak()
        candidate_started = time.perf_counter()
        generation = generate_candidates(data)
        candidate_seconds = time.perf_counter() - candidate_started
        candidate_peak_bytes = tracemalloc.get_traced_memory()[1] if trace_memory else None
        candidate_counts = Counter(candidate.session_key for candidate in generation.candidates)
        per_session = sorted(
            candidate_counts.get(session.key, 0) for session in generation.sessions
        )
        candidate_count = len(generation.candidates)
        input_diagnostic_count = len(generation.input_diagnostics)
        del generation

        gc.collect()
        if trace_memory:
            tracemalloc.reset_peak()
        solve_started = time.perf_counter()
        result = solve_optimization(data)
        solve_seconds = time.perf_counter() - solve_started
        solve_peak_bytes = tracemalloc.get_traced_memory()[1] if trace_memory else None
    finally:
        if trace_memory:
            tracemalloc.stop()

    total_seconds = time.perf_counter() - benchmark_started
    return {
        "schema_version": 1,
        "runtime": {
            "python": platform.python_version(),
            "ortools": version("ortools"),
            "platform": platform.platform(),
        },
        "configuration": _config_json(config),
        "scale": {
            "students": len(data.students),
            "teachers": len(data.teachers),
            "days": len(data.open_dates),
            "slots_per_day": len(data.time_slots),
            "subjects": len(data.subjects),
            "lesson_requests": len(data.lesson_requests),
            "sessions": session_count,
            "availability_rows": len(data.availabilities),
        },
        "generation_rules": {
            "identities": "sequential synthetic IDs and SYNTHETIC_* display names only",
            "student_availability": (
                f"{config.student_available_days} seeded days/student, "
                f"{config.student_slots_per_day} consecutive slots/selected day"
            ),
            "teacher_availability": (
                f"{config.teacher_available_day_ratio:.3f} of days/teacher, "
                f"{config.teacher_slots_per_day} consecutive slots/selected day"
            ),
            "qualifications": (
                f"{config.qualifications_per_teacher} seeded subjects/teacher; "
                "each teacher's rotating base subject guarantees broad coverage"
            ),
            "lesson_requests": (
                f"{config.requests_per_student} requests/student; session pattern "
                f"{list(config.sessions_pattern)}; deterministic subject distribution"
            ),
            "solver": (
                "fixed seed, one CP-SAT search worker, five required lexicographic stages; "
                "optional sixth balance stage disabled"
            ),
            "group_blocks": 0,
            "existing_assignments": 0,
        },
        "timings_seconds": {
            "input_generation": _rounded(input_seconds),
            "candidate_generation": _rounded(candidate_seconds),
            "end_to_end_solve": _rounded(solve_seconds),
            "end_to_end_over_time_limit": _rounded(
                max(0.0, solve_seconds - config.time_limit_seconds)
            ),
            "solver_reported_elapsed": _rounded(result.elapsed_seconds),
            "total_benchmark": _rounded(total_seconds),
        },
        "candidates": {
            "count": candidate_count,
            "input_diagnostic_count": input_diagnostic_count,
            "per_session_min": min(per_session, default=0),
            "per_session_median": _percentile(per_session, 0.5),
            "per_session_p95": _percentile(per_session, 0.95),
            "per_session_max": max(per_session, default=0),
        },
        "result": {
            "status": result.solver_status,
            "assigned": len(result.assignments),
            "unassigned": len(result.unassigned_lessons),
            "cancelled": result.cancelled,
            "warning_count": len(result.warnings),
            "within_requested_wall_time": solve_seconds <= config.time_limit_seconds,
        },
        "memory": {
            "measured": trace_memory,
            "method": "tracemalloc" if trace_memory else "disabled",
            "scope": (
                "Python allocations only; native OR-Tools/C++ allocations are excluded"
                if trace_memory
                else "use --trace-memory for an instrumented Python-allocation reference"
            ),
            "timing_note": (
                "reported timings include tracemalloc instrumentation overhead"
                if trace_memory
                else "timings represent the normal application execution path"
            ),
            "candidate_generation_peak_bytes": candidate_peak_bytes,
            "candidate_generation_peak_mib": (
                _mib(candidate_peak_bytes) if candidate_peak_bytes is not None else None
            ),
            "end_to_end_solve_peak_bytes": solve_peak_bytes,
            "end_to_end_solve_peak_mib": (
                _mib(solve_peak_bytes) if solve_peak_bytes is not None else None
            ),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        config = BenchmarkConfig(
            students=args.students,
            teachers=args.teachers,
            days=args.days,
            slots_per_day=args.slots,
            subjects=args.subjects,
            requests_per_student=args.requests_per_student,
            sessions_pattern=args.sessions_pattern,
            student_available_days=args.student_available_days,
            student_slots_per_day=args.student_slots_per_day,
            teacher_available_day_ratio=args.teacher_available_day_ratio,
            teacher_slots_per_day=args.teacher_slots_per_day,
            qualifications_per_teacher=args.qualifications_per_teacher,
            time_limit_seconds=args.time_limit,
            seed=args.seed,
        )
        report = run_benchmark(config, trace_memory=args.trace_memory)
    except ValueError as exc:
        parser.error(str(exc))
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _teachers(config: BenchmarkConfig, rng: random.Random) -> tuple[TeacherData, ...]:
    teachers: list[TeacherData] = []
    subject_ids = tuple(range(1, config.subjects + 1))
    for offset in range(config.teachers):
        base_subject = subject_ids[offset % config.subjects]
        remaining = tuple(subject_id for subject_id in subject_ids if subject_id != base_subject)
        extra_count = config.qualifications_per_teacher - 1
        qualified = frozenset(
            (base_subject, *rng.sample(remaining, extra_count)) if extra_count else (base_subject,)
        )
        teacher_id = offset + 1
        teachers.append(
            TeacherData(
                id=teacher_id,
                display_name=f"SYNTHETIC_TEACHER_{teacher_id:03d}",
                qualified_subject_ids=qualified,
                allow_gap=teacher_id % 10 == 0,
            )
        )
    return tuple(teachers)


def _lesson_requests(
    config: BenchmarkConfig,
    students: tuple[StudentData, ...],
    teachers: tuple[TeacherData, ...],
) -> tuple[LessonRequestData, ...]:
    teachers_by_subject: dict[int, tuple[int, ...]] = {
        subject_id: tuple(
            teacher.id for teacher in teachers if subject_id in teacher.qualified_subject_ids
        )
        for subject_id in range(1, config.subjects + 1)
    }
    requests: list[LessonRequestData] = []
    request_id = 1
    for student in students:
        for request_offset in range(config.requests_per_student):
            subject_id = (
                (student.id - 1) * config.requests_per_student + request_offset
            ) % config.subjects + 1
            eligible = teachers_by_subject[subject_id]
            regular_index = (student.id + request_offset) % len(eligible) if eligible else 0
            regular_teacher_id = eligible[regular_index] if eligible else None
            preferred_values = (
                tuple(
                    eligible[(regular_index + rank) % len(eligible)]
                    for rank in range(min(3, len(eligible)))
                )
                if eligible
                else ()
            )
            preferred: tuple[int | None, int | None, int | None] = (
                preferred_values[0] if len(preferred_values) > 0 else None,
                preferred_values[1] if len(preferred_values) > 1 else None,
                preferred_values[2] if len(preferred_values) > 2 else None,
            )
            priority = (
                5
                if regular_teacher_id is not None and request_id % 20 == 0
                else (request_id - 1) % 4 + 1
            )
            requests.append(
                LessonRequestData(
                    id=request_id,
                    student_id=student.id,
                    subject_id=subject_id,
                    required_sessions=config.sessions_pattern[
                        request_offset % len(config.sessions_pattern)
                    ],
                    regular_teacher_id=regular_teacher_id,
                    regular_teacher_priority=priority,
                    preferred_teacher_ids=preferred,
                    one_to_one_required=request_id % 10 == 0,
                    max_consecutive_slots_override=3 if request_id % 17 == 0 else None,
                    allow_gap_override=True if request_id % 29 == 0 else None,
                )
            )
            request_id += 1
    return tuple(requests)


def _availabilities(
    config: BenchmarkConfig,
    rng: random.Random,
    days: tuple[date, ...],
    slots: tuple[TimeSlotData, ...],
    students: tuple[StudentData, ...],
    teachers: tuple[TeacherData, ...],
) -> tuple[AvailabilityData, ...]:
    rows: list[AvailabilityData] = []
    for student in students:
        selected_days = rng.sample(tuple(range(len(days))), config.student_available_days)
        for day_index in sorted(selected_days):
            start = rng.randrange(len(slots) - config.student_slots_per_day + 1)
            for slot_offset in range(config.student_slots_per_day):
                rows.append(
                    AvailabilityData(
                        owner_type="student",
                        owner_id=student.id,
                        day=days[day_index],
                        time_slot_id=slots[start + slot_offset].id,
                        level=2 if slot_offset == 0 else 1,
                    )
                )

    teacher_day_count = max(1, round(config.days * config.teacher_available_day_ratio))
    for teacher in teachers:
        selected_days = rng.sample(tuple(range(len(days))), teacher_day_count)
        for day_index in sorted(selected_days):
            start = rng.randrange(len(slots) - config.teacher_slots_per_day + 1)
            for slot_offset in range(config.teacher_slots_per_day):
                rows.append(
                    AvailabilityData(
                        owner_type="teacher",
                        owner_id=teacher.id,
                        day=days[day_index],
                        time_slot_id=slots[start + slot_offset].id,
                        level=2 if slot_offset == 1 else 1,
                    )
                )
    return tuple(rows)


def _time_slots(count: int) -> tuple[TimeSlotData, ...]:
    anchor = datetime.combine(BENCHMARK_START_DATE, datetime_time(9, 0))
    slots: list[TimeSlotData] = []
    for offset in range(count):
        start = anchor + timedelta(minutes=70 * offset)
        end = start + timedelta(minutes=60)
        slot_id = offset + 1
        slots.append(
            TimeSlotData(
                id=slot_id,
                code=f"S{slot_id}",
                display_name=f"SYNTHETIC_SLOT_{slot_id}",
                start_time=start.time(),
                end_time=end.time(),
                sort_order=slot_id,
            )
        )
    return tuple(slots)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="匿名合成データでPhase 4最適化性能をJSON計測します。",
    )
    parser.add_argument("--students", type=int, default=150)
    parser.add_argument("--teachers", type=int, default=40)
    parser.add_argument("--days", type=int, default=40)
    parser.add_argument("--slots", type=int, default=5)
    parser.add_argument("--subjects", type=int, default=8)
    parser.add_argument("--requests-per-student", type=int, default=2)
    parser.add_argument(
        "--sessions-pattern",
        type=_parse_session_pattern,
        default=DEFAULT_SESSION_PATTERN,
        metavar="N[,N...]",
    )
    parser.add_argument("--student-available-days", type=int, default=5)
    parser.add_argument("--student-slots-per-day", type=int, default=2)
    parser.add_argument("--teacher-available-day-ratio", type=float, default=0.75)
    parser.add_argument("--teacher-slots-per-day", type=int, default=3)
    parser.add_argument("--qualifications-per-teacher", type=int, default=3)
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--trace-memory",
        action="store_true",
        help="tracemalloc負荷込みのPython allocation参考値も測定する",
    )
    return parser


def _parse_session_pattern(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(int(part.strip()) for part in raw.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("整数をカンマ区切りで指定してください") from exc
    if not values or any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("1以上の整数をカンマ区切りで指定してください")
    return values


def _config_json(config: BenchmarkConfig) -> dict[str, JsonValue]:
    values = asdict(config)
    values["sessions_pattern"] = list(config.sessions_pattern)
    return values


def _percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    index = max(0, math.ceil(len(values) * ratio) - 1)
    return values[index]


def _mib(byte_count: int) -> float:
    return round(byte_count / (1024 * 1024), 3)


def _rounded(seconds: float) -> float:
    return round(seconds, 6)


if __name__ == "__main__":
    raise SystemExit(main())
