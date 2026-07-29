"""最適化snapshot codecだけが使う厳格なJSON helper。"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable, Mapping
from datetime import date, time
from typing import NoReturn, cast

type JsonObject = dict[str, object]

MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024


class SnapshotDecodeError(ValueError):
    """安全なsnapshot復元規則に適合しないJSON。"""


def encode_document(schema: str, version: int, data: JsonObject) -> str:
    return json.dumps(
        {"schema": schema, "schema_version": version, "data": data},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def decode_document(payload: str, schema: str, version: int) -> JsonObject:
    if len(payload.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise SnapshotDecodeError("最適化snapshotが許容サイズを超えています")
    try:
        raw = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise SnapshotDecodeError("最適化snapshotは有効なJSONではありません") from exc
    document = require_object(raw, "$")
    require_fields(document, {"schema", "schema_version", "data"}, "$")
    if require_str(document["schema"], "$.schema") != schema:
        raise SnapshotDecodeError("最適化snapshotのschemaが一致しません")
    if require_int(document["schema_version"], "$.schema_version") != version:
        raise SnapshotDecodeError("未対応の最適化snapshot versionです")
    return require_object(document["data"], "$.data")


def require_object(value: object, path: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SnapshotDecodeError(f"{path} はobjectである必要があります")
    return cast(JsonObject, value)


def require_fields(value: Mapping[str, object], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    fragments: list[str] = []
    if missing:
        fragments.append(f"不足={','.join(missing)}")
    if unknown:
        fragments.append(f"未知={','.join(unknown)}")
    raise SnapshotDecodeError(f"{path} のfieldが不正です ({'; '.join(fragments)})")


def require_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise SnapshotDecodeError(f"{path} はarrayである必要があります")
    return value


def require_str(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise SnapshotDecodeError(f"{path} はstringである必要があります")
    return value


def require_int(value: object, path: str) -> int:
    if type(value) is not int:
        raise SnapshotDecodeError(f"{path} はintegerである必要があります")
    return value


def require_float(value: object, path: str) -> float:
    if type(value) not in (int, float):
        raise SnapshotDecodeError(f"{path} はnumberである必要があります")
    result = float(cast(int | float, value))
    if not math.isfinite(result):
        raise SnapshotDecodeError(f"{path} は有限数である必要があります")
    return result


def require_bool(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise SnapshotDecodeError(f"{path} はbooleanである必要があります")
    return value


def require_optional_int(value: object, path: str) -> int | None:
    return None if value is None else require_int(value, path)


def require_optional_bool(value: object, path: str) -> bool | None:
    return None if value is None else require_bool(value, path)


def require_date(value: object, path: str) -> date:
    text = require_str(value, path)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise SnapshotDecodeError(f"{path} はISO日付である必要があります") from exc


def require_time(value: object, path: str) -> time:
    text = require_str(value, path)
    try:
        result = time.fromisoformat(text)
    except ValueError as exc:
        raise SnapshotDecodeError(f"{path} はISO時刻である必要があります") from exc
    if result.tzinfo is not None:
        raise SnapshotDecodeError(f"{path} にtimezoneは指定できません")
    return result


def map_array[T](
    value: object,
    path: str,
    factory: Callable[[object, str], T],
) -> tuple[T, ...]:
    return tuple(
        factory(item, f"{path}[{index}]") for index, item in enumerate(require_list(value, path))
    )


def int_tuple(value: object, path: str) -> tuple[int, ...]:
    return map_array(value, path, require_int)


def exact_int_tuple(value: object, path: str, length: int) -> tuple[int, ...]:
    result = int_tuple(value, path)
    if len(result) != length:
        raise SnapshotDecodeError(f"{path} は{length}要素である必要があります")
    return result


def exact_optional_int_tuple(
    value: object,
    path: str,
    length: int,
) -> tuple[int | None, ...]:
    result = map_array(value, path, require_optional_int)
    if len(result) != length:
        raise SnapshotDecodeError(f"{path} は{length}要素である必要があります")
    return result


def _unique_object(pairs: Iterable[tuple[str, object]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotDecodeError(f"JSON keyが重複しています: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise SnapshotDecodeError(f"非有限数は使用できません: {value}")


__all__ = [
    "JsonObject",
    "MAX_SNAPSHOT_BYTES",
    "SnapshotDecodeError",
    "decode_document",
    "encode_document",
    "exact_int_tuple",
    "exact_optional_int_tuple",
    "int_tuple",
    "map_array",
    "require_bool",
    "require_date",
    "require_fields",
    "require_float",
    "require_int",
    "require_list",
    "require_object",
    "require_optional_bool",
    "require_optional_int",
    "require_str",
    "require_time",
]
