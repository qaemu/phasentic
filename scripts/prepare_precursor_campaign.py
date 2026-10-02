#!/usr/bin/env python3
"""Prepare a hash-authenticated 100-case Precursor campaign intake.

The command consumes the official Precursor ledger and an already downloaded
raw-scan tree.  It copies only the selected raw files into a new intake
directory, writes strict WP-5 source/case manifests, and leaves ICSD to
POW_COD mapping explicitly unresolved until a reviewed crosswalk is supplied.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phasentic.validation.wp5.acquisition import inventory_source_manifest, write_source_manifest
from phasentic.validation.wp5.artifacts import canonical_sha256, write_json_atomic
from phasentic.validation.wp5.contracts import (
    CASE_MANIFEST_SCHEMA_VERSION,
    PROTOCOL_SCHEMA_VERSION,
    canonical_contract_sha256,
    validate_case_manifest,
    validate_protocol,
)
from phasentic.validation.wp5.precursor_campaign import PrecursorCampaignError, select_precursor_cases


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_identifier(value: Any, prefix: str = "id") -> str:
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value)).strip("_")
    if not text or not text[0].isalnum():
        text = f"{prefix}-{text}" if text else prefix
    return text[:128]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrecursorCampaignError(f"read_failed: {path}") from exc
    if not isinstance(value, Mapping):
        raise PrecursorCampaignError(f"object_required: {path}")
    return value


def _copy_selected(raw_root: Path, destination: Path, selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    destination.mkdir(parents=True, exist_ok=False)
    raw_destination = destination / "data" / "raw_scans"
    raw_destination.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for item in selected:
        source = (raw_root / str(item["raw_path"])).resolve()
        try:
            source.relative_to(raw_root.resolve())
        except ValueError as exc:
            raise PrecursorCampaignError(f"raw_path_escape: {item['sample_id']}") from exc
        if not source.is_file() or source.is_symlink():
            raise PrecursorCampaignError(f"raw_file_unavailable: {item['sample_id']}")
        suffix = source.suffix.lower() or ".xrdml"
        filename = f"{item['case_id']}{suffix}"
        target = raw_destination / filename
        shutil.copyfile(source, target)
        updated = dict(item)
        updated["raw_path"] = f"data/raw_scans/{filename}"
        updated["original_raw_path"] = item["raw_path"]
        copied.append(updated)
    return copied


def _source_records(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in cases:
        records.append(
            {
                "source_id": item["case_id"],
                "kind": "measured_scan",
                "source_url": item["raw_archive_source"],
                "original_filename": Path(str(item["original_raw_path"])).name,
                "local_path": item["raw_path"],
                "expected_sha256": item["raw_sha256"],
                "expected_size_bytes": item["raw_size_bytes"],
                "accessed_at": item.get("accessed_at"),
                "license_status": "open",
                "license_evidence_url": item["license_url"],
                "attribution": "Precursor Genome, Lauren Walters et al.; CC BY 4.0",
                "local_use_status": "allowed",
                "redistribution_status": "allowed",
                "instrument_metadata_source": "Precursor Genome ledger",
                "status": "eligible",
                "reason": "accepted active Precursor scan selected for WP-5 development campaign",
                "label_status": "complete",
                "label_evidence": [
                    {
                        "kind": "precursor-ledger-refinement",
                        "sample_id": item["sample_id"],
                        "human_quality_score": item["human_quality_score"],
                    }
                ],
                "metadata": {
                    "cohort": "precursor-genome",
                    "sample_id": item["sample_id"],
                    "radiation": item["radiation"],
                    "geometry": item["geometry"],
                    "angle_unit": item["angle_unit"],
                    "scan_range_deg": item["scan_range_deg"],
                    "source_phase_labels": item["source_phase_labels"],
                    "expected_phase_weights": item["expected_phase_weights"],
                    "human_quality_score": item["human_quality_score"],
                    "human_quality_score_history": item["human_quality_score_history"],
                    "raw_archive_source": item["raw_archive_source"],
                },
            }
        )
    return records


def _case_records(cases: list[dict[str, Any]], split: str = "development") -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in cases:
        family = f"precursor:sample:{item['sample_id'].lower()}"
        output.append(
            {
                "case_id": item["case_id"],
                "sample_id": item["sample_id"],
                "scan_id": _safe_identifier(item["scan_id"], "scan"),
                "replicate_id": None,
                "source_ids": [item["case_id"]],
                "raw_path": item["raw_path"],
                "raw_sha256": item["raw_sha256"],
                "normalized_path": None,
                "normalized_sha256": None,
                "data_kind": "measured",
                "angle_unit": item["angle_unit"],
                "radiation": item["radiation"],
                "geometry": item["geometry"],
                "scan_range_deg": item["scan_range_deg"],
                "acquisition_id": f"precursor:{item['sample_id'].lower()}",
                "instrument_id": item.get("instrument_profile") or "precursor-aeris",
                "profile_id": None,
                "calibration_artifact_id": None,
                "expected_phase_groups": [],
                "expected_parent_family_groups": [],
                "uncertain_phase_groups": list(item["source_phase_labels"]),
                "label_completeness": "incomplete",
                "label_provenance": [
                    "Precursor Genome accepted human refinement; strict POW_COD crosswalk pending review"
                ],
                "family_group_ids": [family],
                "duplicate_group_id": None,
                "parent_group_id": family,
                "split": split,
                "eligibility": "eligible",
                "eligibility_reasons": [],
                "strata": {
                    "cohort": "precursor-genome",
                    "phase_count": item["phase_count"],
                    "phase_stratum": item["phase_stratum"],
                    "human_quality_score": item["human_quality_score"],
                },
                "metadata": {
                    "cohort": "precursor-genome",
                    "source_expected_phase_groups": list(item["source_phase_labels"]),
                    "expected_phase_weights": dict(item["expected_phase_weights"]),
                    "human_quality_score": item["human_quality_score"],
                    "human_quality_score_history": list(item["human_quality_score_history"]),
                    "refinement_rank": item["refinement_rank"],
                    "refinement_rwp": item["refinement_rwp"],
                    "refinement_origin": item["refinement_origin"],
                    "source_truth_status": "accepted_human_labels_pending_powcod_crosswalk",
                    "crosswalk_policy": "reviewed_exact_only",
                },
            }
        )
    return output


def _protocol(source_id: str, case_id: str, selection: Mapping[str, Any], *, created_at: str, split: str = "development") -> dict[str, Any]:
    protocol_id = f"precursor-campaign-v1-{str(selection['manifest_sha256'])[:12]}"
    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "protocol_id": protocol_id,
        "status": "frozen",
        "created_at": created_at,
        "source_manifest_id": source_id,
        "case_manifest_id": case_id,
        "angle_unit": "two_theta",
        "geometry": "reflection_bragg_brentano",
        "radiations": ["Cu Ka"],
        "reference_snapshot": "pow_cod-2205",
        "variants": ["screening", "joint_no_requery", "full_mixture"],
        "preprocessing": {
            "background_policy": "production-default",
            "calibration_policy": "record-status",
            "peak_tolerance_deg": 0.25,
            "min_prominence_fraction": 0.01,
            "max_peaks": 80,
            "background_window_points": 51,
        },
        "query": {
            "candidate_limit": 200,
            "candidate_retrieval_mode": "bounded_coarse",
            "max_phases": 10,
            "retained_branches": 5,
            "min_independent_evidence": 2,
            "min_objective_improvement": 0.02,
            "complexity_penalty": 0.02,
            "ambiguity_margin": 0.01,
            "inactive_scale_relative_tolerance": 1e-6,
            "profile_width_deg": 0.20,
            "max_fit_attempts": 300,
            "primary_two_theta_max_deg": 100.0,
            "phase_agreement_top_n": 5,
            "phase_agreement_minimum_ratio": 0.8,
        },
        "split_policy": {
            "tracks": [],
            "minimum_independent_groups": 3,
            "precursor_campaign": "all_selected_cases_are_development_only_until_crosswalk_and_freeze",
        },
        "ablations": [],
        "resource_budgets": {"timeout_seconds": 300, "max_rss_bytes": 2_000_000_000},
        "bootstrap": {"method": "cluster", "seed": 20260926, "resamples": 1000},
        "implementation": {
            "algorithm_version": "precursor-campaign-v1",
            "environment_sha256": "0" * 64,
        },
        "metadata": {
            "selection_manifest_sha256": selection["manifest_sha256"],
            "tuning_policy": "all_100_development_then_frozen_replay",
            "evaluation_scope": "all_cases",
            "replay_required": True,
            "success_condition": "all_development_cases_pass_in_one_batch_then_clean_replay",
            "max_phases": 10,
            "dara_controls_parameters": False,
            "crosswalk_required_for_canonical_comparison": True,
        },
        "limitations": [
            "Accepted human labels are the declared development reference outcome; a complete deterministic POW_COD equivalence crosswalk is still required for canonical comparison.",
            "All selected cases are development material during parameter search; held-out evaluation is a later declared run.",
            "This is software-evaluation evidence, not laboratory validation or quantitative phase-fraction certification.",
        ],
    }


def prepare_precursor_campaign(
    ledger_path: str | Path,
    raw_root: str | Path,
    output: str | Path,
    *,
    count: int = 100,
    seed: int = 17,
    max_human_quality_score: int = 1,
    created_at: str | None = None,
    exclude_sample_ids: list[str] | None = None,
    split: str = "development",
) -> dict[str, Any]:
    if split not in {"development", "test"}:
        raise PrecursorCampaignError(f"split_invalid: {split}")
    ledger_path = Path(ledger_path).expanduser().resolve()
    raw_root = Path(raw_root).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise PrecursorCampaignError(f"output_exists: refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    selection = select_precursor_cases(
        _load_json(ledger_path),
        raw_root,
        count=count,
        seed=seed,
        max_human_quality_score=max_human_quality_score,
        exclude_sample_ids=exclude_sample_ids,
    )
    copied = _copy_selected(raw_root, output, list(selection["selected_cases"]))
    selection = dict(selection)
    selection["selected_cases"] = copied
    selection["manifest_sha256"] = canonical_sha256({key: value for key, value in selection.items() if key != "manifest_sha256"})
    write_json_atomic(output / "selection.json", selection)

    created = created_at or _now()
    source_id = f"precursor-sources-{selection['manifest_sha256'][:12]}"
    source = inventory_source_manifest(
        output,
        _source_records(copied),
        manifest_id=source_id,
        data_root="data",
        created_at=created,
        metadata={
            "cohort": "precursor-genome",
            "selection_manifest_sha256": selection["manifest_sha256"],
            "raw_ledger_sha256": _sha256(ledger_path),
            "license": "CC BY 4.0",
        },
    )
    write_source_manifest(output / "source-manifest.json", source)

    case_id = f"precursor-cases-{selection['manifest_sha256'][:12]}"
    case_payload = {
        "schema_version": CASE_MANIFEST_SCHEMA_VERSION,
        "manifest_id": case_id,
        "status": "frozen",
        "source_manifest_id": source.manifest_id,
        "created_at": created,
        "cases": _case_records(copied, split),
        "metadata": {
            "cohort": "precursor-genome",
            "selection_manifest_sha256": selection["manifest_sha256"],
            "selected_count": len(copied),
            "strict_truth_status": "pending_powcod_crosswalk",
        },
    }
    validate_case_manifest(case_payload)
    write_json_atomic(output / "case-manifest.json", case_payload)

    protocol_payload = _protocol(source.manifest_id, case_id, selection, created_at=created, split=split)
    if split == "test":
        protocol_payload["split_policy"]["precursor_campaign"] = "sealed_holdout_scored_once_after_frozen_replay"
        protocol_payload["metadata"].update(
            {
                "tuning_policy": "sealed_holdout_never_used_for_tuning",
                "evaluation_scope": "one_shot_after_parameters_frozen",
                "success_condition": "declared_target_in_docs_wp5_remediation_plan",
            }
        )
        protocol_payload["limitations"] = [
            "Sealed held-out cohort: never inspected, scored or used for tuning until one declared run with frozen parameters.",
            "This is software-evaluation evidence, not laboratory validation or quantitative phase-fraction certification.",
        ]
    validate_protocol(protocol_payload)
    write_json_atomic(output / "protocol.json", protocol_payload)
    receipt = {
        "schema_version": "wp5-precursor-campaign-receipt-1",
        "status": "intake_ready_crosswalk_pending",
        "selection_manifest_sha256": selection["manifest_sha256"],
        "source_manifest_sha256": canonical_contract_sha256(source.to_dict()),
        "case_manifest_sha256": canonical_contract_sha256(case_payload),
        "protocol_sha256": canonical_contract_sha256(protocol_payload),
        "selected_count": len(copied),
        "eligible_count": selection["eligible_count"],
        "excluded_counts": selection["excluded_counts"],
        "limitations": [
            "No strict accuracy score is reported until source labels are explicitly crosswalked to POW_COD equivalence groups.",
            "The campaign does not alter the preserved calibration artifact.",
        ],
    }
    receipt["receipt_sha256"] = canonical_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    write_json_atomic(output / "receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-human-quality-score", type=int, default=1)
    parser.add_argument(
        "--exclude-selection",
        type=Path,
        action="append",
        default=[],
        help="selection.json of another cohort whose samples must not be reused (repeatable)",
    )
    parser.add_argument("--split", choices=("development", "test"), default="development")
    args = parser.parse_args()
    excluded_ids: list[str] = []
    for selection_path in args.exclude_selection:
        excluded_ids.extend(
            str(item["sample_id"]) for item in _load_json(selection_path).get("selected_cases", [])
        )
    try:
        print(json.dumps(
            prepare_precursor_campaign(
                args.ledger,
                args.raw_root,
                args.output,
                count=args.count,
                seed=args.seed,
                max_human_quality_score=args.max_human_quality_score,
                exclude_sample_ids=excluded_ids or None,
                split=args.split,
            ),
            indent=2,
            sort_keys=True,
        ))
    except (PrecursorCampaignError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
