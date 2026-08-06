"""手動列マッピング、型正規化、DB非依存の基礎行検証。"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from types import MappingProxyType

from summer_scheduler.infrastructure.importing.contracts import (
    ImportIssue,
    IssueSeverity,
    MappingConfigurationError,
    MappingResult,
    NormalizedRow,
    SourceRow,
    SourceTable,
    immutable_mapping,
    immutable_string_mapping,
)
from summer_scheduler.infrastructure.importing.schemas import (
    FieldKind,
    FieldSpec,
    ImportSchema,
)

_EXAMPLE_MARKERS = frozenset(
    {
        "1",
        "true",
        "yes",
        "y",
        "はい",
        "例",
        "例示",
        "サンプル",
        "example",
    }
)


def normalize_header(value: str) -> str:
    """全半角・大小文字・空白の差を吸収して列名を比較する。"""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    compact = "".join(character for character in normalized if not character.isspace())
    return compact.removesuffix("(必須)")


def suggest_column_mapping(
    schema: ImportSchema,
    headers: tuple[str, ...],
) -> Mapping[str, str]:
    """schemaの列名候補と一致する入力列を安全に自動提案する。"""
    normalized_headers: dict[str, str] = {}
    ambiguous: set[str] = set()
    for header in headers:
        normalized = normalize_header(header)
        if normalized in normalized_headers:
            ambiguous.add(normalized)
        else:
            normalized_headers[normalized] = header

    mapping: dict[str, str] = {}
    used_headers: set[str] = set()
    for field in schema.fields:
        for accepted_header in field.accepted_headers:
            normalized = normalize_header(accepted_header)
            source_header = normalized_headers.get(normalized)
            if (
                source_header is not None
                and normalized not in ambiguous
                and source_header not in used_headers
            ):
                mapping[field.key] = source_header
                used_headers.add(source_header)
                break
    return MappingProxyType(mapping)


def map_table(
    table: SourceTable,
    schema: ImportSchema,
    column_mapping: Mapping[str, str] | None = None,
) -> MappingResult:
    """入力表をcanonical keyへ変換し、必須値・型・重複を検証する。"""
    mapping = dict(
        suggest_column_mapping(schema, table.headers) if column_mapping is None else column_mapping
    )
    configuration_issues = _mapping_issues(table, schema, mapping)
    fatal_mapping_keys = {
        issue.column_key
        for issue in configuration_issues
        if issue.severity is IssueSeverity.ERROR and issue.column_key is not None
    }
    used_headers = set(mapping.values())
    unmapped_headers = tuple(header for header in table.headers if header not in used_headers)

    rows: list[NormalizedRow] = []
    issues = list(configuration_issues)
    skipped_examples: list[int] = []
    seen_keys: dict[tuple[object, ...], int] = {}

    for source_row in table.rows:
        if _is_example_row(source_row, mapping):
            skipped_examples.append(source_row.row_number)
            continue

        values: dict[str, object] = {"example": False}
        row_issues: list[ImportIssue] = []
        for field in schema.fields:
            if field.key == "example" or field.key in fatal_mapping_keys:
                continue
            source_header = mapping.get(field.key)
            if source_header is None:
                continue
            raw_value = source_row.raw_values.get(source_header)
            try:
                values[field.key] = _normalize_value(raw_value, field)
            except ValueError as exc:
                row_issues.append(
                    ImportIssue(
                        severity=IssueSeverity.ERROR,
                        code=_issue_code(field),
                        message=str(exc),
                        sheet_name=table.sheet_name,
                        row_number=source_row.row_number,
                        column_key=field.key,
                        source_header=source_header,
                        raw_value=raw_value,
                    )
                )

        _validate_time_order(table, schema, source_row, mapping, values, row_issues)
        _validate_duplicate_key(
            table,
            schema,
            source_row,
            values,
            row_issues,
            seen_keys,
        )
        issues.extend(row_issues)
        rows.append(
            NormalizedRow(
                sheet_name=table.sheet_name,
                row_number=source_row.row_number,
                values=immutable_mapping(values),
                raw_values=immutable_mapping(source_row.raw_values),
                unmapped_values=immutable_mapping(
                    {header: source_row.raw_values.get(header) for header in unmapped_headers}
                ),
                issues=tuple(row_issues),
            )
        )

    return MappingResult(
        rows=tuple(rows),
        issues=tuple(issues),
        applied_mapping=immutable_string_mapping(mapping),
        unmapped_headers=unmapped_headers,
        skipped_example_rows=tuple(skipped_examples),
    )


def _mapping_issues(
    table: SourceTable,
    schema: ImportSchema,
    mapping: Mapping[str, str],
) -> tuple[ImportIssue, ...]:
    fields = schema.fields_by_key
    issues: list[ImportIssue] = []
    used_sources: dict[str, str] = {}

    for target_key, source_header in mapping.items():
        if target_key not in fields:
            raise MappingConfigurationError(
                f"schema「{schema.name}」にcanonical key「{target_key}」はありません。"
            )
        if source_header not in table.headers:
            issues.append(
                ImportIssue(
                    IssueSeverity.ERROR,
                    "mapping_source_missing",
                    "指定された入力列が見つかりません。",
                    sheet_name=table.sheet_name,
                    row_number=1,
                    column_key=target_key,
                    source_header=source_header,
                )
            )
        previous_target = used_sources.get(source_header)
        if previous_target is not None:
            raise MappingConfigurationError(
                f"入力列「{source_header}」が「{previous_target}」と"
                f"「{target_key}」へ重複して割り当てられています。"
            )
        used_sources[source_header] = target_key

    for field in schema.fields:
        if field.required and field.key not in mapping:
            issues.append(
                ImportIssue(
                    IssueSeverity.ERROR,
                    "required_mapping_missing",
                    "必須列がマッピングされていません。",
                    sheet_name=table.sheet_name,
                    row_number=1,
                    column_key=field.key,
                )
            )
    return tuple(issues)


def _is_example_row(source_row: SourceRow, mapping: Mapping[str, str]) -> bool:
    source_header = mapping.get("example")
    if source_header is None:
        return False
    raw_value = source_row.raw_values.get(source_header)
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, int | float) and not isinstance(raw_value, bool):
        return raw_value == 1
    if isinstance(raw_value, str):
        return normalize_header(raw_value) in _EXAMPLE_MARKERS
    return False


def _normalize_value(raw_value: object, field: FieldSpec) -> object:
    if _is_blank(raw_value):
        if field.required:
            raise ValueError("必須値が空です。")
        return None
    if field.kind is FieldKind.TEXT:
        return _text_value(raw_value)
    if field.kind is FieldKind.DATE:
        return _date_value(raw_value)
    if field.kind is FieldKind.TIME:
        return _time_value(raw_value)
    if field.kind is FieldKind.AVAILABILITY:
        return _availability_value(raw_value)
    if field.kind is FieldKind.EXAMPLE_MARKER:
        return bool(_is_example_row(SourceRow(0, {"example": raw_value}), {"example": "example"}))
    raise AssertionError(f"未対応のFieldKindです: {field.kind}")


def _text_value(raw_value: object) -> str:
    if isinstance(raw_value, str):
        return raw_value.strip()
    if isinstance(raw_value, bool):
        return "はい" if raw_value else "いいえ"
    if isinstance(raw_value, float) and raw_value.is_integer():
        return str(int(raw_value))
    return str(raw_value).strip()


def _date_value(raw_value: object) -> date:
    if isinstance(raw_value, datetime):
        return raw_value.date()
    if isinstance(raw_value, date):
        return raw_value
    if isinstance(raw_value, str):
        value = unicodedata.normalize("NFKC", raw_value).strip()
        for date_format in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%Y年%m月%d日",
        ):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue
    raise ValueError("日付はYYYY-MM-DDまたはYYYY/MM/DD形式で入力してください。")


def _time_value(raw_value: object) -> time:
    if isinstance(raw_value, datetime):
        return raw_value.time().replace(microsecond=0)
    if isinstance(raw_value, time):
        return raw_value.replace(microsecond=0)
    if isinstance(raw_value, int | float) and not isinstance(raw_value, bool):
        numeric = float(raw_value)
        if math.isfinite(numeric) and 0 <= numeric < 1:
            seconds = round(numeric * 24 * 60 * 60)
            if seconds == 24 * 60 * 60:
                seconds = 0
            base = datetime.combine(date.min, time.min) + timedelta(seconds=seconds)
            return base.time()
    if isinstance(raw_value, str):
        value = unicodedata.normalize("NFKC", raw_value).strip()
        for time_format in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, time_format).time()
            except ValueError:
                continue
    raise ValueError("時刻はHH:MM形式で入力してください。")


def _availability_value(raw_value: object) -> int:
    if isinstance(raw_value, bool):
        raise ValueError("コマ値は0、1、2のいずれかで入力してください。")
    value: int | None = None
    if isinstance(raw_value, int):
        value = raw_value
    elif isinstance(raw_value, float) and raw_value.is_integer():
        value = int(raw_value)
    elif isinstance(raw_value, str):
        normalized = unicodedata.normalize("NFKC", raw_value).strip()
        if normalized in {"0", "1", "2"}:
            value = int(normalized)
    if value not in {0, 1, 2}:
        raise ValueError("コマ値は0、1、2のいずれかで入力してください。")
    return value


def _validate_time_order(
    table: SourceTable,
    schema: ImportSchema,
    source_row: SourceRow,
    mapping: Mapping[str, str],
    values: Mapping[str, object],
    issues: list[ImportIssue],
) -> None:
    if schema.ordered_time_fields is None:
        return
    start_key, end_key = schema.ordered_time_fields
    start_value = values.get(start_key)
    end_value = values.get(end_key)
    if isinstance(start_value, time) and isinstance(end_value, time) and start_value >= end_value:
        issues.append(
            ImportIssue(
                IssueSeverity.ERROR,
                "invalid_time_order",
                "開始時刻は終了時刻より前にしてください。",
                sheet_name=table.sheet_name,
                row_number=source_row.row_number,
                column_key=end_key,
                source_header=mapping.get(end_key),
                raw_value=source_row.raw_values.get(mapping.get(end_key, "")),
            )
        )


def _validate_duplicate_key(
    table: SourceTable,
    schema: ImportSchema,
    source_row: SourceRow,
    values: Mapping[str, object],
    issues: list[ImportIssue],
    seen_keys: dict[tuple[object, ...], int],
) -> None:
    if any(
        issue.severity is IssueSeverity.ERROR and issue.column_key in schema.unique_keys
        for issue in issues
    ):
        return
    key = tuple(values.get(field_key) for field_key in schema.unique_keys)
    if any(value is None for value in key):
        return
    previous_row = seen_keys.get(key)
    if previous_row is None:
        seen_keys[key] = source_row.row_number
        return
    issues.append(
        ImportIssue(
            IssueSeverity.ERROR,
            "duplicate_row",
            f"{previous_row}行目と同じキーが重複しています。",
            sheet_name=table.sheet_name,
            row_number=source_row.row_number,
            column_key=",".join(schema.unique_keys),
        )
    )


def _issue_code(field: FieldSpec) -> str:
    if field.kind is FieldKind.DATE:
        return "invalid_date"
    if field.kind is FieldKind.TIME:
        return "invalid_time"
    if field.kind is FieldKind.AVAILABILITY:
        return "invalid_availability"
    return "required_value_missing" if field.required else "invalid_value"


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
