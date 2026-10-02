#!/usr/bin/env python3
"""Activate a reviewed Precursor/POW_COD crosswalk for the 100-case campaign.

The generated bundle keeps all 100 cases in the declared development split.
Only an explicitly frozen or validated crosswalk may be activated; unresolved
labels remain visible and keep native tuning blocked until every case has
reviewed exact truth.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.benchmark_wp5 import freeze_bundle
from phasentic.validation.wp5.artifacts import canonical_sha256, write_json_atomic
from phasentic.validation.wp5.contracts import canonical_contract_sha256, validate_case_manifest, validate_protocol
from phasentic.validation.wp5.precursor import (
    PrecursorCrosswalkError,
    build_precursor_split,
    enrich_precursor_case_manifest,
    validate_precursor_crosswalk,
)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrecursorCrosswalkError(f"read_failed: {path}") from exc
    if not isinstance(value, dict):
        raise PrecursorCrosswalkError(f"object_required: {path}")
    return value


def _source_labels(cases: list[Mapping[str, Any]]) -> set[str]:
    labels: set[str] = set()
    for case in cases:
        metadata = case.get("metadata")
        if not isinstance(metadata, Mapping) or metadata.get("cohort") != "precursor-genome":
            continue
        values = metadata.get("source_expected_phase_groups", [])
        if isinstance(values, list):
            labels.update(str(value) for value in values if isinstance(value, str) and value.strip())
    return labels


def activate_precursor_crosswalk(
    bundle: str | Path,
    crosswalk: str | Path,
    output: str | Path,
    *,
    seed: int = 17,
    powcod_manifest: str | Path | None = None,
    receipt: str | Path | None = None,
) -> dict[str, Any]:
    base = Path(bundle).expanduser().resolve()
    crosswalk_path = Path(crosswalk).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    source_manifest = _load(base / "source-manifest.json")
    base_cases = _load(base / "case-manifest.json")
    base_protocol = _load(base / "protocol.json")
    checked = validate_precursor_crosswalk(_load(crosswalk_path))
    if checked["status"] not in {"frozen", "validated"}:
        raise PrecursorCrosswalkError("crosswalk_not_final: status must be frozen or validated")

    source_hash = canonical_contract_sha256(source_manifest)
    if source_hash != checked["source_manifest_sha256"]:
        raise PrecursorCrosswalkError("source_manifest_hash_mismatch: crosswalk is bound to another bundle")
    if powcod_manifest is not None:
        powcod = _load(Path(powcod_manifest).expanduser().resolve())
        declared = powcod.get("cache_sha256")
        if not isinstance(declared, str) or declared.lower() != checked["powcod_cache_sha256"]:
            raise PrecursorCrosswalkError("powcod_cache_hash_mismatch: crosswalk and local cache manifest differ")

    raw_cases = [case for case in base_cases.get("cases", []) if isinstance(case, dict)]
    precursor_cases = [
        case for case in raw_cases
        if isinstance(case.get("metadata"), Mapping) and case["metadata"].get("cohort") == "precursor-genome"
    ]
    if not precursor_cases:
        raise PrecursorCrosswalkError("precursor_cases_empty: bundle has no Precursor cases")
    labels = _source_labels(precursor_cases)
    entry_labels = {str(entry.get("source_label")) for entry in checked["entries"]}
    missing = sorted(labels - entry_labels)
    if missing:
        raise PrecursorCrosswalkError(f"crosswalk_labels_missing: {', '.join(missing[:5])}")

    split = build_precursor_split(
        precursor_cases,
        training_count=len(precursor_cases),
        holdout_count=0,
        seed=seed,
    )
    enriched = enrich_precursor_case_manifest(raw_cases, checked, split)
    case_manifest = copy.deepcopy(base_cases)
    case_manifest["cases"] = enriched["cases"]
    case_manifest["manifest_id"] = f"precursor-cases-crosswalk-{checked['content_sha256'][:12]}"
    case_manifest["metadata"] = {
        **dict(case_manifest.get("metadata", {})),
        "precursor_crosswalk_sha256": checked["content_sha256"],
        "precursor_split_sha256": enriched["split_sha256"],
        "selected_count": len(precursor_cases),
        "strict_truth_status": "complete" if enriched["strict_truth_case_count"] == len(precursor_cases) else "partial",
    }
    validate_case_manifest(case_manifest)

    protocol = copy.deepcopy(base_protocol)
    protocol["protocol_id"] = f"precursor-campaign-v1-crosswalk-{checked['content_sha256'][:12]}"
    protocol["case_manifest_id"] = case_manifest["manifest_id"]
    protocol["split_policy"] = {
        **dict(protocol.get("split_policy", {})),
        "tracks": [],
        "precursor_split": "all_development_frozen_replay",
        "precursor_split_method": "all-development-v1",
        "precursor_split_sha256": enriched["split_sha256"],
    }
    protocol["metadata"] = {
        **dict(protocol.get("metadata", {})),
        "precursor_crosswalk_sha256": checked["content_sha256"],
        "powcod_cache_sha256": checked["powcod_cache_sha256"],
        "precursor_split_sha256": enriched["split_sha256"],
        "strict_truth_case_count": enriched["strict_truth_case_count"],
        "all_cases_development_only": True,
    }
    protocol["limitations"] = list(dict.fromkeys(list(protocol.get("limitations", [])) + [
        "All 100 cases remain development material during native tuning; replay is frozen and descriptive.",
        "Only reviewed_exact crosswalk entries contribute to strict phase agreement.",
    ]))
    validate_protocol(protocol)

    if output_path.exists() and any(output_path.iterdir()):
        raise PrecursorCrosswalkError(f"output_exists: refusing to overwrite {output_path}")
    with tempfile.TemporaryDirectory(prefix="xrd-precursor-crosswalk-") as temporary:
        temporary_root = Path(temporary)
        case_path = temporary_root / "case-manifest.json"
        protocol_path = temporary_root / "protocol.json"
        case_path.write_text(json.dumps(case_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        protocol_path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        frozen = freeze_bundle(case_path, protocol_path, output_path, source_path=base / "source-manifest.json")

    receipt_payload: dict[str, Any] = {
        "schema_version": "precursor-crosswalk-activation-receipt-1",
        "status": "activated" if enriched["strict_truth_case_count"] == len(precursor_cases) else "activated_partial",
        "bundle_id": frozen["bundle_id"],
        "bundle_path": str(output_path),
        "source_manifest_sha256": source_hash,
        "crosswalk_sha256": checked["content_sha256"],
        "powcod_cache_sha256": checked["powcod_cache_sha256"],
        "split": split,
        "selected_count": len(precursor_cases),
        "strict_truth_case_count": enriched["strict_truth_case_count"],
        "dara_controls_parameters": False,
        "limitations": [
            "Activation authenticates the software-evaluation bundle; it is not laboratory validation.",
            "Native tuning remains blocked until every selected case has complete reviewed_exact truth.",
        ],
    }
    receipt_payload["receipt_sha256"] = canonical_sha256(receipt_payload)
    if receipt is not None:
        write_json_atomic(Path(receipt).expanduser().resolve(), receipt_payload)
    return receipt_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--powcod-manifest", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    try:
        payload = activate_precursor_crosswalk(
            args.bundle,
            args.crosswalk,
            args.output,
            seed=args.seed,
            powcod_manifest=args.powcod_manifest,
            receipt=args.receipt,
        )
    except (PrecursorCrosswalkError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
