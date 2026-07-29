"""Phase 2の入力値をUIやDBから独立して検証する。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """入力欄へ関連付けられる検証結果。"""

    field: str
    message: str
    severity: Severity = "error"
    code: str = "invalid"


class DomainValidationError(ValueError):
    """1件以上のエラーをまとめて通知する。"""

    def __init__(self, issues: Iterable[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        message = "、".join(issue.message for issue in self.issues)
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TimeSlotInput:
    """コマ検証に必要な値。"""

    code: str
    display_name: str
    start_time: time
    end_time: time
    sort_order: int
    record_id: int | None = None


def parse_iso_date(value: str, field: str) -> date:
    """ISO日付文字列を読み、日本語の検証エラーへ変換する。"""
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise DomainValidationError(
            [ValidationIssue(field, "日付はYYYY-MM-DD形式で入力してください", code="date")]
        ) from exc


def parse_hhmm(value: str, field: str) -> time:
    """HH:MM時刻文字列を読み、日本語の検証エラーへ変換する。"""
    try:
        return time.fromisoformat(value.strip())
    except ValueError as exc:
        raise DomainValidationError(
            [ValidationIssue(field, "時刻はHH:MM形式で入力してください", code="time")]
        ) from exc


def validate_project(
    *,
    title: str,
    campus_name: str,
    start_date: date,
    end_date: date,
) -> tuple[ValidationIssue, ...]:
    """プロジェクト基本情報を検証する。"""
    issues: list[ValidationIssue] = []
    if not title.strip():
        issues.append(ValidationIssue("title", "プロジェクト名を入力してください"))
    if not campus_name.strip():
        issues.append(ValidationIssue("campus_name", "校舎名を入力してください"))
    if start_date > end_date:
        issues.append(
            ValidationIssue(
                "end_date",
                "講習終了日は開始日以降にしてください",
                code="date_range",
            )
        )
    return tuple(issues)


def validate_time_slots(
    slots: Iterable[TimeSlotInput],
) -> tuple[ValidationIssue, ...]:
    """空欄、重複、逆転、区間重複をまとめて検出する。"""
    values = tuple(slots)
    issues: list[ValidationIssue] = []
    seen_codes: dict[str, int | None] = {}
    seen_orders: dict[int, int | None] = {}

    for slot in values:
        normalized_code = slot.code.strip().upper()
        if not normalized_code:
            issues.append(ValidationIssue("code", "コマ名を入力してください"))
        elif normalized_code in seen_codes:
            issues.append(ValidationIssue("code", f"コマ名「{normalized_code}」が重複しています"))
        else:
            seen_codes[normalized_code] = slot.record_id

        if not slot.display_name.strip():
            issues.append(ValidationIssue("display_name", "表示名を入力してください"))

        if slot.sort_order <= 0:
            issues.append(ValidationIssue("sort_order", "順序は1以上にしてください"))
        elif slot.sort_order in seen_orders:
            issues.append(
                ValidationIssue(
                    "sort_order",
                    f"順序「{slot.sort_order}」が重複しています",
                )
            )
        else:
            seen_orders[slot.sort_order] = slot.record_id

        if slot.start_time >= slot.end_time:
            issues.append(
                ValidationIssue(
                    "end_time",
                    f"コマ「{normalized_code or '?'}」の終了時刻は開始時刻より後にしてください",
                    code="time_range",
                )
            )

    valid_ranges = [slot for slot in values if slot.start_time < slot.end_time]
    for index, left in enumerate(valid_ranges):
        for right in valid_ranges[index + 1 :]:
            if left.start_time < right.end_time and right.start_time < left.end_time:
                issues.append(
                    ValidationIssue(
                        "start_time",
                        f"コマ「{left.code}」と「{right.code}」の時刻が重複しています",
                        code="time_overlap",
                    )
                )
    return tuple(issues)


def validate_student(
    *,
    external_id: str,
    name: str,
    grade: str,
    max_consecutive_slots: int,
) -> tuple[ValidationIssue, ...]:
    """生徒入力の単項目を検証する。"""
    issues: list[ValidationIssue] = []
    if not external_id.strip():
        issues.append(ValidationIssue("external_id", "生徒IDを入力してください"))
    if not name.strip():
        issues.append(ValidationIssue("name", "氏名を入力してください"))
    if not grade.strip():
        issues.append(ValidationIssue("grade", "学年を入力してください"))
    if max_consecutive_slots <= 0:
        issues.append(
            ValidationIssue(
                "default_max_consecutive_slots",
                "標準最大連続コマ数は1以上にしてください",
            )
        )
    return tuple(issues)


def validate_teacher(*, external_id: str, name: str) -> tuple[ValidationIssue, ...]:
    """講師入力の必須項目を検証する。"""
    issues: list[ValidationIssue] = []
    if not external_id.strip():
        issues.append(ValidationIssue("external_id", "講師IDを入力してください"))
    if not name.strip():
        issues.append(ValidationIssue("name", "氏名を入力してください"))
    return tuple(issues)


def validate_subject(
    *,
    code: str,
    display_name: str,
    school_level: str,
    sort_order: int,
) -> tuple[ValidationIssue, ...]:
    """科目入力を検証する。"""
    issues: list[ValidationIssue] = []
    if not code.strip():
        issues.append(ValidationIssue("code", "科目コードを入力してください"))
    if not display_name.strip():
        issues.append(ValidationIssue("display_name", "科目名を入力してください"))
    if school_level not in {"elementary", "junior_high", "high_school"}:
        issues.append(ValidationIssue("school_level", "学校段階を選択してください"))
    if sort_order <= 0:
        issues.append(ValidationIssue("sort_order", "並び順は1以上にしてください"))
    return tuple(issues)


def validate_lesson_request(
    *,
    required_sessions: int,
    regular_teacher_priority: int,
    regular_teacher_id: int | None,
    preferred_teacher_ids: Iterable[int | None],
    max_consecutive_slots_override: int | None,
    regular_teacher_can_teach: bool | None,
) -> tuple[ValidationIssue, ...]:
    """LessonRequest固有の制約と警告を返す。"""
    issues: list[ValidationIssue] = []
    if required_sessions < 1:
        issues.append(ValidationIssue("required_sessions", "必要授業回数は1以上にしてください"))
    if not 1 <= regular_teacher_priority <= 5:
        issues.append(
            ValidationIssue(
                "regular_teacher_priority",
                "担当講師優先度は1～5にしてください",
            )
        )
    if regular_teacher_priority == 5 and regular_teacher_id is None:
        issues.append(
            ValidationIssue(
                "regular_teacher_id",
                "優先度5では通常担当講師が必須です",
                code="priority_five_teacher",
            )
        )
    if max_consecutive_slots_override is not None and max_consecutive_slots_override <= 0:
        issues.append(
            ValidationIssue(
                "max_consecutive_slots_override",
                "最大連続コマ数の上書きは1以上にしてください",
            )
        )

    preferred = [teacher_id for teacher_id in preferred_teacher_ids if teacher_id is not None]
    if len(preferred) != len(set(preferred)):
        issues.append(
            ValidationIssue(
                "preferred_teacher_ids",
                "希望講師が重複しています",
                severity="warning",
                code="duplicate_preferred_teacher",
            )
        )

    if regular_teacher_id is not None and regular_teacher_can_teach is False:
        severity: Severity = "error" if regular_teacher_priority == 5 else "warning"
        issues.append(
            ValidationIssue(
                "regular_teacher_id",
                "通常担当講師はこの科目を担当不可に設定されています",
                severity=severity,
                code="teacher_not_qualified",
            )
        )
    return tuple(issues)


def raise_for_errors(issues: Iterable[ValidationIssue]) -> None:
    """warningを保持したままerrorだけを例外化する。"""
    errors = tuple(issue for issue in issues if issue.severity == "error")
    if errors:
        raise DomainValidationError(errors)
