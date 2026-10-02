"""Precursor Genome crosswalk and split controls.

The Precursor Genome ledger names phases with ICSD and space-group labels while
the production matcher reports POW_COD reference IDs.  This module is the
explicit boundary between those namespaces.  Candidate generation is useful
for review, but it never activates a mapping: only a ``reviewed_exact`` entry
can contribute to strict phase-presence truth.
"""

from __future__ import annotations

from contextlib import closing

from collections import Counter, defaultdict
from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping, Sequence


PRECROSSWALK_SCHEMA_VERSION = "precursor-powcod-crosswalk-1"
PRECROSSWALK_METHOD_VERSION = "explicit-review-boundary-2026-09-25"
PRECROSSWALK_SPLIT_VERSION = "stratified-sha256-v1"
PRECROSSWALK_TUNING_SCHEMA_VERSION = "precursor-native-tuning-1"

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_LABEL = re.compile(
    r"^(?P<formula>.+?)_(?P<space_group>\d+)_\(icsd_(?P<icsd>\d+)\)-(?P<variant>[^\s].*)$",
    re.IGNORECASE,
)
_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*(?:\.\d+)?)")
_GROUP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_STATUSES = {"reviewed_exact", "reviewed_family", "ambiguous", "unresolved"}


class PrecursorCrosswalkError(ValueError):
    """Raised when source labels or an explicit crosswalk are unsafe."""


@dataclass(frozen=True)
class PrecursorLabel:
    source_label: str
    formula: str
    normalized_formula: str
    space_group_number: int
    icsd_id: str
    variant: str


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PrecursorCrosswalkError(f"{field}_invalid: expected SHA-256")
    return value.lower()


def normalize_formula(formula: str) -> str:
    """Return a deterministic elemental composition key.

    Precursor labels are simple stoichiometric formulas.  POW_COD also has
    parenthesised and hydrated formulas; the tokenisation intentionally keeps
    this helper conservative and returns a key only when every character is
    understood.  A non-matching database formula is simply not suggested.
    """

    if not isinstance(formula, str) or not formula.strip():
        raise PrecursorCrosswalkError("formula_invalid: formula must be non-empty")
    text = formula.replace(" ", "").replace("·", ".")
    # Parentheses change stoichiometry and are not guessed here.
    if any(char in text for char in "()[]{}"):
        raise PrecursorCrosswalkError("formula_unsupported: grouped formula requires explicit review")
    pieces = list(_FORMULA_TOKEN.finditer(text))
    if not pieces or "".join(piece.group(0) for piece in pieces) != text:
        raise PrecursorCrosswalkError("formula_unparseable: unsupported formula syntax")
    totals: Counter[str] = Counter()
    for piece in pieces:
        element, raw_count = piece.groups()
        count = float(raw_count) if raw_count else 1.0
        if count <= 0 or not count.is_integer():
            raise PrecursorCrosswalkError("formula_non_integer: fractional stoichiometry needs explicit review")
        totals[element] += int(count)
    return "".join(f"{element}{count if count != 1 else ''}" for element, count in sorted(totals.items()))


def parse_precursor_label(source_label: str) -> PrecursorLabel:
    if not isinstance(source_label, str) or not source_label.strip():
        raise PrecursorCrosswalkError("label_unparseable: label must be non-empty")
    match = _LABEL.fullmatch(source_label.strip())
    if match is None:
        raise PrecursorCrosswalkError(f"label_unparseable: {source_label!r}")
    formula = match.group("formula").strip()
    try:
        normalized = normalize_formula(formula)
    except PrecursorCrosswalkError as exc:
        raise PrecursorCrosswalkError(f"label_unparseable: {source_label!r}: {exc}") from exc
    return PrecursorLabel(
        source_label=source_label.strip(),
        formula=formula,
        normalized_formula=normalized,
        space_group_number=int(match.group("space_group")),
        icsd_id=match.group("icsd"),
        variant=match.group("variant").strip(),
    )


def _entry_status(entry: Mapping[str, Any]) -> str:
    value = entry.get("mapping_status")
    if value not in _STATUSES:
        raise PrecursorCrosswalkError("mapping_status_invalid: expected explicit review status")
    return str(value)


def _identifiers(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise PrecursorCrosswalkError(f"{field}_invalid: expected a non-empty string array")
    output = list(dict.fromkeys(str(item).strip() for item in value))
    for item in output:
        if not _GROUP_ID.fullmatch(item):
            raise PrecursorCrosswalkError(f"{field}_invalid: unsafe identifier {item!r}")
    return output


def _validate_entry(label: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise PrecursorCrosswalkError(f"entry_invalid: {label}")
    status = _entry_status(raw)
    candidates = _identifiers(raw.get("candidate_reference_ids", []), "candidate_reference_ids")
    selected = _identifiers(raw.get("selected_reference_ids", []), "selected_reference_ids")
    canonical = raw.get("canonical_group_id")
    if canonical is not None and (not isinstance(canonical, str) or not _GROUP_ID.fullmatch(canonical)):
        raise PrecursorCrosswalkError("canonical_group_id_invalid: expected a stable identifier")
    parent = raw.get("parent_family_group_id")
    if parent is not None and (not isinstance(parent, str) or not _GROUP_ID.fullmatch(parent)):
        raise PrecursorCrosswalkError("parent_family_group_id_invalid: expected a stable identifier")
    if status == "reviewed_exact":
        if canonical is None or len(selected) != 1:
            raise PrecursorCrosswalkError("reviewed_exact_requires: one canonical group and one selected reference")
        if candidates and selected[0] not in candidates:
            raise PrecursorCrosswalkError("selected_reference_not_candidate: exact mapping is inconsistent")
    elif status == "reviewed_family":
        if canonical is not None or parent is None:
            raise PrecursorCrosswalkError("reviewed_family_requires: parent family and no strict canonical group")
        if selected:
            raise PrecursorCrosswalkError("reviewed_family_selected_reference: family mappings cannot select a COD entry")
    else:
        if canonical is not None or selected:
            raise PrecursorCrosswalkError(f"{status}_cannot_activate: unresolved mappings cannot select truth")
    if status == "ambiguous" and len(candidates) < 2:
        raise PrecursorCrosswalkError("ambiguous_requires: at least two candidate references")
    try:
        parsed = parse_precursor_label(label)
        parsed_fields = {
            "formula": parsed.formula,
            "normalized_formula": parsed.normalized_formula,
            "space_group_number": parsed.space_group_number,
            "icsd_id": parsed.icsd_id,
            "variant": parsed.variant,
        }
    except PrecursorCrosswalkError:
        if status != "unresolved":
            raise
        parsed_fields = {
            "formula": None,
            "normalized_formula": None,
            "space_group_number": None,
            "icsd_id": None,
            "variant": None,
        }
    return {
        "source_label": label,
        **parsed_fields,
        "mapping_status": status,
        "canonical_group_id": canonical,
        "parent_family_group_id": parent,
        "candidate_reference_ids": sorted(candidates),
        "selected_reference_ids": list(selected),
        "evidence": copy.deepcopy(raw.get("evidence", [])),
        "notes": str(raw.get("notes", "")) if raw.get("notes") is not None else "",
    }


def validate_precursor_crosswalk(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise PrecursorCrosswalkError("crosswalk_invalid: expected object")
    if payload.get("schema_version") != PRECROSSWALK_SCHEMA_VERSION:
        raise PrecursorCrosswalkError("schema_version_unsupported: precursor crosswalk")
    source_hash = _require_sha(payload.get("source_manifest_sha256"), "source_manifest_sha256")
    cache_hash = _require_sha(payload.get("powcod_cache_sha256"), "powcod_cache_sha256")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise PrecursorCrosswalkError("entries_empty: precursor crosswalk needs entries")
    normalized_entries = []
    labels: set[str] = set()
    canonical_groups: dict[str, str] = {}
    for raw in entries:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("source_label"), str):
            raise PrecursorCrosswalkError("entry_invalid: source_label is required")
        label = str(raw["source_label"])
        if label in labels:
            raise PrecursorCrosswalkError(f"entry_duplicate: {label}")
        labels.add(label)
        entry = _validate_entry(label, raw)
        group = entry.get("canonical_group_id")
        if group is not None and group in canonical_groups and canonical_groups[group] != label:
            raise PrecursorCrosswalkError(f"canonical_group_conflict: {group}")
        if group is not None:
            canonical_groups[group] = label
        normalized_entries.append(entry)
    normalized_entries.sort(key=lambda item: item["source_label"])
    result = {
        "schema_version": PRECROSSWALK_SCHEMA_VERSION,
        "method_version": str(payload.get("method_version", PRECROSSWALK_METHOD_VERSION)),
        "status": str(payload.get("status", "draft")),
        "source_manifest_sha256": source_hash,
        "powcod_cache_sha256": cache_hash,
        "entries": normalized_entries,
        "limitations": list(payload.get("limitations", [])),
    }
    if result["status"] not in {"draft", "frozen", "validated", "blocked"}:
        raise PrecursorCrosswalkError("status_invalid: precursor crosswalk")
    expected_hash = payload.get("content_sha256")
    computed = _sha256(result)
    if expected_hash is not None and _require_sha(expected_hash, "content_sha256") != computed:
        raise PrecursorCrosswalkError("content_hash_mismatch: precursor crosswalk")
    result["content_sha256"] = computed
    return result


def build_precursor_crosswalk(
    labels: Iterable[str],
    overrides: Mapping[str, Mapping[str, Any]],
    *,
    source_manifest_sha256: str,
    powcod_cache_sha256: str,
    status: str = "draft",
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    _require_sha(source_manifest_sha256, "source_manifest_sha256")
    _require_sha(powcod_cache_sha256, "powcod_cache_sha256")
    unique_labels = sorted(set(str(label) for label in labels))
    entries: list[dict[str, Any]] = []
    for label in unique_labels:
        raw = overrides.get(label, {"mapping_status": "unresolved"})
        entry = {"source_label": label, **dict(raw)}
        entries.append(entry)
    return validate_precursor_crosswalk(
        {
            "schema_version": PRECROSSWALK_SCHEMA_VERSION,
            "method_version": PRECROSSWALK_METHOD_VERSION,
            "status": status,
            "source_manifest_sha256": source_manifest_sha256,
            "powcod_cache_sha256": powcod_cache_sha256,
            "entries": entries,
            "limitations": list(limitations),
        }
    )


def _space_group_number(name: str | None) -> int | None:
    if not name:
        return None
    try:
        import gemmi  # type: ignore

        group = gemmi.find_spacegroup_by_name(str(name))
        return int(group.number) if group is not None else None
    except (ImportError, AttributeError, TypeError, ValueError):
        common = {"P 1": 1, "P -1": 2, "P 21/c": 14, "P n -3 m": 224, "F m -3 m": 225}
        return common.get(" ".join(str(name).split()))


def _phase_rows(cache: Path) -> list[tuple[str, str, str | None, str | None]]:
    if cache.is_symlink() or not cache.is_file():
        raise PrecursorCrosswalkError(f"powcod_cache_unavailable: {cache}")
    with closing(sqlite3.connect(cache)) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(phases)")}
        required = {"reference_id", "formula", "space_group"}
        if not required.issubset(columns):
            raise PrecursorCrosswalkError("powcod_cache_schema_invalid: phases columns missing")
        rows = connection.execute("SELECT reference_id, formula, space_group, cod_id FROM phases ORDER BY reference_id").fetchall()
    return [(str(reference), str(formula), str(space_group) if space_group is not None else None, str(cod) if cod is not None else None) for reference, formula, space_group, cod in rows]


def suggest_powcod_candidates(cache: str | Path, labels: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Generate review suggestions without activating any mapping."""

    rows = _phase_rows(Path(cache).expanduser().resolve())
    by_key: dict[tuple[str, int], list[str]] = defaultdict(list)
    for reference, formula, space_group, _cod_id in rows:
        try:
            key = (normalize_formula(formula), _space_group_number(space_group))
        except PrecursorCrosswalkError:
            continue
        if key[1] is not None:
            by_key[key].append(reference)
    output: dict[str, dict[str, Any]] = {}
    for source_label in sorted(set(str(item) for item in labels)):
        try:
            parsed = parse_precursor_label(source_label)
        except PrecursorCrosswalkError as exc:
            output[source_label] = {
                "mapping_status": "unresolved",
                "candidate_reference_ids": [],
                "suggestion_reason": str(exc),
            }
            continue
        candidates = sorted(set(by_key.get((parsed.normalized_formula, parsed.space_group_number), [])))
        output[source_label] = {
            "mapping_status": "ambiguous" if len(candidates) > 1 else "unresolved",
            "candidate_reference_ids": candidates,
            "suggestion_reason": "formula_and_space_group_unique_unreviewed" if len(candidates) == 1 else (
                "formula_and_space_group_multiple_candidates" if candidates else "no_formula_and_space_group_candidate"
            ),
        }
    return output


def _case_group(case: Mapping[str, Any]) -> str:
    for key in ("group_id", "parent_group_id", "sample_id", "case_id"):
        value = case.get(key)
        if isinstance(value, str) and value.strip():
            return value
    raise PrecursorCrosswalkError("case_group_missing: every case needs a stable group identifier")


def _case_stratum(case: Mapping[str, Any]) -> str:
    strata = case.get("strata")
    if isinstance(strata, Mapping):
        value = strata.get("phase_count")
        if value is not None:
            return str(value)
    metadata = case.get("metadata")
    if isinstance(metadata, Mapping):
        labels = metadata.get("source_expected_phase_groups") or metadata.get("phase_labels_source")
        if isinstance(labels, list):
            return str(len(labels))
    return "unknown"


def build_precursor_split(
    cases: Sequence[Mapping[str, Any]],
    *,
    training_count: int = 35,
    holdout_count: int = 15,
    seed: int = 0,
) -> dict[str, Any]:
    if training_count < 0 or holdout_count < 0 or training_count + holdout_count != len(cases):
        raise PrecursorCrosswalkError("split_count_invalid: counts must cover cases exactly")
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[_case_group(case)].append(case)
    group_rows = []
    for group_id, members in grouped.items():
        strata = Counter(_case_stratum(case) for case in members)
        if len(strata) != 1:
            raise PrecursorCrosswalkError(f"split_stratum_conflict: {group_id}")
        digest = hashlib.sha256(f"{seed}:{group_id}".encode("utf-8")).hexdigest()
        group_rows.append((digest, group_id, len(members), next(iter(strata))))
    by_stratum: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for digest, group_id, _size, stratum in group_rows:
        by_stratum[stratum].append((digest, group_id))
    total = len(cases)
    stratum_sizes = {key: sum(size for _digest, _group, size, stratum in group_rows if stratum == key) for key in by_stratum}
    raw_targets = {key: stratum_sizes[key] * holdout_count / total for key in by_stratum}
    targets = {key: int(value) for key, value in raw_targets.items()}
    remainder = holdout_count - sum(targets.values())
    for key in sorted(raw_targets, key=lambda item: (-(raw_targets[item] - targets[item]), item))[:remainder]:
        targets[key] += 1
    strata_keys = sorted(by_stratum)
    # Dynamic programming over case counts and per-stratum counts keeps whole
    # replicate/sample groups together while finding an exact requested
    # holdout size.  At a given state, the lexicographically smallest digest
    # sequence is retained, so the result is deterministic across processes.
    states: dict[tuple[int, tuple[int, ...]], tuple[str, ...]] = {(0, (0,) * len(strata_keys)): ()}
    stratum_index = {key: index for index, key in enumerate(strata_keys)}
    for digest, group_id, size, stratum in sorted(group_rows):
        next_states = dict(states)
        index = stratum_index[stratum]
        for (count, counts), selected in states.items():
            new_count = count + size
            if new_count > holdout_count:
                continue
            updated_counts = list(counts)
            updated_counts[index] += size
            state = (new_count, tuple(updated_counts))
            candidate = selected + (digest + "\x00" + group_id,)
            previous = next_states.get(state)
            if previous is None or candidate < previous:
                next_states[state] = candidate
        states = next_states
    choices = [
        (sum((counts[index] - targets[key]) ** 2 for index, key in enumerate(strata_keys)), selected, counts)
        for (count, counts), selected in states.items()
        if count == holdout_count
    ]
    if not choices:
        raise PrecursorCrosswalkError("split_count_unreachable: cannot construct exact holdout without splitting groups")
    _distance, selected_tokens, actual_counts = min(choices, key=lambda item: (item[0], item[1]))
    selected_groups = {token.split("\x00", 1)[1] for token in selected_tokens}
    case_by_group = {group_id: members for group_id, members in grouped.items()}
    holdout = sorted(str(case["case_id"]) for group_id in selected_groups for case in case_by_group[group_id])
    training = sorted(
        str(case["case_id"])
        for group_id, members in case_by_group.items()
        if group_id not in selected_groups
        for case in members
    )
    result = {
        "method_version": PRECROSSWALK_SPLIT_VERSION,
        "seed": seed,
        "training_case_count": len(training),
        "holdout_case_count": len(holdout),
        "training_case_ids": training,
        "holdout_case_ids": holdout,
        "stratum_targets": targets,
        "stratum_actual": {key: actual_counts[index] for index, key in enumerate(strata_keys)},
    }
    result["split_sha256"] = _sha256(result)
    return result


def enrich_precursor_case_manifest(
    cases: Sequence[Mapping[str, Any]],
    crosswalk: Mapping[str, Any],
    split: Mapping[str, Any],
) -> dict[str, Any]:
    checked = validate_precursor_crosswalk(crosswalk)
    entries = {entry["source_label"]: entry for entry in checked["entries"]}
    training = set(split.get("training_case_ids", []))
    holdout = set(split.get("holdout_case_ids", []))
    if training & holdout:
        raise PrecursorCrosswalkError("split_overlap: training and holdout case IDs overlap")
    output_cases: list[dict[str, Any]] = []
    for original in cases:
        case = copy.deepcopy(dict(original))
        metadata = case.get("metadata") if isinstance(case.get("metadata"), Mapping) else {}
        if str(metadata.get("cohort", "")) != "precursor-genome":
            output_cases.append(case)
            continue
        labels = metadata.get("source_expected_phase_groups")
        if not isinstance(labels, list):
            labels = [item.get("name") for item in metadata.get("phase_labels_source", []) if isinstance(item, Mapping)]
        labels = [str(item) for item in labels if isinstance(item, str) and item.strip()]
        mapped = [entries.get(label, {"source_label": label, "mapping_status": "unresolved"}) for label in labels]
        exact_groups = [entry["canonical_group_id"] for entry in mapped if entry.get("mapping_status") == "reviewed_exact" and entry.get("canonical_group_id")]
        source_weights = metadata.get("expected_phase_weights")
        expected_group_weights: dict[str, float] = {}
        if isinstance(source_weights, Mapping):
            for entry in mapped:
                label = entry.get("source_label")
                group = entry.get("canonical_group_id")
                weight = source_weights.get(label) if isinstance(label, str) else None
                if entry.get("mapping_status") == "reviewed_exact" and group and isinstance(weight, (int, float)) and not isinstance(weight, bool):
                    expected_group_weights[str(group)] = expected_group_weights.get(str(group), 0.0) + float(weight)
        parent_groups = sorted({entry["parent_family_group_id"] for entry in mapped if entry.get("parent_family_group_id")})
        unresolved = [entry["source_label"] for entry in mapped if entry.get("mapping_status") not in {"reviewed_exact"}]
        case["expected_phase_groups"] = list(dict.fromkeys(exact_groups))
        case["expected_parent_family_groups"] = parent_groups
        case["uncertain_phase_groups"] = unresolved
        case["label_completeness"] = "complete" if labels and len(unresolved) == 0 else "incomplete"
        case["label_provenance"] = list(dict.fromkeys(list(case.get("label_provenance", [])) + [
            f"Precursor/POW_COD crosswalk {checked['content_sha256']}; only reviewed_exact entries activate strict truth."
        ]))
        metadata = dict(metadata)
        metadata["crosswalk_sha256"] = checked["content_sha256"]
        metadata["crosswalk_method_version"] = checked["method_version"]
        metadata["crosswalk_entries"] = [
            {
                "source_label": entry["source_label"],
                "mapping_status": entry.get("mapping_status"),
                "candidate_reference_ids": list(entry.get("candidate_reference_ids", [])),
                "canonical_group_id": entry.get("canonical_group_id"),
                "parent_family_group_id": entry.get("parent_family_group_id"),
            }
            for entry in mapped
        ]
        metadata["unresolved_source_labels"] = unresolved
        metadata["reference_resolution"] = "reviewed_exact" if case["label_completeness"] == "complete" else "partial_crosswalk"
        if expected_group_weights and not unresolved:
            metadata["expected_phase_group_weights"] = dict(sorted(expected_group_weights.items()))
            metadata["source_truth_status"] = "crosswalked"
        else:
            metadata["source_truth_status"] = "accepted_human_labels_pending_powcod_crosswalk"
        case["metadata"] = metadata
        case_id = str(case.get("case_id", ""))
        if case_id in training:
            case["split"] = "development"
            case.setdefault("strata", {})["precursor_split"] = "training"
        elif case_id in holdout:
            case["split"] = "test"
            case.setdefault("strata", {})["precursor_split"] = "holdout"
        else:
            raise PrecursorCrosswalkError(f"split_case_missing: {case_id}")
        output_cases.append(case)
    return {
        "cases": output_cases,
        "crosswalk_sha256": checked["content_sha256"],
        "split_sha256": split.get("split_sha256") or _sha256(split),
        "strict_truth_case_count": sum(1 for case in output_cases if case.get("metadata", {}).get("cohort") == "precursor-genome" and case.get("label_completeness") == "complete"),
    }


def native_tuning_score(metrics: Mapping[str, Any]) -> tuple[float, float, float, float]:
    """Return a deterministic, DARA-independent tuning objective.

    The tuple is ordered for maximisation: strict recovery, family recovery,
    candidate recall at 5, then lower false-support rate.  Null rates score
    zero and remain visible in the persisted manifest.
    """

    def rate(path: Sequence[str], default: float = 0.0) -> float:
        value: Any = metrics
        for key in path:
            if not isinstance(value, Mapping):
                return default
            value = value.get(key)
        raw = value.get("rate") if isinstance(value, Mapping) else value
        return float(raw) if isinstance(raw, (int, float)) else default

    strict = rate(("exact_set",))
    family = rate(("family_recovery",))
    recall = rate(("candidate_recall", "5"))
    false_support = rate(("false_support",))
    return (strict, family, recall, -false_support)


def select_native_parameters(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise PrecursorCrosswalkError("tuning_candidates_empty: native parameter candidates required")
    ranked = []
    for candidate in candidates:
        if str(candidate.get("comparator", "native")) != "native":
            raise PrecursorCrosswalkError("tuning_comparator_forbidden: DARA cannot control parameters")
        settings = candidate.get("settings")
        metrics = candidate.get("metrics")
        if not isinstance(settings, Mapping) or not isinstance(metrics, Mapping):
            raise PrecursorCrosswalkError("tuning_candidate_invalid: settings and metrics required")
        ranked.append((native_tuning_score(metrics), _sha256(settings), candidate))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, settings_hash, winner = ranked[0]
    result = {
        "schema_version": PRECROSSWALK_TUNING_SCHEMA_VERSION,
        "comparator": "native",
        "objective": ["strict_equivalence_group_recovery", "parent_family_recovery", "candidate_recall_at_5", "negative_false_support_minimized"],
        "selected_settings": copy.deepcopy(dict(winner["settings"])),
        "selected_settings_sha256": settings_hash,
        "selected_score": list(score),
        "candidate_count": len(candidates),
        "candidates": [
            {"settings_sha256": _sha256(item["settings"]), "score": list(native_tuning_score(item["metrics"]))}
            for item in candidates
        ],
        "limitations": [
            "Selection is valid only for the declared Precursor training split and crosswalk hash.",
            "No DARA result may select or modify native settings.",
        ],
    }
    result["content_sha256"] = _sha256(result)
    return result


def freeze_native_parameter_manifest(
    candidates: Sequence[Mapping[str, Any]],
    *,
    protocol_id: str,
    protocol_sha256: str,
    crosswalk_sha256: str,
    split: Mapping[str, Any],
    strict_truth_case_count: int,
) -> dict[str, Any]:
    """Freeze a native-only tuning result after the reference-truth gate."""

    if not isinstance(protocol_id, str) or not protocol_id.strip():
        raise PrecursorCrosswalkError("protocol_id_invalid: native parameter manifest")
    _require_sha(protocol_sha256, "protocol_sha256")
    _require_sha(crosswalk_sha256, "crosswalk_sha256")
    if isinstance(strict_truth_case_count, bool) or strict_truth_case_count < 1:
        raise PrecursorCrosswalkError(
            "training_truth_unavailable: at least one complete Precursor reference case is required before freezing parameters"
        )
    training_ids = split.get("training_case_ids")
    holdout_ids = split.get("holdout_case_ids")
    if not isinstance(training_ids, list) or not isinstance(holdout_ids, list):
        raise PrecursorCrosswalkError("split_receipt_invalid: training and holdout IDs are required")
    if set(training_ids) & set(holdout_ids):
        raise PrecursorCrosswalkError("split_overlap: native parameter manifest")
    selected = select_native_parameters(candidates)
    result = {
        **selected,
        "status": "frozen",
        "protocol_id": protocol_id,
        "protocol_sha256": protocol_sha256.lower(),
        "crosswalk_sha256": crosswalk_sha256.lower(),
        "split_sha256": str(split.get("split_sha256") or _sha256(split)),
        "training_case_ids": sorted(str(item) for item in training_ids),
        "holdout_case_ids": sorted(str(item) for item in holdout_ids),
        "training_strict_truth_case_count": int(strict_truth_case_count),
        "evaluation_policy": "evaluate held-out Precursor and external cohorts only after this manifest is frozen",
    }
    result["content_sha256"] = _sha256(result)
    return result


__all__ = [
    "PRECROSSWALK_SCHEMA_VERSION",
    "PRECROSSWALK_METHOD_VERSION",
    "PRECROSSWALK_SPLIT_VERSION",
    "PRECROSSWALK_TUNING_SCHEMA_VERSION",
    "PrecursorCrosswalkError",
    "PrecursorLabel",
    "normalize_formula",
    "parse_precursor_label",
    "build_precursor_crosswalk",
    "validate_precursor_crosswalk",
    "suggest_powcod_candidates",
    "build_precursor_split",
    "enrich_precursor_case_manifest",
    "native_tuning_score",
    "select_native_parameters",
    "freeze_native_parameter_manifest",
]
