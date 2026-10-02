"""Independent WP-5 evaluation metrics.

The production matcher produces a report for one scan at a time.  This module
deliberately operates on persisted, JSON-like case rows instead of importing
the matcher or trusting a summary produced by a runner.  That separation is
what lets the closure validator recompute denominators and detect dropped or
rewritten rows.

Rows are intentionally duck-typed so that the evaluator can consume the
versioned WP-5 result contract without making the metric implementation depend
on the contract dataclasses.  The canonical fields are ``case_id``,
``expected_phase_groups``, ``top_candidates``, ``selected_phase_groups``,
``supported_phase_groups``, ``label_completeness`` and ``evaluation_status``.
Legacy aliases used by WP-4 are accepted as input, but all output uses the
WP-5 names and explicit null-denominator reasons.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
import math
import random
import json
from typing import Any, TypeAlias


MetricValue: TypeAlias = dict[str, int | float | str | None]
MetricFunction: TypeAlias = Callable[[Sequence[Mapping[str, Any]]], Any]


class MetricValidationError(ValueError):
    """Raised when metric input cannot be interpreted without guessing."""


_COMPLETE_LABELS = {"complete", "known", "certified", "expert_review"}
_MISSING_LIBRARY = {"missing_library", "missing-reference", "missing_reference"}
_EXCLUDED = {
    "excluded",
    "ineligible",
    "unavailable",
    "rights_pending",
    "missing_metadata",
    "missing_source",
    "blocked",
    "not_eligible",
}
_FAILURE_STATUSES = {
    "failed",
    "parse_failed",
    "calibration_failed",
    "analysis_failed",
    "error",
}
_DECISIONS = ("supported", "tentative", "ambiguous", "unresolved", "abstained")


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _canonical_row(row: Mapping[str, Any]) -> str:
    """Return a deterministic tie-breaker for rows lacking a case ID."""

    try:
        return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        return repr(sorted((str(key), repr(value)) for key, value in row.items()))


def _normalise_values(value: Any) -> tuple[Any, ...]:
    """Return a stable tuple for a field that should contain identifiers."""

    if value is None:
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def _group_id(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in (
            "equivalence_group_id",
            "equivalence_group",
            "structure_family",
            "family_group_id",
            "reference_id",
            "phase_id",
            "id",
        ):
            candidate = _as_text(value.get(key))
            if candidate:
                return candidate
        return None
    return _as_text(value)


def _unique_groups(value: Any) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for item in _normalise_values(value):
        identifier = _group_id(item)
        if identifier and identifier not in seen:
            seen.add(identifier)
            output.append(identifier)
    return tuple(output)


def _field(row: Mapping[str, Any], *names: str) -> tuple[bool, Any]:
    for name in names:
        if name in row:
            return True, row[name]
    return False, None


def _expected(row: Mapping[str, Any]) -> tuple[str, ...] | None:
    present, value = _field(
        row,
        "expected_phase_groups",
        "expected_phase_ids",
        "expected_phases",
        "phases",
    )
    return _unique_groups(value) if present else None


def _label_complete(row: Mapping[str, Any], expected: tuple[str, ...] | None) -> bool:
    explicit = row.get("truth_complete")
    if isinstance(explicit, bool):
        return explicit
    explicit = row.get("labels_complete")
    if isinstance(explicit, bool):
        return explicit
    for key in ("label_completeness", "truth_status", "label_status"):
        value = _as_text(row.get(key))
        if value:
            return value.lower() in _COMPLETE_LABELS
    # An explicit expected field is the old result-row contract.  It is safe
    # to keep accepting it as complete for backwards-compatible re-evaluation;
    # new WP-5 manifests always carry label_completeness explicitly.
    return expected is not None


def _status(row: Mapping[str, Any]) -> str:
    value = row.get("evaluation_status", row.get("status", "eligible"))
    return _as_text(value).lower() if _as_text(value) else "eligible"


def _missing_library(row: Mapping[str, Any]) -> bool:
    status = _status(row)
    kind = _as_text(row.get("kind"))
    return status in _MISSING_LIBRARY or (kind or "").lower() in _MISSING_LIBRARY


def _eligible(row: Mapping[str, Any], expected: tuple[str, ...] | None) -> bool:
    if expected is None or not _label_complete(row, expected):
        return False
    return _status(row) not in _EXCLUDED and not _missing_library(row)


def _failure(row: Mapping[str, Any]) -> bool:
    if row.get("error") not in (None, "", False):
        return True
    return _status(row) in _FAILURE_STATUSES


def _candidates(row: Mapping[str, Any]) -> tuple[str, ...]:
    present, value = _field(row, "top_candidates", "candidates", "candidate_groups")
    if not present:
        return ()
    return _unique_groups(value)


def _selected(row: Mapping[str, Any]) -> tuple[str, ...]:
    present, value = _field(
        row,
        "selected_phase_groups",
        "selected_phase_ids",
        "mixture_selected_components",
        "selection",
    )
    return _unique_groups(value) if present else ()


def _family_groups(row: Mapping[str, Any], *, expected: bool) -> tuple[str, ...]:
    names = (
        ("expected_parent_family_groups", "expected_family_groups", "expected_parent_groups")
        if expected
        else ("selected_parent_family_groups", "selected_family_groups", "selected_parent_groups")
    )
    present, value = _field(row, *names)
    if present:
        return _unique_groups(value)
    return ()


def _supported(row: Mapping[str, Any]) -> tuple[str, ...]:
    present, value = _field(row, "supported_phase_groups", "supported_phase_ids")
    if present:
        return _unique_groups(value)
    raw = row.get("top_candidates", row.get("candidates", ()))
    output: list[str] = []
    for candidate in _normalise_values(raw):
        if isinstance(candidate, Mapping) and (_as_text(candidate.get("status")) or "").lower() == "supported":
            identifier = _group_id(candidate)
            if identifier and identifier not in output:
                output.append(identifier)
    return tuple(output)


def _tentative(row: Mapping[str, Any]) -> tuple[str, ...]:
    present, value = _field(row, "tentative_phase_groups", "tentative_phase_ids")
    if present:
        return _unique_groups(value)
    raw = row.get("top_candidates", row.get("candidates", ()))
    output: list[str] = []
    for candidate in _normalise_values(raw):
        if isinstance(candidate, Mapping) and (_as_text(candidate.get("status")) or "").lower() == "tentative":
            identifier = _group_id(candidate)
            if identifier and identifier not in output:
                output.append(identifier)
    return tuple(output)


def _metric(numerator: int, denominator: int, reason: str | None = None) -> MetricValue:
    if denominator == 0:
        return {
            "numerator": int(numerator),
            "denominator": 0,
            "rate": None,
            "undefined_reason": reason or "zero denominator",
        }
    if numerator < 0 or numerator > denominator:
        raise MetricValidationError(
            f"metric numerator {numerator} is outside denominator {denominator}"
        )
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": float(numerator / denominator),
        "undefined_reason": None,
    }


def _metric_from_values(values: list[tuple[set[str], set[str]]], *, empty_reason: str) -> MetricValue:
    numerator = sum(len(expected & observed) for expected, observed in values)
    denominator = sum(len(expected) for expected, _ in values)
    return _metric(numerator, denominator, empty_reason)


def evaluate_phase_agreement(
    expected: Mapping[str, float] | Sequence[str],
    predicted: Sequence[str],
    *,
    top_n: int = 5,
    minimum_ratio: float = 0.80,
) -> dict[str, Any]:
    """Evaluate the bounded phase-agreement rule used by the Precursor campaign.

    ``expected`` may be a phase-to-weight mapping from a reviewed refinement or
    an ordered sequence of canonical phase groups.  Recall is measured against
    the ``top_n`` reference phases (five by default); precision uses every
    reference phase so a prediction outside the selected top-N is not treated
    as an incorrect phase.
    Duplicate identifiers are collapsed before scoring.  An empty or invalid
    reference is never a pass.
    """

    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise MetricValidationError("top_n must be a positive integer")
    if isinstance(minimum_ratio, bool) or not isinstance(minimum_ratio, (int, float)):
        raise MetricValidationError("minimum_ratio must be numeric")
    ratio = float(minimum_ratio)
    if not math.isfinite(ratio) or not 0.0 < ratio <= 1.0:
        raise MetricValidationError("minimum_ratio must be in (0, 1]")
    if isinstance(expected, Mapping):
        weighted: list[tuple[str, float]] = []
        for raw_identifier, raw_weight in expected.items():
            identifier = _as_text(raw_identifier)
            if not identifier or isinstance(raw_weight, bool) or not isinstance(raw_weight, (int, float)):
                raise MetricValidationError("expected phase weights must contain non-empty identifiers and numeric weights")
            weight = float(raw_weight)
            if not math.isfinite(weight) or weight < 0.0:
                raise MetricValidationError("expected phase weights must be finite and non-negative")
            weighted.append((identifier, weight))
        weighted.sort(key=lambda item: (-item[1], item[0]))
        all_reference = tuple(identifier for identifier, _ in weighted)
        top_reference = all_reference[:top_n]
    else:
        if isinstance(expected, (str, bytes)):
            raise MetricValidationError("expected phases must be a sequence of identifiers")
        all_reference = tuple(dict.fromkeys(identifier for identifier in (_as_text(item) for item in expected) if identifier))
        top_reference = all_reference[:top_n]
    if isinstance(predicted, (str, bytes)):
        raise MetricValidationError("predicted phases must be a sequence of identifiers")
    predicted_groups = tuple(dict.fromkeys(identifier for identifier in (_as_text(item) for item in predicted) if identifier))
    if not top_reference:
        return {
            "status": "insufficient_truth",
            "passed": False,
            "reference_count": 0,
            "reference_total_count": len(all_reference),
            "predicted_count": len(predicted_groups),
            "matched_count": 0,
            "recall": None,
            "precision": None,
            "top_reference_groups": [],
            "matched_groups": [],
            "missing_groups": [],
            "unexpected_groups": list(predicted_groups),
        }
    all_reference_set = set(all_reference)
    top_reference_set = set(top_reference)
    predicted_set = set(predicted_groups)
    matched = top_reference_set & predicted_set
    correct_predictions = all_reference_set & predicted_set
    recall = len(matched) / len(top_reference_set)
    precision = len(correct_predictions) / len(predicted_set) if predicted_set else 0.0
    passed = recall >= ratio and precision >= ratio
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "reference_count": len(top_reference),
        "reference_total_count": len(all_reference),
        "predicted_count": len(predicted_groups),
        "matched_count": len(matched),
        "recall": recall,
        "precision": precision,
        "minimum_ratio": ratio,
        "top_reference_groups": list(top_reference),
        "matched_groups": sorted(matched),
        "missing_groups": sorted(top_reference_set - predicted_set),
        "unexpected_groups": sorted(predicted_set - all_reference_set),
    }


def _weighted_metric(numerator: float, denominator: int, reason: str) -> MetricValue:
    if denominator == 0:
        return {"numerator": 0.0, "denominator": 0, "rate": None, "undefined_reason": reason}
    return {
        "numerator": float(numerator),
        "denominator": int(denominator),
        "rate": float(numerator / denominator),
        "undefined_reason": None,
    }


def _base_metrics(rows: Sequence[Mapping[str, Any]], top_k: Sequence[int]) -> dict[str, Any]:
    if isinstance(rows, (str, bytes)):
        raise MetricValidationError("bootstrap rows must be a sequence of objects")
    materialized = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise MetricValidationError(f"bootstrap row {index} must be an object")
        materialized.append(dict(row))
    decorated = [(row, _expected(row)) for row in materialized]
    eligible = [(row, expected) for row, expected in decorated if _eligible(row, expected)]
    complete = [
        (row, expected)
        for row, expected in decorated
        if expected is not None and _label_complete(row, expected) and not _missing_library(row)
        and _status(row) not in _EXCLUDED
    ]
    missing_library = [row for row, _ in decorated if _missing_library(row)]
    incomplete = [
        row
        for row, expected in decorated
        if expected is not None and not _label_complete(row, expected) and not _missing_library(row)
    ]

    candidate_recall: dict[str, MetricValue] = {}
    for k in top_k:
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise MetricValidationError("top_k values must be positive integers")
        values = [
            (set(expected), set(_candidates(row)[:k]))
            for row, expected in eligible
            if expected
        ]
        candidate_recall[str(k)] = _metric_from_values(
            values,
            empty_reason="no complete eligible positive labels",
        )

    selected_pairs = [(set(expected), set(_selected(row))) for row, expected in eligible]
    selected_hits = sum(len(expected & selected) for expected, selected in selected_pairs)
    selected_expected = sum(len(expected) for expected, _ in selected_pairs)
    selected_predicted = sum(len(selected) for _, selected in selected_pairs)
    selection = {
        "recall": _metric(selected_hits, selected_expected, "no complete eligible positive labels"),
        "precision": _metric(
            selected_hits,
            selected_predicted,
            "no selected phase groups",
        ),
        "predicted_member_count": selected_predicted,
    }

    exact_numerator = sum(expected == selected for expected, selected in selected_pairs)
    exact_set = _metric(exact_numerator, len(selected_pairs), "no complete eligible labels")

    family_scores: list[tuple[float, int]] = []
    for row, expected in eligible:
        expected_groups = _family_groups(row, expected=True)
        selected_groups = _family_groups(row, expected=False)
        if not expected_groups:
            continue
        exact_groups = set(_selected(row))
        expected_exact = set(expected)
        score = 0.0
        for family in expected_groups:
            if family in selected_groups:
                score += 0.5
        # Exact canonical matches retain full credit in this separate metric.
        score += sum(0.5 for group in expected_exact if group in exact_groups)
        family_scores.append((min(score, float(len(expected_groups))), len(expected_groups)))
    family_recovery = _weighted_metric(
        sum(score for score, _ in family_scores),
        sum(denominator for _, denominator in family_scores),
        "no complete labels with parent-family mappings",
    )

    supported_pairs = [(set(_supported(row)), set(expected)) for row, expected in complete]
    false_supported = sum(len(supported - expected) for supported, expected in supported_pairs)
    all_supported = sum(len(supported) for supported, _ in supported_pairs)
    supported_phase_error = _metric(
        false_supported,
        all_supported,
        "no supported phase groups with complete truth labels",
    )

    selection_pairs = [(set(_selected(row)), set(expected)) for row, expected in complete]
    false_selected = sum(len(selected - expected) for selected, expected in selection_pairs)
    all_selected = sum(len(selected) for selected, _ in selection_pairs)
    selection_error = _metric(
        false_selected,
        all_selected,
        "no selected phase groups with complete truth labels",
    )
    tentative_pairs = [(set(_tentative(row)), set(expected)) for row, expected in complete]
    false_tentative = sum(len(selected - expected) for selected, expected in tentative_pairs)
    all_tentative = sum(len(selected) for selected, _ in tentative_pairs)
    tentative_error = _metric(
        false_tentative,
        all_tentative,
        "no tentative phase groups with complete truth labels",
    )

    negatives = [row for row, expected in complete if not expected]
    negative_with_support = sum(bool(_supported(row)) for row in negatives)
    negative_support = _metric(
        negative_with_support,
        len(negatives),
        "no complete negative controls",
    )

    eligible_for_decision = [row for row, _ in eligible]
    decision_counts = {
        decision: sum(_as_text(row.get("decision")) == decision for row in eligible_for_decision)
        for decision in _DECISIONS
    }
    decision_rates = {
        decision: _metric(
            decision_counts[decision],
            len(eligible_for_decision),
            "no complete eligible labels",
        )
        for decision in _DECISIONS
    }
    failures = sum(_failure(row) for row in materialized)
    failure_rate = _metric(failures, len(materialized), "no result rows")

    # Preserve explicit phase-count and reference-coverage denominators.  A
    # missing-library case is evidence about coverage, not a failed prediction.
    reference_coverage = _metric(
        len(eligible),
        len(eligible) + len(missing_library),
        "no eligible or missing-library cases",
    )

    return {
        "case_count": len(materialized),
        "eligible_case_count": len(eligible),
        "complete_label_case_count": len(complete),
        "label_incomplete_case_count": len(incomplete),
        "missing_library_case_count": len(missing_library),
        "failure_count": failures,
        "failure_rate": failure_rate,
        "candidate_recall": candidate_recall,
        # Names retained as explicit aliases for WP-4 closure consumers and
        # manuscript tables.  They point to the same independently computed
        # values; no second aggregation is performed.
        "top_k_recall": candidate_recall,
        "selection": selection,
        "selected_set": selection,
        "exact_set": exact_set,
        "exact_set_recovery": exact_set,
        "family_recovery": family_recovery,
        "supported_phase_error": supported_phase_error,
        "false_support": supported_phase_error,
        "selection_error": selection_error,
        "tentative_error": tentative_error,
        "negative_support": negative_support,
        "decision_counts": decision_counts,
        "abstention": {
            "ambiguous": decision_rates["ambiguous"],
            "unresolved": decision_rates["unresolved"],
            "abstained": decision_rates["abstained"],
            "any_abstention": _metric(
                decision_counts["ambiguous"] + decision_counts["unresolved"] + decision_counts["abstained"],
                len(eligible_for_decision),
                "no complete eligible labels",
            ),
        },
        "reference_coverage": reference_coverage,
    }


def _strata_for(row: Mapping[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    raw = row.get("strata")
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            key_text = _as_text(key)
            value_text = _as_text(value)
            if key_text and value_text:
                output[key_text] = value_text
    # These fields are standard in the WP-5 case contract.  Including them in
    # the derived view makes a caller's result useful even when it has no
    # precomputed strata object.
    for key in (
        "data_kind",
        "instrument_id",
        "radiation",
        "calibration_status",
        "overlap",
        "library_completeness",
    ):
        value = _as_text(row.get(key))
        if value and key not in output:
            output[key] = value
    return output


def aggregate_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    top_k: Sequence[int] = (1, 3, 5),
    include_strata: bool = True,
) -> dict[str, Any]:
    """Compute WP-5 metrics directly from persisted case rows.

    The order of input rows does not affect the result.  Case rows with an
    error remain in case and failure counts; complete truth-bearing failures
    remain in the recall/exact-set denominators.  Incomplete labels and
    missing-library cases are reported separately and never silently treated
    as false predictions.
    """

    if isinstance(rows, (str, bytes)):
        raise MetricValidationError("metric rows must be a sequence of objects")
    materialized: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise MetricValidationError(f"metric row {index} must be an object")
        detached = dict(row)
        case_id = _as_text(detached.get("case_id", detached.get("id")))
        if not case_id:
            raise MetricValidationError(f"metric row {index} has no case_id")
        if case_id in seen_case_ids:
            raise MetricValidationError(f"duplicate metric case_id: {case_id}")
        seen_case_ids.add(case_id)
        materialized.append(detached)
    result = _base_metrics(materialized, top_k)
    result["metric_schema_version"] = "wp5-metrics-0.1"
    result["macro"] = _macro_views(materialized, top_k)
    if not include_strata:
        return result
    strata: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in materialized:
        for key, value in _strata_for(row).items():
            strata[key][value].append(row)
    result["strata"] = {
        key: {
            value: _base_metrics(group_rows, top_k)
            for value, group_rows in sorted(values.items())
        }
        for key, values in sorted(strata.items())
    }
    return result


def _mean_defined(values: Sequence[Any], *, reason: str) -> MetricValue:
    numbers = [float(value) for value in values if _metric_number(value) is not None]
    if not numbers:
        return _metric(0, 0, reason)
    return {"numerator": None, "denominator": len(numbers), "rate": sum(numbers) / len(numbers), "undefined_reason": None}


def _macro_views(rows: Sequence[Mapping[str, Any]], top_k: Sequence[int]) -> dict[str, Any]:
    """Return equal-weight group/sample macro views alongside micro metrics."""

    candidate_fields = (
        "sample_id",
        "group_id",
        "structure_family",
        "instrument_id",
        "radiation",
    )
    output: dict[str, Any] = {}
    for field in candidate_fields:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            value = _as_text(row.get(field))
            if value:
                groups[value].append(row)
        if not groups:
            continue
        per_group = {value: _base_metrics(group_rows, top_k) for value, group_rows in sorted(groups.items())}
        exact_rates = [summary["exact_set"]["rate"] for summary in per_group.values()]
        selection_rates = [summary["selection"]["recall"]["rate"] for summary in per_group.values()]
        output[field] = {
            "group_count": len(per_group),
            "status": "ok" if len(per_group) >= 2 else "insufficient_data",
            "reason": None if len(per_group) >= 2 else "at least two independent groups are required",
            "exact_set": _mean_defined(exact_rates, reason="no defined group exact-set rates"),
            "selection_recall": _mean_defined(selection_rates, reason="no defined group selection-recall rates"),
            "groups": per_group,
        }
    return output


def macro_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    group_key: str = "sample_id",
    top_k: Sequence[int] = (1, 3, 5),
) -> dict[str, Any]:
    """Compute an equal-weight macro view over independent groups."""

    aggregate = aggregate_metrics(rows, top_k=top_k, include_strata=False)
    return aggregate.get("macro", {}).get(group_key, {
        "group_count": 0,
        "status": "insufficient_data",
        "reason": f"no rows contain {group_key}",
        "exact_set": _metric(0, 0, f"no rows contain {group_key}"),
        "selection_recall": _metric(0, 0, f"no rows contain {group_key}"),
        "groups": {},
    })


def compute_wp5_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    top_k: Sequence[int] = (1, 3, 5),
    include_strata: bool = True,
) -> dict[str, Any]:
    """Explicit alias used by benchmark scripts and closure validators."""

    return aggregate_metrics(rows, top_k=top_k, include_strata=include_strata)


def compute_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    top_k: Sequence[int] = (1, 3, 5),
    include_strata: bool = True,
) -> dict[str, Any]:
    """Short compatibility alias for callers that expose a generic metric API."""

    return aggregate_metrics(rows, top_k=top_k, include_strata=include_strata)


def safe_rate(numerator: int, denominator: int) -> float | None:
    """Return a rate or ``None`` for an undefined denominator."""

    if denominator == 0:
        return None
    return float(numerator / denominator)


def _metric_number(value: Any) -> float | None:
    if isinstance(value, Mapping):
        value = value.get("rate", value.get("value"))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise MetricValidationError("cannot calculate a percentile of no values")
    if fraction <= 0:
        return ordered[0]
    if fraction >= 1:
        return ordered[-1]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def grouped_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    metric: MetricFunction,
    *,
    group_key: str | Callable[[Mapping[str, Any]], Any] = "group_id",
    n_resamples: int = 2_000,
    seed: int = 0,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Calculate a fixed-seed cluster bootstrap confidence interval.

    Resampling occurs at the independent group level.  All rows belonging to
    one group are sampled together, so repeated scans cannot create false
    statistical power.  The callback may return a scalar or a metric mapping
    containing ``rate``/``value``.  Undefined callback outputs are dropped and
    reported; if no valid resample remains, the interval is explicitly marked
    ``insufficient_data``.
    """

    if isinstance(n_resamples, bool) or not isinstance(n_resamples, int) or n_resamples < 1:
        raise MetricValidationError("n_resamples must be a positive integer")
    if isinstance(confidence_level, bool) or not isinstance(confidence_level, (int, float)):
        raise MetricValidationError("confidence_level must be a finite number in (0, 1)")
    confidence = float(confidence_level)
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise MetricValidationError("confidence_level must be a finite number in (0, 1)")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise MetricValidationError("seed must be an integer")

    if isinstance(rows, (str, bytes)):
        raise MetricValidationError("bootstrap rows must be a sequence of objects")
    materialized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise MetricValidationError(f"bootstrap row {index} must be an object")
        materialized.append(dict(row))
    key_fn = group_key if callable(group_key) else lambda row: row.get(group_key)
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, row in enumerate(materialized):
        raw = key_fn(row)
        group = _as_text(raw)
        if not group:
            raise MetricValidationError(f"row {index} has no independent group identifier")
        groups[group].append(row)
    # Keep the resampling independent of the order in which a persisted
    # result file happened to be read.  A metric callback should itself be
    # order-independent, but deterministic inputs make that contract safer.
    for group_rows in groups.values():
        group_rows.sort(key=lambda row: (_as_text(row.get("case_id", row.get("id"))) or "", _canonical_row(row)))
    materialized.sort(key=lambda row: (_as_text(row.get("case_id", row.get("id"))) or "", _canonical_row(row)))
    ordered_groups = tuple(sorted(groups))
    group_count = len(ordered_groups)

    estimate = _metric_number(metric(materialized)) if materialized else None
    base = {
        "method": "cluster_bootstrap",
        "group_key": group_key if isinstance(group_key, str) else "callable",
        "group_count": group_count,
        "resamples": n_resamples,
        "seed": seed,
        "confidence_level": confidence,
        "estimate": estimate,
        "lower": None,
        "upper": None,
        "resamples_used": 0,
        "dropped_resamples": 0,
    }
    if group_count < 2:
        return {
            **base,
            "status": "insufficient_data",
            "reason": "at least two independent groups are required",
        }
    if estimate is None:
        return {
            **base,
            "status": "insufficient_data",
            "reason": "the point estimate has an undefined denominator or is nonfinite",
        }

    generator = random.Random(seed)
    values: list[float] = []
    for _ in range(n_resamples):
        sampled_rows: list[Mapping[str, Any]] = []
        for _ in ordered_groups:
            selected_group = ordered_groups[generator.randrange(group_count)]
            sampled_rows.extend(groups[selected_group])
        value = _metric_number(metric(sampled_rows))
        if value is None:
            base["dropped_resamples"] = int(base["dropped_resamples"]) + 1
            continue
        values.append(value)

    if not values:
        return {
            **base,
            "status": "insufficient_data",
            "reason": "all bootstrap resamples had undefined metrics",
        }
    alpha = (1.0 - confidence) / 2.0
    return {
        **base,
        "status": "ok",
        "lower": _percentile(values, alpha),
        "upper": _percentile(values, 1.0 - alpha),
        "resamples_used": len(values),
    }


def bootstrap_metric(
    rows: Sequence[Mapping[str, Any]],
    metric: MetricFunction,
    *,
    group_key: str | Callable[[Mapping[str, Any]], Any] = "group_id",
    n_resamples: int = 2_000,
    seed: int = 0,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Compatibility alias for :func:`grouped_bootstrap`."""

    return grouped_bootstrap(
        rows,
        metric,
        group_key=group_key,
        n_resamples=n_resamples,
        seed=seed,
        confidence_level=confidence_level,
    )


__all__ = [
    "MetricFunction",
    "MetricValidationError",
    "MetricValue",
    "aggregate_metrics",
    "bootstrap_metric",
    "compute_wp5_metrics",
    "compute_metrics",
    "macro_metrics",
    "grouped_bootstrap",
    "safe_rate",
]
