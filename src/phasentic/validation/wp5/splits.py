"""Duplicate, equivalence, and split-leakage checks for WP-5 evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence


class SplitLeakageError(ValueError):
    """Raised when connected cases cross a declared evaluation partition."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _value(case: Any, key: str, default: Any = None) -> Any:
    if isinstance(case, Mapping):
        return case.get(key, default)
    return getattr(case, key, default)


def _values(case: Any, key: str) -> tuple[str, ...]:
    raw = _value(case, key, ())
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,) if raw.strip() else ()
    if isinstance(raw, (list, tuple, set)):
        return tuple(str(item) for item in raw if isinstance(item, str) and item.strip())
    return ()


def _families(case: Any) -> tuple[str, ...]:
    """Read only explicit equivalence-family declarations.

    Expected phase labels are truth data and cannot substitute for a
    documented structure-family identity.  A common reference ID alone is not
    evidence that two cases belong to the same structure family.
    """

    values = list(_values(case, "family_group_ids"))
    structure_family = _value(case, "structure_family")
    if isinstance(structure_family, str) and structure_family.strip():
        values.append(structure_family)
    return tuple(dict.fromkeys(values))


def _group(case: Any, key: str) -> str | None:
    raw = _value(case, key)
    if not isinstance(raw, str) or not raw.strip():
        return None
    if raw.strip().lower() in {"unknown", "unavailable", "synthetic", "unassigned", "tbd"}:
        return None
    return raw


def _case_id(case: Any) -> str:
    raw = _value(case, "case_id", _value(case, "id"))
    return str(raw) if raw is not None else ""


def _split(case: Any) -> str:
    raw = _value(case, "split", "unassigned")
    return str(raw) if raw is not None else "unassigned"


def _group_index(cases: Sequence[Any], extractor) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        case_id = _case_id(case)
        for identity in extractor(case):
            if case_id not in grouped[identity]:
                grouped[identity].append(case_id)
    return {key: tuple(values) for key, values in sorted(grouped.items()) if len(values) > 1}


def detect_duplicate_groups(cases: Sequence[Any]) -> dict[str, dict[str, tuple[str, ...]]]:
    """Return duplicate/equivalence groups without removing any case rows."""

    return {
        "exact_raw": _group_index(
            cases,
            lambda case: ((_value(case, "raw_sha256"),) if isinstance(_value(case, "raw_sha256"), str) else ()),
        ),
        "exact_normalized": _group_index(
            cases,
            lambda case: ((_value(case, "normalized_sha256"),) if isinstance(_value(case, "normalized_sha256"), str) else ()),
        ),
        "duplicate_group": _group_index(
            cases,
            lambda case: ((_group(case, "duplicate_group_id"),) if _group(case, "duplicate_group_id") else ()),
        ),
        "parent_group": _group_index(
            cases,
            lambda case: ((_group(case, "parent_group_id"),) if _group(case, "parent_group_id") else ()),
        ),
        "sample": _group_index(
            cases,
            lambda case: ((_group(case, "sample_id"),) if _group(case, "sample_id") else ()),
        ),
        "family": _group_index(
            cases,
            lambda case: _families(case),
        ),
        "acquisition": _group_index(
            cases,
            lambda case: ((_group(case, "acquisition_id"),) if _group(case, "acquisition_id") else ()),
        ),
    }


def _groups_by_split(cases: Sequence[Any], extractor) -> dict[str, dict[str, set[str]]]:
    result: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for case in cases:
        split = _split(case)
        for identity in extractor(case):
            result[identity][split].add(_case_id(case))
    return {identity: dict(partitions) for identity, partitions in result.items()}


def _cross_partition(groups: Mapping[str, Mapping[str, set[str]]]) -> list[tuple[str, tuple[str, ...]]]:
    conflicts: list[tuple[str, tuple[str, ...]]] = []
    for identity, partitions in groups.items():
        if len(partitions) > 1:
            conflicts.append((identity, tuple(sorted(partitions))))
    return sorted(conflicts)


def independent_group_counts(cases: Sequence[Any]) -> dict[str, int]:
    """Count independent sample/family/instrument groups with unknowns explicit."""

    def known_group(value: str) -> bool:
        normalized = value.strip().lower()
        return bool(normalized) and normalized not in {"unknown", "unavailable", "synthetic"} and not normalized.startswith("synthetic-")

    def count(key: str) -> int:
        values = {
            _group(case, key)
            for case in cases
            if _group(case, key) and known_group(str(_group(case, key)))
        }
        return len(values)

    return {
        "sample": count("sample_id"),
        "family": len({item for case in cases for item in _families(case) if known_group(item)}),
        "instrument": count("instrument_id"),
        "acquisition": count("acquisition_id"),
    }


def validate_split_assignments(
    cases: Sequence[Any],
    *,
    enforce_family: bool = True,
    enforce_instrument: bool = False,
    enforce_acquisition: bool = False,
    require_explicit_split: bool = False,
    minimum_independent_groups: int | None = None,
    minimum_group_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate partition membership and return an auditable split summary.

    Exact byte/normalized duplicates, sample/replicate parentage, and explicit
    acquisition groups are always checked.  Family and instrument constraints
    are selectable because the protocol has separate family-held-out,
    instrument-held-out, and joint-held-out tracks.
    """

    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not cases:
        raise SplitLeakageError("cases_empty", "split validation needs at least one case")
    case_ids = [_case_id(case) for case in cases]
    if any(not case_id for case_id in case_ids):
        raise SplitLeakageError("case_id_missing", "every case needs a case_id")
    if len(set(case_ids)) != len(case_ids):
        raise SplitLeakageError("case_id_duplicate", "case IDs must be unique")
    if require_explicit_split and any(_split(case) == "unassigned" for case in cases):
        raise SplitLeakageError("split_unassigned", "every frozen case needs an explicit partition")
    for case in cases:
        if _split(case) not in {"development", "calibration", "test", "unassigned"}:
            raise SplitLeakageError("split_invalid", f"case {_case_id(case)} has an unsupported split")

    groups = {
        "exact_raw": _groups_by_split(cases, lambda case: ((_value(case, "raw_sha256"),) if _value(case, "raw_sha256") else ())),
        "exact_normalized": _groups_by_split(cases, lambda case: ((_value(case, "normalized_sha256"),) if _value(case, "normalized_sha256") else ())),
        "duplicate_group": _groups_by_split(cases, lambda case: ((_group(case, "duplicate_group_id"),) if _group(case, "duplicate_group_id") else ())),
        "parent_group": _groups_by_split(cases, lambda case: ((_group(case, "parent_group_id"),) if _group(case, "parent_group_id") else ())),
        "sample": _groups_by_split(cases, lambda case: ((_group(case, "sample_id"),) if _group(case, "sample_id") else ())),
    }
    if enforce_family:
        groups["family"] = _groups_by_split(
            cases,
            lambda case: _families(case),
        )
    if enforce_instrument:
        groups["instrument"] = _groups_by_split(cases, lambda case: ((_group(case, "instrument_id"),) if _group(case, "instrument_id") else ()))
    if enforce_acquisition:
        groups["acquisition"] = _groups_by_split(cases, lambda case: ((_group(case, "acquisition_id"),) if _group(case, "acquisition_id") else ()))

    conflicts: list[dict[str, Any]] = []
    for group_type, indexed in groups.items():
        for identity, partitions in _cross_partition(indexed):
            conflicts.append({"group_type": group_type, "group_id": identity, "splits": list(partitions)})
    if conflicts:
        first = conflicts[0]
        code = "family_leakage" if first["group_type"] == "family" else "split_leakage"
        raise SplitLeakageError(code, f"{first['group_type']} group {first['group_id']} crosses {', '.join(first['splits'])}")

    counts = independent_group_counts(cases)
    status = "valid"
    if minimum_independent_groups is not None:
        if isinstance(minimum_independent_groups, bool) or minimum_independent_groups < 1:
            raise SplitLeakageError("minimum_groups_invalid", "minimum_independent_groups must be positive")
        dimensions = tuple(minimum_group_types or counts.keys())
        if any(dimension not in counts for dimension in dimensions):
            raise SplitLeakageError("minimum_group_type_invalid", "minimum_group_types contains an unknown dimension")
        if not dimensions:
            raise SplitLeakageError("minimum_group_type_invalid", "minimum_group_types cannot be empty")
        if min(counts[dimension] for dimension in dimensions) < minimum_independent_groups:
            status = "insufficient_groups"
    return {
        "status": status,
        "case_count": len(cases),
        "split_counts": {
            split: sum(_split(case) == split for case in cases)
            for split in ("development", "calibration", "test", "unassigned")
        },
        "independent_group_counts": counts,
        "duplicate_groups": detect_duplicate_groups(cases),
        "constraints": {
            "enforce_family": enforce_family,
            "enforce_instrument": enforce_instrument,
            "enforce_acquisition": enforce_acquisition,
        },
    }


def validate_split_track(cases: Sequence[Any], track: str, *, minimum_independent_groups: int = 3) -> dict[str, Any]:
    """Validate one declared generalization track with a named status."""

    if track not in {"family-held-out", "instrument-held-out", "joint-held-out"}:
        raise SplitLeakageError("track_invalid", f"unsupported split track: {track}")
    return validate_split_assignments(
        cases,
        enforce_family=track in {"family-held-out", "joint-held-out"},
        enforce_instrument=track in {"instrument-held-out", "joint-held-out"},
        require_explicit_split=True,
        minimum_independent_groups=minimum_independent_groups,
        minimum_group_types=(
            ("family",)
            if track == "family-held-out"
            else ("instrument",)
            if track == "instrument-held-out"
            else ("family", "instrument")
        ),
    )


__all__ = [
    "SplitLeakageError",
    "detect_duplicate_groups",
    "independent_group_counts",
    "validate_split_assignments",
    "validate_split_track",
]
