"""50名の架空生徒と20名の架空講師を含むmaster_data.xlsxを生成する。"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

from summer_scheduler.domain.defaults import DEFAULT_SUBJECTS, SCHOOL_LEVEL_LABELS
from summer_scheduler.infrastructure.excel.schema import (
    LESSON_REQUEST_SHEET,
    QUALIFICATION_SHEET,
    STUDENT_SHEET,
    SUBJECT_SHEET,
    TEACHER_SHEET,
)
from summer_scheduler.infrastructure.excel.template import write_master_data_workbook

DEFAULT_OUTPUT = Path("generated_examples/master_data_example_50_students_20_teachers.xlsx")

_GRADE_LEVELS = (
    ("小4", "elementary"),
    ("小5", "elementary"),
    ("小6", "elementary"),
    ("中1", "junior_high"),
    ("中2", "junior_high"),
    ("中3", "junior_high"),
    ("高1", "high_school"),
    ("高2", "high_school"),
    ("高3", "high_school"),
)

_SUBJECTS_BY_LEVEL = {
    level: tuple(subject.code for subject in DEFAULT_SUBJECTS if subject.school_level == level)
    for level in ("elementary", "junior_high", "high_school")
}

# 講師ごとの資格を明示する。高校数学一般と数学III等を自動推定しない。
_QUALIFIED_SUBJECTS = {
    "T001": {"ES_ENG", "JH_ENG", "HS_ENG"},
    "T002": {"ES_ENG", "ES_JPN", "JH_ENG", "HS_ENG"},
    "T003": {"ES_ENG", "JH_ENG", "HS_ENG"},
    "T004": {"ES_ENG", "ES_JPN", "JH_ENG", "JH_JPN"},
    "T005": {"ES_MATH", "JH_MATH", "HS_MATH_GENERAL"},
    "T006": {"ES_MATH", "JH_MATH", "HS_MATH_GENERAL", "HS_MATH_III"},
    "T007": {"JH_MATH", "HS_MATH_GENERAL", "HS_MATH_III", "HS_PHYSICS"},
    "T008": {"ES_MATH", "JH_MATH", "HS_MATH_GENERAL", "HS_INFORMATICS"},
    "T009": {"ES_JPN", "JH_JPN", "HS_MODERN_JPN", "HS_CLASSICAL_JPN"},
    "T010": {"ES_JPN", "JH_JPN", "HS_MODERN_JPN", "HS_CLASSICAL_JPN"},
    "T011": {"ES_JPN", "JH_JPN", "HS_MODERN_JPN", "HS_CLASSICAL_JPN"},
    "T012": {"ES_SCI", "JH_SCI", "HS_CHEMISTRY", "HS_BIOLOGY"},
    "T013": {"ES_SCI", "JH_SCI", "HS_CHEMISTRY", "HS_BIOLOGY"},
    "T014": {"JH_SCI", "HS_MATH_GENERAL", "HS_PHYSICS", "HS_CHEMISTRY"},
    "T015": {"ES_SOC", "JH_SOC", "HS_JAPANESE_HISTORY", "HS_GEOGRAPHY"},
    "T016": {
        "ES_SOC",
        "JH_SOC",
        "HS_WORLD_HISTORY",
        "HS_GEOGRAPHY",
        "HS_POLITICS_ECONOMICS",
    },
    "T017": {"JH_MATH", "HS_MATH_GENERAL", "HS_INFORMATICS"},
    "T018": {"ES_ENG", "ES_MATH", "ES_JPN", "ES_SCI", "ES_SOC"},
    "T019": {"JH_ENG", "JH_MATH", "JH_JPN", "JH_SCI", "JH_SOC"},
    "T020": {
        "HS_ENG",
        "HS_MODERN_JPN",
        "HS_CLASSICAL_JPN",
        "HS_MATH_GENERAL",
        "HS_MATH_III",
        "HS_PHYSICS",
        "HS_CHEMISTRY",
        "HS_BIOLOGY",
        "HS_JAPANESE_HISTORY",
        "HS_WORLD_HISTORY",
        "HS_GEOGRAPHY",
        "HS_POLITICS_ECONOMICS",
        "HS_INFORMATICS",
    },
}


def build_example_rows() -> dict[str, list[dict[str, object]]]:
    """5シート分の決定的な架空データを構築する。"""
    students: list[dict[str, object]] = []
    teachers: list[dict[str, object]] = []
    subjects: list[dict[str, object]] = []
    qualifications: list[dict[str, object]] = []
    lesson_requests: list[dict[str, object]] = []

    for number in range(1, 21):
        teacher_id = f"T{number:03d}"
        teachers.append(
            {
                "external_id": teacher_id,
                "name": f"架空 講師{number:02d}",
                "allow_gap": number in {18, 19, 20},
                "note": "自動生成された架空の講師です。",
                "active": True,
            }
        )

    for subject in DEFAULT_SUBJECTS:
        subjects.append(
            {
                "code": subject.code,
                "display_name": subject.display_name,
                "school_level": SCHOOL_LEVEL_LABELS[subject.school_level],
                "sort_order": subject.sort_order,
                "active": True,
            }
        )

    for teacher_id in sorted(_QUALIFIED_SUBJECTS):
        teacher_subjects = _QUALIFIED_SUBJECTS[teacher_id]
        for subject in DEFAULT_SUBJECTS:
            can_teach = subject.code in teacher_subjects
            qualifications.append(
                {
                    "teacher_external_id": teacher_id,
                    "subject_code": subject.code,
                    "can_teach": can_teach,
                    "note": "架空の指導可能設定" if can_teach else None,
                }
            )

    request_number = 0
    for student_number in range(1, 51):
        grade, school_level = _GRADE_LEVELS[(student_number - 1) % len(_GRADE_LEVELS)]
        student_id = f"S{student_number:03d}"
        students.append(
            {
                "external_id": student_id,
                "name": f"架空 生徒{student_number:02d}",
                "grade": grade,
                "default_max_consecutive_slots": 3 if student_number % 17 == 0 else 2,
                "allow_gap": student_number % 19 == 0,
                "note": "自動生成された架空の生徒です。",
                "active": True,
            }
        )

        subject_pool = _SUBJECTS_BY_LEVEL[school_level]
        subject_count = 3 if student_number % 3 == 0 else 2
        start = (student_number * 2) % len(subject_pool)
        selected_subjects = tuple(
            subject_pool[(start + offset) % len(subject_pool)] for offset in range(subject_count)
        )
        for subject_offset, subject_code in enumerate(selected_subjects):
            request_number += 1
            qualified_teachers = _teachers_for_subject(subject_code)
            regular_index = (student_number + subject_offset) % len(qualified_teachers)
            regular_teacher = qualified_teachers[regular_index]
            preferred = _rotated(qualified_teachers, regular_index, maximum=3)
            lesson_requests.append(
                {
                    "student_external_id": student_id,
                    "subject_code": subject_code,
                    "required_sessions": 3 + ((student_number + subject_offset) % 4),
                    "regular_teacher_external_id": regular_teacher,
                    "regular_teacher_priority": (
                        5 if request_number % 9 == 0 else 2 + (request_number % 3)
                    ),
                    "preferred_teacher_1_external_id": preferred[0],
                    "preferred_teacher_2_external_id": (
                        preferred[1] if len(preferred) >= 2 else None
                    ),
                    "preferred_teacher_3_external_id": (
                        preferred[2] if len(preferred) >= 3 else None
                    ),
                    "one_to_one_required": request_number % 13 == 0,
                    "max_consecutive_slots_override": (3 if request_number % 29 == 0 else None),
                    "allow_gap_override": True if request_number % 31 == 0 else None,
                    "note": "自動生成された架空の受講希望です。",
                }
            )

    rows = {
        STUDENT_SHEET.name: students,
        TEACHER_SHEET.name: teachers,
        SUBJECT_SHEET.name: subjects,
        QUALIFICATION_SHEET.name: qualifications,
        LESSON_REQUEST_SHEET.name: lesson_requests,
    }
    validate_example_rows(rows)
    return rows


def validate_example_rows(
    rows_by_sheet: Mapping[str, Sequence[Mapping[str, object]]],
) -> None:
    """人数と、担当・希望講師の資格整合性を検証する。"""
    students = rows_by_sheet[STUDENT_SHEET.name]
    teachers = rows_by_sheet[TEACHER_SHEET.name]
    subjects = rows_by_sheet[SUBJECT_SHEET.name]
    qualifications = rows_by_sheet[QUALIFICATION_SHEET.name]
    requests = rows_by_sheet[LESSON_REQUEST_SHEET.name]
    if len(students) != 50:
        raise ValueError("架空生徒は50名である必要があります。")
    if len(teachers) != 20:
        raise ValueError("架空講師は20名である必要があります。")
    if len(subjects) != len(DEFAULT_SUBJECTS):
        raise ValueError("既定科目がすべて含まれていません。")

    qualified_pairs = {
        (str(row["teacher_external_id"]), str(row["subject_code"]))
        for row in qualifications
        if row["can_teach"] is True
    }
    known_teachers = {str(row["external_id"]) for row in teachers}
    known_students = {str(row["external_id"]) for row in students}
    known_subjects = {str(row["code"]) for row in subjects}
    for subject_code in known_subjects:
        if not any(pair[1] == subject_code for pair in qualified_pairs):
            raise ValueError(f"指導可能講師がいない科目です: {subject_code}")

    seen_requests: set[tuple[str, str]] = set()
    for row in requests:
        student_id = str(row["student_external_id"])
        subject_code = str(row["subject_code"])
        identity = (student_id, subject_code)
        if identity in seen_requests:
            raise ValueError(f"受講希望が重複しています: {student_id}/{subject_code}")
        seen_requests.add(identity)
        if student_id not in known_students or subject_code not in known_subjects:
            raise ValueError(f"受講希望の参照先が不明です: {student_id}/{subject_code}")
        for field in (
            "regular_teacher_external_id",
            "preferred_teacher_1_external_id",
            "preferred_teacher_2_external_id",
            "preferred_teacher_3_external_id",
        ):
            value = row.get(field)
            if value is None:
                continue
            teacher_id = str(value)
            if teacher_id not in known_teachers:
                raise ValueError(f"未登録講師です: {teacher_id}")
            if (teacher_id, subject_code) not in qualified_pairs:
                raise ValueError(
                    f"{field}の講師が科目を指導できません: {student_id}/{subject_code}/{teacher_id}"
                )


def generate_example_workbook(output: Path = DEFAULT_OUTPUT) -> Path:
    """架空データを検証し、Excelブックを生成する。"""
    destination = output.expanduser().resolve()
    write_master_data_workbook(destination, build_example_rows())
    return destination


def _teachers_for_subject(subject_code: str) -> tuple[str, ...]:
    teachers = tuple(
        teacher_id
        for teacher_id, subject_codes in sorted(_QUALIFIED_SUBJECTS.items())
        if subject_code in subject_codes
    )
    if not teachers:
        raise ValueError(f"指導可能講師がいない科目です: {subject_code}")
    return teachers


def _rotated(values: Sequence[str], start: int, *, maximum: int) -> tuple[str, ...]:
    return tuple(
        values[(start + offset) % len(values)] for offset in range(min(maximum, len(values)))
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="架空生徒50名・架空講師20名のmaster_data.xlsxを生成します。"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"出力先（既定: {DEFAULT_OUTPUT}）",
    )
    arguments = parser.parse_args()
    path = generate_example_workbook(arguments.output)
    rows = build_example_rows()
    print(f"generated: {path}")
    print(
        f"students={len(rows[STUDENT_SHEET.name])} "
        f"teachers={len(rows[TEACHER_SHEET.name])} "
        f"subjects={len(rows[SUBJECT_SHEET.name])} "
        f"qualifications={len(rows[QUALIFICATION_SHEET.name])} "
        f"lesson_requests={len(rows[LESSON_REQUEST_SHEET.name])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
