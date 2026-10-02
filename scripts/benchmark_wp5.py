#!/usr/bin/env python3
"""Build and execute the reproducible WP-5 evaluation package.

The commands in this module operate on local, hash-authenticated manifests.
They deliberately keep dataset acquisition separate from evaluation: an
operator may inventory public or private material, but no downloader or
network service is invoked by the benchmark runner.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phasentic.domain.models import AnalysisSettings, AngleUnit
from phasentic.references.factory import ReferenceConfigurationError, open_reference_store
from phasentic.references.equivalence import (
    RuntimeEquivalenceSettings,
    formulas_compatible,
    parse_source_phase_label,
    space_group_number,
)
from phasentic.reporting.service import ALGORITHM_VERSION, analyze_file
from phasentic.validation.wp5.artifacts import (
    WP5ArtifactError,
    artifact_record,
    canonical_sha256,
    sha256_file,
    write_json_atomic,
)
from phasentic.validation.wp5.contracts import (
    CaseManifest,
    Protocol,
    SourceManifest,
    canonical_contract_sha256,
    load_case_manifest,
    load_protocol,
    load_source_manifest,
)
from phasentic.validation.wp5.metrics import compute_wp5_metrics, evaluate_phase_agreement, grouped_bootstrap
from phasentic.validation.wp5.policy import (
    evaluation_policy_from_query,
    WP5_PHASE_AGREEMENT_MINIMUM_RATIO,
    WP5_PHASE_AGREEMENT_TOP_N,
)
from phasentic.validation.wp5.phase_scoring import (
    PHASE_SCORING_VERSION,
    best_hypothesis_rank,
    labels_from_source,
    predictions_from_components,
    score_phase_agreement,
)
from phasentic.validation.wp5.runner import EvaluationRunner, RunnerValidationError
from phasentic.validation.wp5.sources import SourcePathError, hash_file, verify_source_manifest_files
from phasentic.validation.wp5.splits import SplitLeakageError, validate_split_assignments, validate_split_track


class WP5CommandError(ValueError):
    """A named, user-facing WP-5 command failure."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WP5CommandError(f"artifact_read_failed: {path}") from exc


def _safe_root(path: Path) -> Path:
    candidate = path.expanduser().absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            raise WP5CommandError(f"path_unsafe: symlink root is not allowed: {path}")
    return candidate


def _safe_file_path(path: Path, *, code: str) -> Path:
    """Return a lexical absolute file path after rejecting symlink parents."""

    candidate = path.expanduser().absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            raise WP5CommandError(f"{code}: symlink path is not allowed: {path}")
    return candidate


def _manifest_data_root(path: Path, manifest: SourceManifest) -> Path:
    """Resolve the source root while supporting both documented layouts.

    A manifest may store paths relative to its own directory or to its
    ``data_root`` directory.  Prefer the layout whose eligible hashes all
    authenticate; never guess between two conflicting files.
    """

    parent = path.resolve().parent
    candidates = [parent]
    declared = (parent / manifest.data_root).resolve()
    if declared != parent:
        candidates.append(declared)
    for candidate in candidates:
        try:
            verify_source_manifest_files(manifest, candidate)
            return candidate
        except (SourcePathError, OSError):
            continue
    raise WP5CommandError("source_files_unavailable: no manifest data root authenticates all eligible files")


def _write_output(path: Path, payload: Any, *, refuse_existing: bool = False) -> None:
    path = path.expanduser().resolve()
    exists_with_content = path.is_dir() and any(path.iterdir())
    if refuse_existing and (exists_with_content or (path.exists() and not path.is_dir())):
        raise WP5CommandError(f"output_exists: refusing to overwrite {path}")
    write_json_atomic(path, payload)


def import_sources(source_path: Path, data_root: Path, output: Path) -> dict[str, Any]:
    manifest = load_source_manifest(source_path)
    actual_root = _safe_root(data_root)
    try:
        checked = verify_source_manifest_files(manifest, actual_root)
    except SourcePathError as exc:
        raise WP5CommandError(f"source_verification_failed: {exc}") from exc
    payload = {
        "schema_version": "wp5-import-result-0.1",
        "status": "complete",
        "manifest_id": manifest.manifest_id,
        "manifest_sha256": canonical_contract_sha256(manifest.to_dict()),
        "data_root": str(actual_root),
        "source_count": len(manifest.sources),
        "eligible_count": sum(item.status == "eligible" for item in manifest.sources),
        "sources": [dict(item) for item in checked],
        "created_at": _now(),
    }
    _write_output(output, payload)
    return payload


def _copy_contained(source_root: Path, relative: str, destination_root: Path) -> None:
    source = (source_root / relative).resolve()
    try:
        source.relative_to(source_root.resolve())
    except ValueError as exc:
        raise WP5CommandError(f"path_unsafe: source escapes data root: {relative}") from exc
    if not source.is_file() or source.is_symlink():
        raise WP5CommandError(f"source_files_unavailable: {relative}")
    destination = destination_root / relative
    # ``mkdir -p`` follows a pre-existing symlink in a destination parent.
    # Check every component before creating directories so a manifest cannot
    # redirect a frozen bundle outside its root.
    cursor = destination_root
    for part in Path(relative).parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise WP5CommandError(f"path_unsafe: destination parent is a symlink: {relative}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink() or destination.is_symlink():
        raise WP5CommandError(f"path_unsafe: destination is a symlink: {relative}")
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_file() or sha256_file(destination) != sha256_file(source):
            raise WP5CommandError(f"duplicate_path_conflict: {relative}")
        return
    shutil.copyfile(source, destination)


def freeze_bundle(case_path: Path, protocol_path: Path, output: Path, source_path: Path | None = None) -> dict[str, Any]:
    case_manifest = load_case_manifest(case_path)
    protocol = load_protocol(protocol_path)
    source_path = source_path or case_path.resolve().parent / "source-manifest.json"
    source_manifest = load_source_manifest(source_path)
    if case_manifest.source_manifest_id != source_manifest.manifest_id:
        raise WP5CommandError("manifest_link_invalid: case and source manifests do not match")
    if protocol.source_manifest_id != source_manifest.manifest_id or protocol.case_manifest_id != case_manifest.manifest_id:
        raise WP5CommandError("manifest_link_invalid: protocol does not reference supplied manifests")
    if (output.is_dir() and any(output.iterdir())) or (output.exists() and not output.is_dir()):
        raise WP5CommandError(f"output_exists: refusing to overwrite {output}")
    source_root = _manifest_data_root(source_path, source_manifest)
    try:
        source_checks = verify_source_manifest_files(source_manifest, source_root)
    except SourcePathError as exc:
        raise WP5CommandError(f"source_verification_failed: {exc}") from exc
    # Bind every eligible case to an authenticated source record before any
    # output directory is created.  A case may not smuggle in a path/hash that
    # is absent from the source inventory, and non-eligible source records may
    # never be used to create an eligible evaluation row.
    source_by_id = {source.source_id: source for source in source_manifest.sources}
    source_by_path: dict[str, tuple[Any, str]] = {}
    for source in source_manifest.sources:
        for path, identity_kind in ((source.local_path, "normalized"), (source.raw_local_path, "raw")):
            if path is None:
                continue
            if path in source_by_path and source_by_path[path][0].source_id != source.source_id:
                raise WP5CommandError(f"case_source_invalid: source path is claimed by multiple sources: {path}")
            source_by_path[path] = (source, identity_kind)
    for case in case_manifest.cases:
        unknown_sources = sorted(set(case.source_ids).difference(source_by_id))
        if unknown_sources:
            raise WP5CommandError(
                f"case_source_invalid: case {case.case_id} references unknown source_id(s): {', '.join(unknown_sources)}"
            )
        if case.eligibility != "eligible":
            continue
        bound = [source_by_id[source_id] for source_id in case.source_ids]
        if any(source.status != "eligible" for source in bound):
            raise WP5CommandError(f"case_source_invalid: eligible case {case.case_id} references a non-eligible source")
        raw_binding = source_by_path.get(case.raw_path)
        if raw_binding is None or raw_binding[0].source_id not in case.source_ids:
            raise WP5CommandError(f"case_source_invalid: raw_path for case {case.case_id} is not bound to source_ids")
        raw_source, raw_kind = raw_binding
        expected_raw_sha = raw_source.raw_sha256 if raw_kind == "raw" else raw_source.sha256
        if expected_raw_sha is None or case.raw_sha256.lower() != expected_raw_sha.lower():
            raise WP5CommandError(f"case_source_invalid: raw_sha256 for case {case.case_id} does not match its source")
        actual_raw = hash_file(source_root / case.raw_path)
        if actual_raw.lower() != case.raw_sha256.lower():
            raise WP5CommandError(f"case_source_invalid: raw bytes for case {case.case_id} do not match raw_sha256")
        if case.normalized_path is not None:
            normalized_binding = source_by_path.get(case.normalized_path)
            if normalized_binding is None or normalized_binding[0].source_id not in case.source_ids:
                raise WP5CommandError(
                    f"case_source_invalid: normalized_path for case {case.case_id} is not bound to source_ids"
                )
            normalized_source, normalized_kind = normalized_binding
            if normalized_kind != "normalized" or normalized_source.sha256 is None:
                raise WP5CommandError(
                    f"case_source_invalid: normalized_path for case {case.case_id} is not a normalized source"
                )
            if case.normalized_sha256 is None or case.normalized_sha256.lower() != normalized_source.sha256.lower():
                raise WP5CommandError(
                    f"case_source_invalid: normalized_sha256 for case {case.case_id} does not match its source"
                )
            actual_normalized = hash_file(source_root / case.normalized_path)
            if actual_normalized.lower() != case.normalized_sha256.lower():
                raise WP5CommandError(
                    f"case_source_invalid: normalized bytes for case {case.case_id} do not match normalized_sha256"
                )
    try:
        split_summary = validate_split_assignments(
            [case.to_dict() for case in case_manifest.cases],
            enforce_family=True,
            require_explicit_split=True,
        )
    except SplitLeakageError as exc:
        raise WP5CommandError(f"split_invalid: {exc}") from exc
    raw_tracks = protocol.split_policy.get("tracks", ())
    if not isinstance(raw_tracks, (list, tuple)):
        raise WP5CommandError("split_policy_invalid: tracks must be an array")
    minimum_groups = protocol.split_policy.get("minimum_independent_groups", 3)
    split_tracks: dict[str, dict[str, Any]] = {}
    for track in raw_tracks:
        if not isinstance(track, str) or not track.strip():
            raise WP5CommandError("split_policy_invalid: track names must be non-empty strings")
        try:
            split_tracks[track] = validate_split_track(
                [case.to_dict() for case in case_manifest.cases],
                track,
                minimum_independent_groups=int(minimum_groups),
            )
        except (SplitLeakageError, ValueError) as exc:
            raise WP5CommandError(f"split_track_invalid: {track}: {exc}") from exc
    output = _safe_root(output)
    output.mkdir(parents=True, exist_ok=True)
    copied_cases: list[dict[str, Any]] = []
    for case in case_manifest.cases:
        for relative in (case.raw_path, case.normalized_path):
            if relative:
                _copy_contained(source_root, relative, output)
        copied_cases.append(case.to_dict())
    # Copy every eligible source, including sources not currently referenced
    # by a case, so the frozen package remains a complete audit bundle.
    for source in source_manifest.sources:
        if source.status == "eligible" and source.local_path:
            _copy_contained(source_root, source.local_path, output)
        if source.status == "eligible" and source.raw_local_path:
            _copy_contained(source_root, source.raw_local_path, output)
    write_json_atomic(output / "source-manifest.json", source_manifest.to_dict())
    write_json_atomic(output / "case-manifest.json", case_manifest.to_dict())
    write_json_atomic(output / "protocol.json", protocol.to_dict())
    contains_measured = any(case.data_kind.startswith("measured") for case in case_manifest.cases)
    bundle_limitations = ["This bundle is valid only for the declared source and protocol hashes."]
    if contains_measured:
        bundle_limitations.extend(
            [
                "Measured scans are local evaluation evidence only; their rights scope does not authorize redistribution.",
                "Measured calibration, independent held-out groups, and laboratory accuracy remain separate evidence gates.",
            ]
        )
    else:
        bundle_limitations.append("Project-authored pilot scans are synthetic software controls, not measured evidence.")
    if protocol.limitations:
        bundle_limitations.extend(str(item) for item in protocol.limitations)
    manifest_payload: dict[str, Any] = {
        "schema_version": "wp5-bundle-0.1",
        "bundle_id": canonical_sha256({
            "source_manifest": source_manifest.to_dict(),
            "case_manifest": case_manifest.to_dict(),
            "protocol": protocol.to_dict(),
            "source_checks": list(source_checks),
        }),
        "status": "frozen",
        "created_at": _now(),
        "source_manifest": "source-manifest.json",
        "case_manifest": "case-manifest.json",
        "protocol": "protocol.json",
        "source_manifest_sha256": canonical_contract_sha256(source_manifest.to_dict()),
        "case_manifest_sha256": canonical_contract_sha256(case_manifest.to_dict()),
        "protocol_sha256": canonical_contract_sha256(protocol.to_dict()),
        "split_summary": split_summary,
        "split_tracks": split_tracks,
        "case_count": len(copied_cases),
        "source_count": len(source_manifest.sources),
        "limitations": list(dict.fromkeys(bundle_limitations)),
    }
    files = [
        artifact_record(output / name, output, kind=kind)
        for name, kind in (("source-manifest.json", "source-manifest"), ("case-manifest.json", "case-manifest"), ("protocol.json", "protocol"))
    ]
    files.extend(
        artifact_record(path, output, kind="scan")
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name not in {"bundle.json", "source-manifest.json", "case-manifest.json", "protocol.json"}
    )
    manifest_payload["artifacts"] = files
    manifest_payload["content_sha256"] = canonical_sha256(manifest_payload)
    write_json_atomic(output / "bundle.json", manifest_payload)
    return manifest_payload


def _load_bundle(bundle: Path) -> tuple[dict[str, Any], SourceManifest, CaseManifest, Protocol]:
    bundle = _safe_root(bundle)
    manifest = _load(bundle / "bundle.json")
    if manifest.get("schema_version") != "wp5-bundle-0.1" or manifest.get("status") != "frozen":
        raise WP5CommandError("bundle_invalid: bundle is not frozen")
    try:
        for record in manifest.get("artifacts", []):
            from phasentic.validation.wp5.artifacts import verify_artifact_record

            verify_artifact_record(record, bundle)
    except (WP5ArtifactError, TypeError) as exc:
        raise WP5CommandError(f"bundle_integrity_failed: {exc}") from exc
    source = load_source_manifest(bundle / str(manifest["source_manifest"]))
    cases = load_case_manifest(bundle / str(manifest["case_manifest"]))
    protocol = load_protocol(bundle / str(manifest["protocol"]))
    return manifest, source, cases, protocol


def _candidate_group(item: Mapping[str, Any]) -> str | None:
    """Return the frozen equivalence group for one reported candidate."""

    value = (
        item.get("equivalence_group_id")
        or item.get("duplicate_group_id")
        or item.get("equivalence_group")
        or item.get("reference_id")
    )
    return str(value) if value else None


def _select_cases_by_id(
    cases: Sequence[Mapping[str, Any]],
    requested_ids: Sequence[str] | None,
) -> list[Mapping[str, Any]]:
    """Select an explicit case order without consulting label metadata."""

    if requested_ids is None:
        return list(cases)
    if isinstance(requested_ids, (str, bytes)) or not isinstance(requested_ids, Sequence) or not requested_ids:
        raise WP5CommandError("case_selection_invalid: case_ids must be a non-empty sequence")
    if any(not isinstance(value, str) or not value.strip() for value in requested_ids):
        raise WP5CommandError("case_selection_invalid: every case id must be a non-empty string")
    normalized = tuple(value.strip() for value in requested_ids)
    if len(set(normalized)) != len(normalized):
        raise WP5CommandError("case_selection_invalid: duplicate case ids are not allowed")
    by_id: dict[str, Mapping[str, Any]] = {}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in by_id:
            raise WP5CommandError("case_manifest_invalid: case ids must be unique non-empty strings")
        by_id[case_id] = case
    missing = sorted(set(normalized).difference(by_id))
    if missing:
        raise WP5CommandError(
            "case_selection_invalid: ids are absent from the requested eligible split: "
            + ", ".join(missing)
        )
    return [by_id[case_id] for case_id in normalized]


def _resolve_precursor_truth(case: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any] | None:
    """Resolve accepted human labels against this report's runtime clusters.

    The source label is used only after deterministic matching has produced a
    report.  Formula and (when supplied) space-group evidence select a unique
    temporary cluster; ambiguous or missing candidates remain explicitly
    unresolved and cannot become a passing case.
    """

    metadata = case.get("metadata") if isinstance(case.get("metadata"), Mapping) else {}
    if metadata.get("cohort") != "precursor-genome":
        return None
    raw_labels = metadata.get("source_expected_phase_groups")
    if not isinstance(raw_labels, (list, tuple)) or not raw_labels:
        return {
            "status": "unresolved",
            "reason": "source_labels_missing",
            "labels": [],
            "resolved": [],
        }
    raw_weights = metadata.get("expected_phase_weights")
    if not isinstance(raw_weights, Mapping):
        return {
            "status": "unresolved",
            "reason": "source_weights_missing",
            "labels": [str(label) for label in raw_labels],
            "resolved": [],
        }
    provenance = report.get("provenance") if isinstance(report.get("provenance"), Mapping) else {}
    resolution = provenance.get("powcod_equivalence_resolution") if isinstance(provenance.get("powcod_equivalence_resolution"), Mapping) else {}
    groups = resolution.get("groups", [])
    if not isinstance(groups, list):
        groups = []
    resolved: list[dict[str, Any]] = []
    expected_weights: dict[str, float] = {}
    unresolved: list[dict[str, Any]] = []
    for raw_label in raw_labels:
        label = str(raw_label)
        parsed = parse_source_phase_label(label)
        if parsed is None:
            unresolved.append({"source_label": label, "status": "unresolved", "reason": "label_unparseable"})
            continue
        candidates: list[Mapping[str, Any]] = []
        for group in groups:
            if not isinstance(group, Mapping) or not isinstance(group.get("formula"), str):
                continue
            if not formulas_compatible(str(parsed["formula"]), str(group["formula"])):
                continue
            expected_space = parsed.get("space_group_number")
            if expected_space is not None and space_group_number(group.get("space_group")) != expected_space:
                continue
            candidates.append(group)
        candidate_ids = sorted({str(group.get("group_id")) for group in candidates if group.get("group_id")})
        if len(candidate_ids) != 1:
            unresolved.append(
                {
                    "source_label": label,
                    "status": "ambiguous" if len(candidate_ids) > 1 else "unresolved",
                    "reason": "multiple_runtime_groups" if len(candidate_ids) > 1 else "no_runtime_group",
                    "candidate_group_ids": candidate_ids,
                }
            )
            continue
        group_id = candidate_ids[0]
        resolved.append(
            {
                "source_label": label,
                "status": "resolved",
                "group_id": group_id,
                "candidate_group_ids": candidate_ids,
                "icsd_id": parsed.get("icsd_id"),
            }
        )
        raw_weight = raw_weights.get(label)
        if isinstance(raw_weight, (int, float)) and not isinstance(raw_weight, bool):
            expected_weights[group_id] = expected_weights.get(group_id, 0.0) + float(raw_weight)
        else:
            unresolved.append({"source_label": label, "status": "unresolved", "reason": "source_weight_invalid"})
    status = "resolved" if len(resolved) == len(raw_labels) and not unresolved and expected_weights else "unresolved"
    return {
        "status": status,
        "method": "runtime_formula_space_group_cluster_resolution",
        "labels": [str(label) for label in raw_labels],
        "resolved": resolved,
        "unresolved": unresolved,
        "expected_phase_group_weights": dict(sorted(expected_weights.items())),
        "runtime_equivalence_configuration_sha256": resolution.get("configuration_sha256"),
    }



def _score_precursor_row(
    row: dict[str, Any],
    metadata: Mapping[str, Any],
    report: Mapping[str, Any],
    selected_hypothesis: Mapping[str, Any] | None,
    variant: str,
    *,
    top_n: int,
    minimum_ratio: float,
    gate_level: str,
) -> dict[str, Any]:
    """Score a Precursor case by chemistry, independent of runtime group IDs.

    The report is complete and frozen before this runs; labels never reach
    retrieval, ranking or selection.
    """

    raw_labels = metadata.get("source_expected_phase_groups")
    labels, problems = labels_from_source(
        raw_labels if isinstance(raw_labels, (list, tuple)) else [],
        metadata.get("expected_phase_weights") if isinstance(metadata.get("expected_phase_weights"), Mapping) else None,
    )
    if variant == "screening":
        candidates = report.get("candidates") if isinstance(report.get("candidates"), list) else []
        components = candidates[:1]
    else:
        components = list(selected_hypothesis.get("components", [])) if isinstance(selected_hypothesis, Mapping) else []
    coverage = metadata.get("reference_coverage")
    agreement = score_phase_agreement(
        labels,
        predictions_from_components([item for item in components if isinstance(item, Mapping)]),
        gate_level=gate_level,
        top_n=top_n,
        minimum_ratio=minimum_ratio,
        label_problems=problems,
        reference_coverage=coverage if isinstance(coverage, Mapping) else None,
    )
    mixture = report.get("mixture") if isinstance(report.get("mixture"), Mapping) else {}
    hypotheses = mixture.get("hypotheses", []) if isinstance(mixture.get("hypotheses"), list) else []
    agreement["best_hypothesis_rank"] = best_hypothesis_rank(labels, hypotheses, level="family")
    agreement["abstained"] = variant != "screening" and selected_hypothesis is None
    row["phase_agreement"] = agreement
    row["phase_truth_resolution"] = {
        "status": "chemistry_scored",
        "method": PHASE_SCORING_VERSION,
        "source_truth_status": "accepted_source_labels",
        "refinement_origin": metadata.get("refinement_origin"),
    }
    row["label_completeness"] = "complete" if not problems and labels else "incomplete"
    row["campaign_passed"] = bool(agreement["passed"])
    row["correct"] = bool(agreement["levels"]["strict"]["passed"])
    return row


def _analysis_row(
    case: Mapping[str, Any],
    report: Mapping[str, Any] | None,
    error: Mapping[str, Any] | None,
    variant: str,
    *,
    phase_agreement_top_n: int = WP5_PHASE_AGREEMENT_TOP_N,
    phase_agreement_minimum_ratio: float = WP5_PHASE_AGREEMENT_MINIMUM_RATIO,
    phase_match_level: str = "strict",
) -> dict[str, Any]:
    expected = list(case.get("expected_phase_groups", []))
    row: dict[str, Any] = {
        "case_id": case["case_id"],
        "sample_id": case.get("sample_id"),
        "source_ids": list(case.get("source_ids") or []),
        "split": case.get("split"),
        "group_id": case.get("parent_group_id") or case.get("sample_id") or case["case_id"],
        "structure_family": (case.get("family_group_ids") or [case["case_id"]])[0],
        "instrument_id": case.get("instrument_id"),
        "acquisition_id": case.get("acquisition_id"),
        "data_kind": case.get("data_kind"),
        "radiation": case.get("radiation"),
        "calibration_status": (case.get("metadata") or {}).get("calibration_status", "unverified"),
        "library_completeness": (case.get("metadata") or {}).get("reference_completeness", "unknown"),
        "strata": dict(case.get("strata") or {}),
        "expected_phase_groups": expected,
        "expected_parent_family_groups": list(case.get("expected_parent_family_groups", [])),
        "source_expected_phase_labels": list((case.get("metadata") or {}).get("source_expected_phase_groups", [])),
        "label_completeness": case.get("label_completeness", "unknown"),
        "evaluation_status": "analysis_failure" if error else "eligible",
        "variant": variant,
        "top_candidates": [],
        "selected_phase_groups": [],
        "supported_phase_groups": [],
        "tentative_phase_groups": [],
        "decision": "unresolved",
        "score": None,
        "error": dict(error) if error else None,
        "phase_agreement": {"status": "not_applicable", "passed": False},
        "phase_truth_resolution": {"status": "not_run"},
        "campaign_passed": None,
    }
    if report is None:
        return row
    candidates = report.get("candidates", [])
    if isinstance(candidates, list):
        row["top_candidates"] = [
            {
                "reference_id": item.get("reference_id"),
                "equivalence_group": _candidate_group(item),
                "equivalence_group_id": item.get("equivalence_group_id"),
                "duplicate_group_id": item.get("duplicate_group_id"),
                "parent_family_group_id": item.get("parent_family_group_id"),
                "equivalence_kind": item.get("equivalence_kind"),
                "equivalence_confidence": item.get("equivalence_confidence"),
                "equivalence_member_ids": list(item.get("equivalence_member_ids", [])),
                "equivalence_label": item.get("equivalence_label"),
                "equivalence_resolution": item.get("equivalence_resolution"),
                "formula": item.get("formula"),
                "space_group": item.get("space_group"),
                "status": item.get("status"),
                "score": item.get("score"),
            }
            for item in candidates
            if isinstance(item, Mapping) and item.get("reference_id")
        ]
    row["decision"] = str(report.get("decision", "unresolved"))
    if row["top_candidates"]:
        row["score"] = row["top_candidates"][0].get("score")
    mixture = report.get("mixture")
    selected: list[str] = []
    supported: list[str] = []
    selected_hypothesis: Mapping[str, Any] | None = None
    if variant == "screening":
        selected = [str(row["top_candidates"][0]["equivalence_group"])] if row["top_candidates"] else []
    elif isinstance(mixture, Mapping):
        selected_id = mixture.get("selected_hypothesis_id")
        hypotheses = mixture.get("hypotheses", [])
        selected_hypothesis = next((item for item in hypotheses if isinstance(item, Mapping) and item.get("hypothesis_id") == selected_id), None)
        if selected_id is not None and selected_hypothesis is None:
            raise WP5CommandError("mixture_selected_hypothesis_missing")
        if selected_id is None and isinstance(mixture.get("query"), Mapping):
            if mixture["query"].get("stopping_reason") == "ambiguous_selection":
                row["decision"] = "ambiguous"
        if isinstance(selected_hypothesis, Mapping):
            selected = [
                _candidate_group(component)
                for component in selected_hypothesis.get("components", [])
                if isinstance(component, Mapping) and _candidate_group(component)
            ]
            if selected_hypothesis.get("status") == "supported":
                supported = list(selected)
    for item in row["top_candidates"]:
        group = item.get("equivalence_group")
        if item.get("status") == "supported" and group:
            supported.append(str(group))
        elif item.get("status") == "tentative" and group:
            row["tentative_phase_groups"].append(str(group))
    row["selected_phase_groups"] = list(dict.fromkeys(selected))
    row["supported_phase_groups"] = list(dict.fromkeys(supported))
    selected_set = set(row["selected_phase_groups"])
    selected_parent_families: list[str] = []
    if isinstance(mixture, Mapping) and isinstance(selected_hypothesis, Mapping):
        for component in selected_hypothesis.get("components", []):
            if not isinstance(component, Mapping) or not _candidate_group(component) or _candidate_group(component) not in selected_set:
                continue
            parent = component.get("parent_family_group_id")
            if parent:
                selected_parent_families.append(str(parent))
    for item in row["top_candidates"]:
        if item.get("equivalence_group") in selected_set and item.get("parent_family_group_id"):
            selected_parent_families.append(str(item["parent_family_group_id"]))
    row["selected_parent_family_groups"] = list(dict.fromkeys(selected_parent_families))
    metadata = case.get("metadata") if isinstance(case.get("metadata"), Mapping) else {}
    if metadata.get("cohort") == "precursor-genome":
        return _score_precursor_row(
            row,
            metadata,
            report,
            selected_hypothesis,
            variant,
            top_n=phase_agreement_top_n,
            minimum_ratio=phase_agreement_minimum_ratio,
            gate_level=phase_match_level,
        )
    dynamic_truth = _resolve_precursor_truth(case, report)
    if dynamic_truth is not None:
        row["phase_truth_resolution"] = dynamic_truth
        if dynamic_truth.get("status") == "resolved":
            expected = sorted(dynamic_truth["expected_phase_group_weights"])
            row["expected_phase_groups"] = expected
            row["label_completeness"] = "complete"
            expected_weights = dynamic_truth["expected_phase_group_weights"]
        else:
            expected_weights = None
            row["phase_agreement"] = {
                "status": "truth_unresolved",
                "passed": False,
                "source_truth_status": "accepted_human_labels",
                "reference_source": "Precursor human labels",
                "resolution": dynamic_truth,
            }
            row["campaign_passed"] = False
    else:
        expected_weights = metadata.get("expected_phase_group_weights") or metadata.get("expected_phase_weights")
    if isinstance(expected_weights, Mapping):
        truth_status = str(metadata.get("source_truth_status", ""))
        dynamically_resolved = dynamic_truth is not None and dynamic_truth.get("status") == "resolved"
        if (dynamically_resolved or truth_status == "crosswalked") and row["label_completeness"] == "complete":
            try:
                row["phase_agreement"] = evaluate_phase_agreement(
                    expected_weights,
                    row["selected_phase_groups"],
                    top_n=phase_agreement_top_n,
                    minimum_ratio=phase_agreement_minimum_ratio,
                )
            except (TypeError, ValueError) as exc:
                raise WP5CommandError(f"phase_agreement_invalid: {exc}") from exc
            row["campaign_passed"] = bool(row["phase_agreement"].get("passed"))
        else:
            row["phase_agreement"] = {
                "status": "crosswalk_pending",
                "passed": False,
                "source_truth_status": truth_status or "unknown",
                "reference_source": "Precursor human labels",
            }
            row["campaign_passed"] = False
    row["correct"] = row["label_completeness"] == "complete" and set(row["selected_phase_groups"]) == set(expected)
    return row


def _variant_settings(
    protocol: Protocol,
    variant: str,
    radiation: str,
    *,
    reference_source: str,
) -> AnalysisSettings:
    if variant not in protocol.variants:
        raise WP5CommandError(f"variant_invalid: {variant} is not frozen in protocol")
    if variant == "screening":
        mode = "screening"
        residual = False
    else:
        mode = "mixture"
        residual = variant == "full_mixture"
    query = dict(protocol.query)
    preprocessing = dict(protocol.preprocessing)
    lookup_budget = query.get("candidate_lookup_budget", query.get("lookup_budget"))
    evaluation_policy = evaluation_policy_from_query(query)
    query_max = int(query.get("max_phases", 3))
    return AnalysisSettings(
        radiation=radiation,
        angle_unit=AngleUnit.TWO_THETA,
        reference_source=reference_source,
        matching_two_theta_max_deg=float(evaluation_policy["primary_two_theta_max_deg"]),
        analysis_mode=mode,
        residual_candidate_queries=residual,
        candidate_pool=int(query.get("candidate_limit", 100)),
        candidate_retrieval_mode=str(query.get("candidate_retrieval_mode", "bounded_coarse")),
        max_phases=query_max,
        candidate_lookup_budget=None if lookup_budget is None else int(lookup_budget),
        peak_tolerance_deg=float(query.get("peak_tolerance_deg", preprocessing.get("peak_tolerance_deg", 0.25))),
        min_prominence_fraction=float(query.get("min_prominence_fraction", preprocessing.get("min_prominence_fraction", 0.025))),
        max_peaks=int(query.get("max_peaks", preprocessing.get("max_peaks", 40))),
        background_window_points=int(query.get("background_window_points", preprocessing.get("background_window_points", 31))),
        retained_branches=int(query.get("retained_branches", 3)),
        min_independent_evidence=int(query.get("min_independent_evidence", 2)),
        min_objective_improvement=float(query.get("min_objective_improvement", 0.02)),
        complexity_penalty=float(query.get("complexity_penalty", 0.02)),
        ambiguity_margin=float(query.get("ambiguity_margin", 0.01)),
        inactive_scale_relative_tolerance=float(query.get("inactive_scale_relative_tolerance", 1e-6)),
        profile_width_deg=float(query.get("profile_width_deg", 0.20)),
        max_fit_attempts=int(query.get("max_fit_attempts", 300)),
        swap_fit_attempt_budget=int(query.get("swap_fit_attempt_budget", 25)),
    )


_ABLATION_SETTINGS = frozenset(
    {
        "radiation",
        "peak_tolerance_deg",
        "min_prominence_fraction",
        "max_peaks",
        "background_window_points",
        "candidate_pool",
        "candidate_lookup_budget",
        "candidate_retrieval_mode",
        "max_phases",
        "residual_candidate_queries",
        "retained_branches",
        "min_independent_evidence",
        "min_objective_improvement",
        "complexity_penalty",
        "ambiguity_margin",
        "inactive_scale_relative_tolerance",
        "profile_width_deg",
        "max_fit_attempts",
        "swap_fit_attempt_budget",
        "matching_two_theta_max_deg",
    }
)


def _apply_ablation(protocol: Protocol, settings: AnalysisSettings, ablation_id: str | None) -> tuple[AnalysisSettings, dict[str, Any]]:
    if ablation_id is None:
        return settings, {"id": "baseline", "changes": {}}
    for raw in protocol.ablations:
        if not isinstance(raw, Mapping) or raw.get("id") != ablation_id:
            continue
        if not isinstance(raw.get("factor"), str) or not str(raw.get("factor")).strip() or raw.get("factor") == "unspecified":
            raise WP5CommandError(f"ablation_invalid: {ablation_id} factor_missing")
        changes = raw.get("changes", {})
        if not isinstance(changes, Mapping):
            raise WP5CommandError(f"ablation_invalid: {ablation_id} changes must be an object")
        if not changes:
            raise WP5CommandError(f"ablation_invalid: {ablation_id} changes_missing")
        unknown = sorted(set(changes).difference(_ABLATION_SETTINGS))
        if unknown:
            raise WP5CommandError(f"ablation_invalid: unsupported setting(s): {', '.join(unknown)}")
        try:
            updated = replace(settings, **{str(key): value for key, value in changes.items()})
            updated.validate()
        except (TypeError, ValueError) as exc:
            raise WP5CommandError(f"ablation_invalid: {ablation_id}: {exc}") from exc
        return updated, {"id": ablation_id, "changes": dict(changes)}
    raise WP5CommandError(f"ablation_not_declared: {ablation_id}")


def run_bundle(
    bundle_path: Path,
    split: str,
    variant: str,
    output: Path,
    max_cases: int | None = None,
    *,
    reference_source: str = "demo",
    powcod_path: Path | None = None,
    powcod_cache_path: Path | None = None,
    ablation_id: str | None = None,
    settings_overrides: Mapping[str, Any] | None = None,
    case_ids: Sequence[str] | None = None,
    sample_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one variant. ``sample_context`` (optional) maps case IDs to
    synthesis context such as ``allowed_elements``; it never contains labels
    and its content hash is part of the run identity."""
    if split not in {"all", "development", "calibration", "test"}:
        raise WP5CommandError(f"split_invalid: {split}")
    if reference_source not in {"demo", "pow_cod"}:
        raise WP5CommandError(f"reference_source_invalid: {reference_source}")
    bundle, _source, case_manifest, protocol = _load_bundle(bundle_path)
    try:
        evaluation_policy = evaluation_policy_from_query(protocol.query)
    except ValueError as exc:
        raise WP5CommandError(f"evaluation_policy_invalid: {exc}") from exc
    cases = [
        case.to_dict()
        for case in case_manifest.cases
        if case.eligibility == "eligible"
        and (split == "all" or case.split == split)
    ]
    cases = _select_cases_by_id(cases, case_ids)
    if max_cases is not None and case_ids is not None and len(cases) > max_cases:
        raise WP5CommandError("case_selection_invalid: max_cases is smaller than the explicit case selection")
    output = output.expanduser().resolve()
    if output.exists() and (output / "result.json").exists():
        # EvaluationRunner will enforce identity compatibility and resume
        # case artifacts; a pre-existing unrelated directory is rejected.
        pass
    if variant not in protocol.variants:
        raise WP5CommandError(f"variant_invalid: {variant}")
    radiation = protocol.radiations[0]
    settings, ablation = _apply_ablation(
        protocol,
        _variant_settings(protocol, variant, radiation, reference_source=reference_source),
        ablation_id,
    )
    tuning_overrides = dict(settings_overrides or {})
    if tuning_overrides:
        allowed_overrides = {
            "peak_tolerance_deg", "min_prominence_fraction", "max_peaks", "background_window_points",
            "candidate_pool", "candidate_retrieval_mode", "max_phases", "residual_candidate_queries",
            "candidate_lookup_budget",
            "retained_branches", "min_independent_evidence", "min_objective_improvement", "complexity_penalty",
            "ambiguity_margin", "abstain_when_ambiguous", "oxidizing_synthesis", "missing_intensity_max", "inactive_scale_relative_tolerance", "profile_width_deg", "max_fit_attempts",
            "swap_fit_attempt_budget",
            "matching_two_theta_max_deg",
            "peak_detection", "background_window_deg", "peak_min_snr", "peak_min_width_deg",
            "peak_smoothing_window_deg", "peak_min_relative_prominence",
            "profile_width_mode", "profile_eta", "zero_shift_max_deg", "zero_shift_step_deg",
            "displacement_search_max_deg", "displacement_tolerance_deg", "lattice_scale_tolerance",
        }
        unknown_overrides = sorted(set(tuning_overrides).difference(allowed_overrides))
        if unknown_overrides:
            raise WP5CommandError(f"tuning_override_invalid: unsupported setting(s): {', '.join(unknown_overrides)}")
        try:
            settings = replace(settings, **tuning_overrides)
            settings.validate()
        except (TypeError, ValueError) as exc:
            raise WP5CommandError(f"tuning_override_invalid: {exc}") from exc
    settings_hash = canonical_sha256({"variant": variant, "settings": settings.__dict__})
    resolved_powcod_path: Path | None = None
    resolved_powcod_cache: Path | None = None
    if reference_source == "pow_cod":
        if powcod_path is None or powcod_cache_path is None:
            raise WP5CommandError(
                "powcod_paths_required: --powcod-db and --powcod-cache are required when --reference-source=pow_cod"
            )
        resolved_powcod_path = _safe_file_path(powcod_path, code="powcod_database_unavailable")
        resolved_powcod_cache = _safe_file_path(powcod_cache_path, code="powcod_cache_unavailable")
        if resolved_powcod_path.is_symlink() or not resolved_powcod_path.is_file():
            raise WP5CommandError(f"powcod_database_unavailable: {resolved_powcod_path}")
        if resolved_powcod_cache.is_symlink() or not resolved_powcod_cache.is_file():
            raise WP5CommandError(f"powcod_cache_unavailable: {resolved_powcod_cache}")
    reference_path = resolved_powcod_path or (ROOT / "src" / "phasentic" / "resources" / "demo-references.json")
    if not reference_path.is_file():
        raise WP5CommandError(f"reference_index_unavailable: {reference_path}")
    index_hash = sha256_file(reference_path)
    cache_hash = sha256_file(resolved_powcod_cache) if resolved_powcod_cache is not None else None
    try:
        reference_store = open_reference_store(
            settings,
            powcod_path=resolved_powcod_path,
            powcod_cache_path=resolved_powcod_cache,
        )
        reference_provenance = (
            reference_store.provenance()
            if callable(getattr(reference_store, "provenance", None))
            else {"reference_source": "demo", "reference_database": "demo subset"}
        )
    except (ReferenceConfigurationError, OSError, ValueError) as exc:
        close = locals().get("reference_store")
        if close is not None and callable(getattr(close, "close", None)):
            close.close()
        raise WP5CommandError(f"reference_store_unavailable: {exc}") from exc
    # One read-only store serves every case of this invocation: it keeps the
    # SQLite connection, the element-mask and reflection-count vectors, and
    # equivalence sidecar state warm instead of reopening them per case.
    shared_reference_store = reference_store
    protocol_hash = canonical_contract_sha256(protocol.to_dict())
    algorithm_hash = canonical_sha256({"service_algorithm": ALGORITHM_VERSION, "runner_schema": "wp5-run-0.1"})
    environment_hash = canonical_sha256({"python": platform.python_version(), "platform": platform.platform()})
    identity = {
        "settings_hash": settings_hash,
        "index_hash": index_hash,
        "protocol_hash": protocol_hash,
        "algorithm_hash": algorithm_hash,
        "environment_hash": environment_hash,
        "reference_source": reference_source,
        "reference_cache_hash": cache_hash,
        "ablation": ablation,
        "variant": variant,
        "split": split,
        "case_ids": [str(case["case_id"]) for case in cases] if case_ids is not None else None,
        "tuning_overrides": tuning_overrides,
        "sample_context_sha256": (
            canonical_sha256(dict(sample_context)) if sample_context is not None else None
        ),
    }
    context_cases = (sample_context or {}).get("cases", {}) if sample_context is not None else {}

    def _case_settings(case: Mapping[str, Any]) -> AnalysisSettings:
        entry = context_cases.get(str(case.get("case_id"))) if isinstance(context_cases, Mapping) else None
        if not isinstance(entry, Mapping) or not entry.get("allowed_elements"):
            return settings
        from phasentic.domain.formula import normalize_elements

        return replace(settings, allowed_elements=normalize_elements(entry["allowed_elements"]))

    runner = EvaluationRunner(
        output,
        lambda path, case: analyze_file(
            path,
            _case_settings(case),
            powcod_path=resolved_powcod_path,
            powcod_cache_path=resolved_powcod_cache,
            reference_store=shared_reference_store,
        ).to_dict(),
        data_root=bundle_path,
    )
    try:
        run_manifest = runner.run(cases, identity=identity, max_cases=max_cases)
    except (RunnerValidationError, OSError, ValueError) as exc:
        raise WP5CommandError(f"run_failed: {exc}") from exc
    finally:
        if callable(getattr(shared_reference_store, "close", None)):
            shared_reference_store.close()
    rows: list[dict[str, Any]] = []
    for summary in run_manifest.get("cases", []):
        # A bounded invocation may intentionally leave later cases pending.
        # Do not try to read an artifact that the runner has not created yet;
        # the result remains ``running`` and can be resumed under the same
        # identity on the next invocation.
        if summary.get("status") not in {"complete", "failed"}:
            continue
        payload = _load(output / summary["artifact"])
        result = payload.get("result") if payload.get("status") == "complete" else None
        rows.append(
            _analysis_row(
                next(case for case in cases if case["case_id"] == summary["case_id"]),
                result,
                payload.get("error"),
                variant,
                phase_agreement_top_n=int(evaluation_policy["phase_agreement_top_n"]),
                phase_agreement_minimum_ratio=float(evaluation_policy["phase_agreement_minimum_ratio"]),
                phase_match_level=str(evaluation_policy.get("phase_match_level", "strict")),
            )
        )
    rows.sort(key=lambda row: row["case_id"])
    metrics = compute_wp5_metrics(rows)
    bootstrap: dict[str, Any] = {}
    if rows:
        bootstrap["exact_set"] = grouped_bootstrap(
            rows,
            lambda sample: sum(bool(item.get("correct")) for item in sample) / len(sample) if sample else None,
            group_key="group_id",
            n_resamples=int(protocol.bootstrap.get("resamples", 2000)),
            seed=int(protocol.bootstrap.get("seed", 0)),
        )
    result_payload = {
        "schema_version": "wp5-result-0.1",
        "result_id": canonical_sha256({"bundle_id": bundle["bundle_id"], "split": split, "variant": variant, "identity": identity})[:24],
        "status": "complete" if run_manifest.get("status") == "complete" else "running",
        "protocol_id": protocol.protocol_id,
        "case_manifest_id": case_manifest.manifest_id,
        "split": split,
        "variant": variant,
        "implementation": {"algorithm_version": ALGORITHM_VERSION, "runner_identity_sha256": run_manifest["identity_sha256"]},
        "summary": {"case_count": len(rows), "completed_case_count": run_manifest.get("completed_case_count", 0), "failure_count": run_manifest.get("failure_count", 0), "pending_case_count": run_manifest.get("pending_case_count", 0)},
        "cases": rows,
        "metrics": {**metrics, "bootstrap": bootstrap},
        "provenance": {
            "bundle_id": bundle["bundle_id"],
            "protocol_sha256": protocol_hash,
            "reference_source": reference_source,
            "reference_index_sha256": index_hash,
            "reference_cache_sha256": cache_hash,
            "reference_identity": dict(reference_provenance),
            "ablation": ablation,
            "settings_hash": settings_hash,
            "query": dict(protocol.query),
            "evaluation_policy": evaluation_policy,
            "tuning_overrides": tuning_overrides,
            "equivalence_method_version": RuntimeEquivalenceSettings().method_version,
            "equivalence_configuration_sha256": RuntimeEquivalenceSettings().configuration_sha256,
        },
        "limitations": ["This run is a development software-control evaluation.", "No quantitative phase fractions or laboratory accuracy claim is made."],
    }
    write_json_atomic(output / "result.json", result_payload)
    return result_payload



def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="authenticate a source inventory")
    imp.add_argument("--sources", type=Path, required=True)
    imp.add_argument("--data-root", type=Path, required=True)
    imp.add_argument("--output", type=Path, required=True)
    freeze = sub.add_parser("freeze", help="freeze manifests and source bytes into a bundle")
    freeze.add_argument("--cases", type=Path, required=True)
    freeze.add_argument("--protocol", type=Path, required=True)
    freeze.add_argument("--sources", type=Path)
    freeze.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("run", help="run one production-path variant")
    run.add_argument("--bundle", type=Path, required=True)
    run.add_argument(
        "--split",
        required=True,
        help="case partition to evaluate (development, calibration, test, or all eligible cases)",
    )
    run.add_argument("--variant", required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--max-cases", type=int)
    run.add_argument("--case-id", action="append", dest="case_ids", help="explicit eligible case selection; may be repeated")
    run.add_argument("--sample-context", type=Path, help="per-case synthesis context JSON (e.g. allowed elements); never labels")
    run.add_argument("--reference-source", choices=("demo", "pow_cod"), default="demo")
    run.add_argument("--powcod-db", type=Path, help="verified POW_COD SQLite database for --reference-source=pow_cod")
    run.add_argument("--powcod-cache", type=Path, help="verified POW_COD compact cache for --reference-source=pow_cod")
    run.add_argument("--ablation-id", help="declared protocol ablation to run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "import":
            payload = import_sources(args.sources, args.data_root, args.output)
        elif args.command == "freeze":
            payload = freeze_bundle(args.cases, args.protocol, args.output, args.sources)
        else:
            payload = run_bundle(
                args.bundle,
                args.split,
                args.variant,
                args.output,
                args.max_cases,
                reference_source=args.reference_source,
                powcod_path=args.powcod_db,
                powcod_cache_path=args.powcod_cache,
                ablation_id=args.ablation_id,
                case_ids=args.case_ids,
                sample_context=(json.loads(args.sample_context.read_text(encoding="utf-8")) if args.sample_context else None),
            )
    except (WP5CommandError, OSError, ValueError) as exc:
        print(f"WP-5 command failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
