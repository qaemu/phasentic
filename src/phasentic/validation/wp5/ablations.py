"""Contracts and paired summaries for WP-5 ablation suites.

An ablation suite is a collection of production-path result artifacts that
share one frozen bundle, split, variant, and reference identity.  This module
only compares persisted result data; it does not rerun the matcher or infer
scientific significance from a small pilot.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any


ABLATION_SUITE_SCHEMA_VERSION = "wp5-ablation-suite-0.1"


class AblationValidationError(ValueError):
    """Raised when an ablation declaration or suite cannot be trusted."""


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def validate_ablation_declarations(raw: Any) -> tuple[dict[str, Any], ...]:
    """Validate and copy protocol ablations without mutating the protocol.

    A declaration must have a stable identifier and a non-empty settings
    object.  ``factor`` is optional for backwards-compatible protocols, but
    new protocols should provide it so reports can state what was changed.
    """

    if not isinstance(raw, (list, tuple)):
        raise AblationValidationError("ablations must be an array")
    declarations: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise AblationValidationError(f"ablation[{index}] must be an object")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise AblationValidationError(f"ablation[{index}].id must be a non-empty string")
        identifier = identifier.strip()
        if identifier in identifiers:
            raise AblationValidationError(f"ablation_id_duplicate: {identifier}")
        identifiers.add(identifier)
        changes = item.get("changes")
        # Older frozen protocols used ``levels`` as a planning declaration
        # before executable paired runs were introduced.  Preserve those
        # manifests for audit/review; the execution command will reject them
        # with a named ``changes_missing`` error.
        if changes is None and isinstance(item.get("levels"), (list, tuple)) and item.get("levels"):
            changes = {}
        if not isinstance(changes, Mapping) or (not changes and not (isinstance(item.get("levels"), (list, tuple)) and item.get("levels"))):
            raise AblationValidationError(f"ablation[{identifier}].changes must be an object")
        factor = item.get("factor", "unspecified")
        if not isinstance(factor, str) or not factor.strip():
            raise AblationValidationError(f"ablation[{identifier}].factor must be a non-empty string")
        copied = {str(key): value for key, value in item.items()}
        copied["id"] = identifier
        copied["factor"] = factor.strip()
        copied["changes"] = dict(changes)
        declarations.append(copied)
    return tuple(declarations)


def _metric_value(metrics: Mapping[str, Any], path: Sequence[str]) -> Mapping[str, Any] | None:
    current: Any = metrics
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return dict(current) if isinstance(current, Mapping) else None


_PAIRED_METRICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("exact_set_recovery", ("exact_set_recovery",)),
    ("candidate_recall_at_1", ("top_k_recall", "1")),
    ("candidate_recall_at_3", ("top_k_recall", "3")),
    ("candidate_recall_at_5", ("top_k_recall", "5")),
    ("selection_precision", ("selection", "precision")),
    ("selection_recall", ("selection", "recall")),
    ("failure_rate", ("failure_rate",)),
)


def paired_metric_deltas(baseline: Mapping[str, Any], ablation: Mapping[str, Any]) -> dict[str, Any]:
    """Return transparent rate/numerator/denominator comparisons.

    Missing or undefined rates remain explicit; they are never converted to
    zero.  A delta is computed only when both rates are finite numbers.
    """

    baseline_metrics = baseline.get("metrics", {})
    ablation_metrics = ablation.get("metrics", {})
    if not isinstance(baseline_metrics, Mapping) or not isinstance(ablation_metrics, Mapping):
        raise AblationValidationError("result metrics must be objects")
    output: dict[str, Any] = {}
    for name, path in _PAIRED_METRICS:
        before = _metric_value(baseline_metrics, path)
        after = _metric_value(ablation_metrics, path)
        before_rate = before.get("rate") if before else None
        after_rate = after.get("rate") if after else None
        delta = None
        reason = None
        if isinstance(before_rate, (int, float)) and not isinstance(before_rate, bool) and isinstance(after_rate, (int, float)) and not isinstance(after_rate, bool):
            delta = float(after_rate) - float(before_rate)
        else:
            reason = "undefined_rate_or_metric_missing"
        output[name] = {
            "baseline": before,
            "ablation": after,
            "delta_rate": delta,
            "undefined_reason": reason,
        }
    return output


def validate_ablation_suite(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the portable shape of a persisted ablation suite."""

    if not isinstance(payload, Mapping):
        raise AblationValidationError("ablation suite must be an object")
    if payload.get("schema_version") != ABLATION_SUITE_SCHEMA_VERSION:
        raise AblationValidationError("ablation_suite_schema_unsupported")
    if payload.get("status") not in {"complete", "partial", "failed"}:
        raise AblationValidationError("ablation_suite_status_invalid")
    for key in ("protocol_id", "protocol_sha256", "bundle_id", "split", "variant", "reference_source"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise AblationValidationError(f"ablation_suite_{key}_invalid")
    for key in ("protocol_sha256", "bundle_id", "content_sha256"):
        if not isinstance(payload.get(key), str) or not _SHA256.fullmatch(payload[key]):
            raise AblationValidationError(f"ablation_suite_{key}_invalid")
    baseline = payload.get("baseline")
    if not isinstance(baseline, Mapping) or not isinstance(baseline.get("result_sha256"), str) or not _SHA256.fullmatch(baseline["result_sha256"]):
        raise AblationValidationError("ablation_suite_baseline_invalid")
    try:
        declarations = validate_ablation_declarations(payload.get("ablations", []))
    except AblationValidationError:
        raise
    entries = payload.get("ablations")
    if not isinstance(entries, list) or len(entries) != len(declarations):
        raise AblationValidationError("ablation_suite_entries_invalid")
    for declaration, entry in zip(declarations, entries):
        if declaration.get("factor") == "unspecified":
            raise AblationValidationError(f"ablation_suite_factor_missing: {declaration['id']}")
        if entry.get("id") != declaration["id"] or not isinstance(entry.get("result_sha256"), str):
            raise AblationValidationError(f"ablation_suite_entry_invalid: {declaration['id']}")
        if not _SHA256.fullmatch(entry["result_sha256"]):
            raise AblationValidationError(f"ablation_suite_entry_hash_invalid: {declaration['id']}")
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    if payload.get("content_sha256") != _canonical_hash(unsigned):
        raise AblationValidationError("ablation_suite_content_hash_mismatch")
    return dict(payload)


def _canonical_hash(value: Any) -> str:
    """Import lazily to keep this small contract module dependency-light."""

    from .artifacts import canonical_sha256

    return canonical_sha256(value)


__all__ = [
    "ABLATION_SUITE_SCHEMA_VERSION",
    "AblationValidationError",
    "paired_metric_deltas",
    "validate_ablation_declarations",
    "validate_ablation_suite",
]
