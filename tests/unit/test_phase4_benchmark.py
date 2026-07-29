"""Phase 4性能計測ツールの軽量smoke test。"""

from __future__ import annotations

from tools.benchmark_phase4 import (
    BenchmarkConfig,
    build_synthetic_input,
    run_benchmark,
)

from summer_scheduler.optimization.serialization import optimization_input_to_json


def test_synthetic_benchmark_input_is_reproducible_and_anonymous() -> None:
    config = _small_config()

    first = build_synthetic_input(config)
    second = build_synthetic_input(config)

    assert optimization_input_to_json(first) == optimization_input_to_json(second)
    assert all(item.display_name.startswith("SYNTHETIC_STUDENT_") for item in first.students)
    assert all(item.display_name.startswith("SYNTHETIC_TEACHER_") for item in first.teachers)
    assert sum(item.required_sessions for item in first.lesson_requests) == 4
    assert first.settings.random_seed == config.seed
    assert first.settings.num_search_workers == 1


def test_small_benchmark_reports_normal_path_timings_without_instrumentation() -> None:
    report = run_benchmark(_small_config())

    scale = report["scale"]
    candidates = report["candidates"]
    result = report["result"]
    timings = report["timings_seconds"]
    memory = report["memory"]
    assert isinstance(scale, dict)
    assert isinstance(candidates, dict)
    assert isinstance(result, dict)
    assert isinstance(timings, dict)
    assert isinstance(memory, dict)
    assert scale["students"] == 4
    assert scale["sessions"] == 4
    assert isinstance(candidates["count"], int) and candidates["count"] > 0
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assigned = result["assigned"]
    unassigned = result["unassigned"]
    assert isinstance(assigned, int)
    assert isinstance(unassigned, int)
    assert assigned + unassigned == 4
    assert result["within_requested_wall_time"] is True
    assert isinstance(timings["candidate_generation"], float)
    assert isinstance(timings["end_to_end_solve"], float)
    assert timings["end_to_end_over_time_limit"] == 0.0
    assert memory["measured"] is False
    assert memory["method"] == "disabled"
    assert memory["end_to_end_solve_peak_bytes"] is None


def test_memory_metrics_require_explicit_instrumentation() -> None:
    report = run_benchmark(_small_config(), trace_memory=True)

    memory = report["memory"]
    assert isinstance(memory, dict)
    assert memory["measured"] is True
    assert memory["method"] == "tracemalloc"
    assert isinstance(memory["candidate_generation_peak_bytes"], int)
    assert isinstance(memory["end_to_end_solve_peak_bytes"], int)


def _small_config() -> BenchmarkConfig:
    return BenchmarkConfig(
        students=4,
        teachers=3,
        days=3,
        slots_per_day=3,
        subjects=2,
        requests_per_student=1,
        sessions_pattern=(1,),
        student_available_days=2,
        student_slots_per_day=2,
        teacher_available_day_ratio=1.0,
        teacher_slots_per_day=2,
        qualifications_per_teacher=1,
        time_limit_seconds=2,
        seed=1234,
    )
