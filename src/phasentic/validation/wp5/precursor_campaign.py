"""Deterministic intake for the Precursor Genome measured-evidence campaign.

The public Precursor ledger contains many scans and multiple refinement
attempts per sample.  This module selects one explicitly active, accepted
refinement per sample, authenticates the corresponding raw scan, and records
every rejection reason.  It does not map ICSD labels to POW_COD groups; that
is a separate reviewed crosswalk and remains a hard boundary for strict
metrics.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


class PrecursorCampaignError(ValueError):
    """Raised when campaign intake cannot proceed without guessing."""


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SOURCE_URL = "https://github.com/lauren-walters/precursor-genome"
_ZENODO_URL = "https://zenodo.org/records/21285546"
_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or not _IDENTIFIER.fullmatch(value.strip()):
        raise PrecursorCampaignError(f"{field}_invalid: expected a stable identifier")
    return value.strip()


def _safe_raw_root(raw_root: str | Path) -> Path:
    root = Path(raw_root).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise PrecursorCampaignError(f"raw_root_unavailable: {root}")
    return root


def _resolve_raw(root: Path, ledger_filename: Any) -> tuple[Path | None, str]:
    if not isinstance(ledger_filename, str) or not ledger_filename.strip():
        return None, "raw_filename_missing"
    candidate = Path(ledger_filename)
    candidates: list[Path] = []
    if not candidate.is_absolute():
        direct = (root / candidate).resolve()
        try:
            direct.relative_to(root)
        except ValueError:
            direct = None  # type: ignore[assignment]
        if direct is not None and direct.is_file() and not direct.is_symlink():
            candidates.append(direct)
    if not candidates:
        name = candidate.name
        if not name:
            return None, "raw_filename_missing"
        candidates = sorted(
            item.resolve()
            for item in root.rglob(name)
            if item.is_file() and not item.is_symlink()
        )
    unique = list(dict.fromkeys(candidates))
    if not unique:
        return None, "raw_file_missing"
    if len(unique) > 1:
        return None, "raw_file_ambiguous"
    return unique[0], ""


def _active_scan(sample: Mapping[str, Any]) -> Mapping[str, Any] | None:
    xrd = sample.get("characterization", {}).get("xrd", {}) if isinstance(sample.get("characterization"), Mapping) else {}
    scans = xrd.get("scans") if isinstance(xrd, Mapping) else None
    if not isinstance(scans, list) or not scans:
        return None
    index = sample.get("active_scan_index")
    if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(scans):
        selected = scans[index]
        return selected if isinstance(selected, Mapping) else None
    active = [item for item in scans if isinstance(item, Mapping) and item.get("is_active") is True]
    return active[0] if len(active) == 1 else None


def _active_refinement(scan: Mapping[str, Any]) -> Mapping[str, Any] | None:
    cases = scan.get("refinement_cases")
    if not isinstance(cases, list) or not cases:
        return None
    index = scan.get("active_case_index")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(cases):
        return None
    selected = cases[index]
    return selected if isinstance(selected, Mapping) else None


def _quality(refinement: Mapping[str, Any]) -> tuple[bool, int | None, str]:
    verification = refinement.get("verification")
    if not isinstance(verification, Mapping) or verification.get("is_accepted") is not True:
        return False, None, "refinement_not_accepted"
    score = verification.get("human_quality_score")
    if isinstance(score, bool) or not isinstance(score, int):
        return False, None, "human_quality_missing"
    return True, score, ""


def _weights(refinement: Mapping[str, Any]) -> tuple[dict[str, float], list[str]]:
    raw = refinement.get("phase_weights")
    if not isinstance(raw, Mapping) or not raw:
        raise PrecursorCampaignError("phase_weights_missing: accepted refinement has no phase weights")
    output: dict[str, float] = {}
    for label, value in raw.items():
        if not isinstance(label, str) or not label.strip():
            raise PrecursorCampaignError("phase_label_invalid: phase weights keys must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
            raise PrecursorCampaignError(f"phase_weight_invalid: {label}")
        output[label.removesuffix(".cif")] = float(value)
    labels = refinement.get("cif_names")
    if isinstance(labels, list):
        ordered = [str(item).removesuffix(".cif") for item in labels if isinstance(item, str) and item.strip()]
        for label in output:
            if label not in ordered:
                ordered.append(label)
    else:
        ordered = list(output)
    return output, ordered


def _stratum(phase_count: int) -> str:
    if phase_count <= 1:
        return "single"
    if phase_count == 2:
        return "two"
    return "three_or_more"


def _allocate(count: int, grouped: Mapping[str, list[dict[str, Any]]]) -> dict[str, int]:
    total = sum(len(items) for items in grouped.values())
    if total <= 0:
        return {key: 0 for key in grouped}
    keys = sorted(grouped)
    raw = {key: count * len(grouped[key]) / total for key in keys}
    allocation = {key: int(math.floor(raw[key])) for key in keys}
    remaining = count - sum(allocation.values())
    for key in sorted(keys, key=lambda item: (-(raw[item] - allocation[item]), item))[:remaining]:
        allocation[key] += 1
    return allocation


def select_precursor_cases(
    ledger: Mapping[str, Any],
    raw_root: str | Path,
    *,
    count: int = 100,
    seed: int = 17,
    max_human_quality_score: int = 1,
    exclude_sample_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Select a reproducible, stratified Precursor cohort.

    ``exclude_sample_ids`` reserves samples that belong to another cohort
    (for example the development bundle) so a held-out cohort never
    overlaps it. Excluded samples are counted as ``reserved_by_other_cohort``.

    Selection is by sample, never by individual refinement case.  Only the
    ledger's active scan and active accepted refinement are eligible.  Human
    quality score 1 is the default so the campaign does not silently treat a
    score-2 or score-3 case as a perfect reference.
    """

    if not isinstance(ledger, Mapping):
        raise PrecursorCampaignError("ledger_invalid: expected an object")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise PrecursorCampaignError("count_invalid: expected a positive integer")
    if not isinstance(max_human_quality_score, int) or isinstance(max_human_quality_score, bool) or max_human_quality_score < 1:
        raise PrecursorCampaignError("quality_limit_invalid: expected a positive integer")
    samples = ledger.get("samples")
    if not isinstance(samples, list):
        raise PrecursorCampaignError("ledger_samples_invalid: samples must be an array")
    root = _safe_raw_root(raw_root)
    reserved = {str(value) for value in (exclude_sample_ids or ())}
    excluded: Counter[str] = Counter()
    eligible: list[dict[str, Any]] = []
    seen_samples: set[str] = set()
    for raw_sample in samples:
        if not isinstance(raw_sample, Mapping):
            excluded["sample_invalid"] += 1
            continue
        try:
            sample_id = _identifier(raw_sample.get("sample_id"), "sample_id")
        except PrecursorCampaignError:
            excluded["sample_id_invalid"] += 1
            continue
        if sample_id in seen_samples:
            excluded["duplicate_sample_id"] += 1
            continue
        seen_samples.add(sample_id)
        if sample_id in reserved:
            excluded["reserved_by_other_cohort"] += 1
            continue
        scan = _active_scan(raw_sample)
        if scan is None:
            excluded["active_scan_missing"] += 1
            continue
        if scan.get("status") != "valid":
            excluded["scan_not_valid"] += 1
            continue
        refinement = _active_refinement(scan)
        if refinement is None:
            excluded["active_refinement_missing"] += 1
            continue
        accepted, score, reason = _quality(refinement)
        if not accepted:
            excluded[reason] += 1
            continue
        assert score is not None
        if score > max_human_quality_score:
            excluded["human_quality_above_limit"] += 1
            continue
        try:
            weights, labels = _weights(refinement)
        except PrecursorCampaignError as exc:
            excluded[str(exc).split(":", 1)[0]] += 1
            continue
        raw_file, reason = _resolve_raw(root, scan.get("filename"))
        if raw_file is None:
            excluded[reason] += 1
            continue
        try:
            relative_raw = raw_file.relative_to(root).as_posix()
        except ValueError as exc:  # pragma: no cover - guarded by resolver
            raise PrecursorCampaignError("raw_path_escape: resolved file is outside raw root") from exc
        phase_count = sum(1 for value in weights.values() if value > 0.0)
        if phase_count < 1:
            excluded["phase_weights_empty"] += 1
            continue
        digest = _sha256(raw_file)
        selection_key = hashlib.sha256(f"{seed}:{sample_id}:{digest}".encode("utf-8")).hexdigest()
        xrd_settings = scan.get("xrd_settings") if isinstance(scan.get("xrd_settings"), Mapping) else {}
        range_value = xrd_settings.get("range_2theta", [10.0, 100.0])
        if not isinstance(range_value, (list, tuple)) or len(range_value) != 2:
            excluded["scan_range_invalid"] += 1
            continue
        eligible.append({
            "case_id": f"precursor-{sample_id.lower()}",
            "sample_id": sample_id,
            "scan_id": Path(str(scan.get("filename"))).stem,
            "raw_path": relative_raw,
            "raw_sha256": digest,
            "raw_size_bytes": raw_file.stat().st_size,
            "radiation": "Cu Ka",
            "angle_unit": "two_theta",
            "geometry": "reflection_bragg_brentano",
            "scan_range_deg": [float(range_value[0]), float(range_value[1])],
            "instrument_profile": xrd_settings.get("instrument_profile"),
            "source_phase_labels": labels,
            "expected_phase_weights": {key: weights[key] for key in sorted(weights)},
            "human_quality_score": score,
            "human_quality_score_history": list((refinement.get("verification") or {}).get("quality_score_history", [])),
            "refinement_rank": refinement.get("rank"),
            "refinement_rwp": refinement.get("rwp"),
            "refinement_origin": refinement.get("origin"),
            "phase_count": phase_count,
            "phase_stratum": _stratum(phase_count),
            "selection_key": selection_key,
            "precursor_source": _SOURCE_URL,
            "raw_archive_source": _ZENODO_URL,
            "license": "CC BY 4.0",
            "license_url": _LICENSE_URL,
        })
    if len(eligible) < count:
        raise PrecursorCampaignError(f"eligible_count_insufficient: requested {count}, found {len(eligible)}")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in eligible:
        grouped[str(item["phase_stratum"])].append(item)
    for items in grouped.values():
        items.sort(key=lambda item: (str(item["selection_key"]), str(item["sample_id"])))
    selected: list[dict[str, Any]] = []
    allocation = _allocate(count, grouped)
    for stratum in sorted(grouped):
        selected.extend(grouped[stratum][:allocation[stratum]])
    selected.sort(key=lambda item: (str(item["selection_key"]), str(item["sample_id"])))
    for rank, item in enumerate(selected, start=1):
        item["selection_rank"] = rank
        item.pop("selection_key", None)
    payload: dict[str, Any] = {
        "schema_version": "wp5-precursor-campaign-selection-1",
        "status": "selected",
        "selection_policy": {
            "requested_count": count,
            "seed": seed,
            "max_human_quality_score": max_human_quality_score,
            "require_active_scan": True,
            "require_active_accepted_refinement": True,
            "stratification": "phase_count:single,two,three_or_more",
            "excluded_sample_count": len(reserved),
            "excluded_sample_ids_sha256": hashlib.sha256(
                "\n".join(sorted(reserved)).encode("utf-8")
            ).hexdigest(),
            "source_truth": "Precursor accepted human refinement phase presence and weights",
        },
        "source": {
            "repository_url": _SOURCE_URL,
            "raw_archive_url": _ZENODO_URL,
            "license": "CC BY 4.0",
            "license_url": _LICENSE_URL,
            "ledger_sample_count": len(samples),
        },
        "selected_cases": selected,
        "selected_count": len(selected),
        "eligible_count": len(eligible),
        "excluded_counts": dict(sorted(excluded.items())),
    }
    payload["manifest_sha256"] = _canonical_hash(payload)
    return payload


__all__ = ["PrecursorCampaignError", "select_precursor_cases"]

