"""Phase 3のセル単位差分契約テスト。"""

from __future__ import annotations

from datetime import date

import pytest

from summer_scheduler.infrastructure.importing import (
    DiffBuildError,
    DiffStatus,
    build_cell_diff,
)


def test_diff_reports_added_changed_unchanged_and_deletion_candidate() -> None:
    target_date = date(2026, 8, 4)
    existing = (
        {"student_id": "S001", "date": target_date, "slot:Y": 1},
        {"student_id": "S002", "date": target_date, "slot:Y": 2},
        {"student_id": "S003", "date": target_date, "slot:Y": 1},
    )
    incoming = (
        {"student_id": "S001", "date": target_date, "slot:Y": 0},
        {"student_id": "S002", "date": target_date, "slot:Y": 2},
        {"student_id": "S004", "date": target_date, "slot:Y": 1},
    )

    result = build_cell_diff(
        existing,
        incoming,
        key_fields=("student_id", "date"),
        value_fields=("slot:Y",),
    )

    assert result.counts[DiffStatus.CHANGED] == 1
    assert result.counts[DiffStatus.UNCHANGED] == 1
    assert result.counts[DiffStatus.ADDED] == 1
    assert result.counts[DiffStatus.DELETION_CANDIDATE] == 1
    changed = next(row for row in result.rows if row.status is DiffStatus.CHANGED)
    assert changed.cells[0].field == "slot:Y"
    assert changed.cells[0].before == 1
    assert changed.cells[0].after == 0
    deletion = next(row for row in result.rows if row.status is DiffStatus.DELETION_CANDIDATE)
    assert deletion.after is None
    assert deletion.key["student_id"] == "S003"


def test_diff_rejects_duplicate_business_keys() -> None:
    duplicate = (
        {"student_id": "S001", "date": date(2026, 8, 4), "slot:Y": 1},
        {"student_id": "S001", "date": date(2026, 8, 4), "slot:Y": 2},
    )

    with pytest.raises(DiffBuildError, match="重複"):
        build_cell_diff(
            (),
            duplicate,
            key_fields=("student_id", "date"),
            value_fields=("slot:Y",),
        )
