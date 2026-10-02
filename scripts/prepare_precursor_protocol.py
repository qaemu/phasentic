#!/usr/bin/env python3
"""Prepare the frozen Precursor 35/15 development and holdout bundle.

This command does not edit the downloaded source bundle.  It derives a new
case manifest from the immutable public-100 bundle, applies only reviewed
crosswalk entries, and asks the existing WP-5 freezer to authenticate every
source byte again.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

# ``python scripts/prepare_precursor_protocol.py`` places ``scripts/`` first
# on sys.path; add the repository root so the existing benchmark module is
# importable without requiring the project to be installed in editable mode.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_wp5 import freeze_bundle
from phasentic.validation.wp5.contracts import canonical_contract_sha256
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


def prepare_precursor_bundle(
    bundle: Path,
    crosswalk_path: Path,
    output: Path,
    *,
    training_count: int = 35,
    holdout_count: int = 15,
    seed: int = 17,
    receipt: Path | None = None,
) -> dict[str, Any]:
    base = bundle.expanduser().resolve()
    source_manifest = _load(base / "source-manifest.json")
    base_cases = _load(base / "case-manifest.json")
    base_protocol = _load(base / "protocol.json")
    crosswalk = validate_precursor_crosswalk(_load(crosswalk_path.expanduser().resolve()))
    source_hash = canonical_contract_sha256(source_manifest)
    if source_hash != crosswalk["source_manifest_sha256"]:
        raise PrecursorCrosswalkError("source_manifest_hash_mismatch: crosswalk is bound to another source bundle")
    precursor_cases = [
        case for case in base_cases.get("cases", [])
        if isinstance(case, dict) and case.get("metadata", {}).get("cohort") == "precursor-genome"
    ]
    if len(precursor_cases) != 50:
        raise PrecursorCrosswalkError(f"precursor_case_count_invalid: expected 50, found {len(precursor_cases)}")
    split = build_precursor_split(
        precursor_cases,
        training_count=training_count,
        holdout_count=holdout_count,
        seed=seed,
    )
    enriched = enrich_precursor_case_manifest(base_cases["cases"], crosswalk, split)
    case_manifest = copy.deepcopy(base_cases)
    case_manifest["cases"] = enriched["cases"]
    case_manifest["manifest_id"] = f"wp5-public-100-precursor-35-15-{split['split_sha256'][:12]}"
    case_manifest["metadata"] = {
        **dict(case_manifest.get("metadata", {})),
        "precursor_crosswalk_sha256": crosswalk["content_sha256"],
        "precursor_split_sha256": split["split_sha256"],
        "precursor_training_case_count": training_count,
        "precursor_holdout_case_count": holdout_count,
        "precursor_tuning_policy": "training split only; held-out test is untouched",
    }
    protocol = copy.deepcopy(base_protocol)
    protocol["protocol_id"] = f"wp5-public-100-precursor-35-15-{split['split_sha256'][:12]}"
    protocol["case_manifest_id"] = case_manifest["manifest_id"]
    protocol["metadata"] = {
        **dict(protocol.get("metadata", {})),
        "precursor_crosswalk_sha256": crosswalk["content_sha256"],
        "precursor_split_sha256": split["split_sha256"],
        "precursor_training_case_count": training_count,
        "precursor_holdout_case_count": holdout_count,
        "dara_controls_parameters": False,
        "powcod_cache_content_sha256": crosswalk["powcod_cache_sha256"],
    }
    # The original 100-case protocol declares instrument/joint tracks.  The
    # Precursor split is a within-instrument 35/15 development/holdout and is
    # intentionally not advertised as an instrument-held-out track.  Keeping
    # only the family track makes that boundary explicit instead of allowing
    # the freezer to silently accept a contradictory split.
    protocol["split_policy"] = {
        **dict(protocol.get("split_policy", {})),
        "tracks": ["family-held-out"],
        "precursor_split": "stratified_35_15",
        "precursor_split_method": "stratified-sha256-v1",
    }
    protocol["limitations"] = list(dict.fromkeys(list(protocol.get("limitations", [])) + [
        "Precursor strict truth is activated only for reviewed_exact crosswalk entries.",
        "The 35-case development split is the only data permitted for native parameter selection.",
        "The 15-case Precursor holdout and external cohorts are evaluated only after parameters are frozen.",
        "DARA remains an optional diagnostic archive and cannot control native parameters.",
    ]))
    output = output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise PrecursorCrosswalkError(f"output_exists: refusing to overwrite {output}")
    with tempfile.TemporaryDirectory(prefix="xrd-precursor-protocol-") as temporary:
        temporary_root = Path(temporary)
        case_path = temporary_root / "case-manifest.json"
        protocol_path = temporary_root / "protocol.json"
        case_path.write_text(json.dumps(case_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        protocol_path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        frozen = freeze_bundle(case_path, protocol_path, output, source_path=base / "source-manifest.json")
    receipt_payload = {
        "schema_version": "precursor-protocol-receipt-1",
        "bundle_id": frozen["bundle_id"],
        "bundle_path": str(output),
        "source_manifest_sha256": source_hash,
        "crosswalk_sha256": crosswalk["content_sha256"],
        "split": split,
        "case_manifest_id": case_manifest["manifest_id"],
        "protocol_id": protocol["protocol_id"],
        "training_case_count": training_count,
        "holdout_case_count": holdout_count,
        "strict_truth_case_count": enriched["strict_truth_case_count"],
        "dara_controls_parameters": False,
        "limitations": [
            "This receipt authenticates the derived software-evaluation bundle; it is not a laboratory validation certificate.",
            "Unresolved and ambiguous source labels remain retained in case metadata and are excluded from strict truth.",
        ],
    }
    if receipt is not None:
        receipt = receipt.expanduser().resolve()
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--training-count", type=int, default=35)
    parser.add_argument("--holdout-count", type=int, default=15)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    try:
        payload = prepare_precursor_bundle(
            args.bundle,
            args.crosswalk,
            args.output,
            training_count=args.training_count,
            holdout_count=args.holdout_count,
            seed=args.seed,
            receipt=args.receipt,
        )
    except (PrecursorCrosswalkError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
