"""取込み前確認で使う行・セル単位の差分契約。"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from summer_scheduler.infrastructure.importing.contracts import NormalizedRow


class DiffStatus(StrEnum):
    """既存行に対する取込み候補の状態。"""

    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    DELETION_CANDIDATE = "deletion_candidate"


@dataclass(frozen=True, slots=True)
class CellDiff:
    """1セルの変更前後。"""

    field: str
    before: object
    after: object


@dataclass(frozen=True, slots=True)
class RowDiff:
    """業務キー単位の差分。削除候補は自動反映しない。"""

    key: Mapping[str, object]
    status: DiffStatus
    before: Mapping[str, object] | None
    after: Mapping[str, object] | None
    cells: tuple[CellDiff, ...]


@dataclass(frozen=True, slots=True)
class DiffResult:
    """差分一覧と状態別件数。"""

    rows: tuple[RowDiff, ...]

    @property
    def counts(self) -> Mapping[DiffStatus, int]:
        """状態別件数を読取り専用で返す。"""
        counts = {status: 0 for status in DiffStatus}
        for row in self.rows:
            counts[row.status] += 1
        return MappingProxyType(counts)


class DiffBuildError(ValueError):
    """差分比較の業務キーが不正または重複している場合の例外。"""


def build_cell_diff(
    existing_rows: Iterable[Mapping[str, object] | NormalizedRow],
    incoming_rows: Iterable[Mapping[str, object] | NormalizedRow],
    *,
    key_fields: Sequence[str],
    value_fields: Sequence[str],
    include_deletion_candidates: bool = True,
) -> DiffResult:
    """業務キーで照合し、追加・変更・同一・削除候補とセル差分を作る。"""
    keys = tuple(key_fields)
    fields = tuple(value_fields)
    if not keys:
        raise DiffBuildError("key_fieldsを1件以上指定してください。")
    if len(keys) != len(set(keys)):
        raise DiffBuildError("key_fieldsが重複しています。")
    if len(fields) != len(set(fields)):
        raise DiffBuildError("value_fieldsが重複しています。")

    existing = _index_rows(existing_rows, keys, "既存データ")
    incoming = _index_rows(incoming_rows, keys, "取込みデータ")
    diffs: list[RowDiff] = []

    for identity, incoming_values in incoming.items():
        key = _key_mapping(keys, identity)
        existing_values = existing.get(identity)
        if existing_values is None:
            diffs.append(
                RowDiff(
                    key,
                    DiffStatus.ADDED,
                    None,
                    _immutable_values(incoming_values),
                    tuple(CellDiff(field, None, incoming_values.get(field)) for field in fields),
                )
            )
            continue
        cells = tuple(
            CellDiff(
                field,
                existing_values.get(field),
                incoming_values.get(field),
            )
            for field in fields
            if existing_values.get(field) != incoming_values.get(field)
        )
        diffs.append(
            RowDiff(
                key,
                DiffStatus.CHANGED if cells else DiffStatus.UNCHANGED,
                _immutable_values(existing_values),
                _immutable_values(incoming_values),
                cells,
            )
        )

    if include_deletion_candidates:
        for identity, existing_values in existing.items():
            if identity in incoming:
                continue
            diffs.append(
                RowDiff(
                    _key_mapping(keys, identity),
                    DiffStatus.DELETION_CANDIDATE,
                    _immutable_values(existing_values),
                    None,
                    tuple(CellDiff(field, existing_values.get(field), None) for field in fields),
                )
            )
    return DiffResult(tuple(diffs))


def _index_rows(
    rows: Iterable[Mapping[str, object] | NormalizedRow],
    key_fields: tuple[str, ...],
    label: str,
) -> dict[tuple[Hashable, ...], Mapping[str, object]]:
    indexed: dict[tuple[Hashable, ...], Mapping[str, object]] = {}
    for row in rows:
        values = row.values if isinstance(row, NormalizedRow) else row
        identity = _identity(values, key_fields)
        if identity in indexed:
            shown = " / ".join(str(value) for value in identity)
            raise DiffBuildError(f"{label}の業務キーが重複しています: {shown}")
        indexed[identity] = values
    return indexed


def _identity(
    values: Mapping[str, object],
    key_fields: tuple[str, ...],
) -> tuple[Hashable, ...]:
    identity: list[Hashable] = []
    for field in key_fields:
        if field not in values or values[field] is None:
            raise DiffBuildError(f"業務キー「{field}」が空です。")
        value = values[field]
        if not isinstance(value, Hashable):
            raise DiffBuildError(f"業務キー「{field}」は比較可能な値ではありません。")
        identity.append(value)
    return tuple(identity)


def _key_mapping(
    key_fields: tuple[str, ...],
    identity: tuple[Hashable, ...],
) -> Mapping[str, object]:
    return MappingProxyType(dict(zip(key_fields, identity, strict=True)))


def _immutable_values(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))
