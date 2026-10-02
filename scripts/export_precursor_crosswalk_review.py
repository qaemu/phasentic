#!/usr/bin/env python3
"""Export a reviewer-facing, evidence-only Precursor crosswalk packet.

The packet deliberately preserves the current mapping status.  It adds source
case occurrences and POW_COD candidate metadata so a crystallographer can
review a bounded queue without editing the application runtime or activating a
formula-only guess.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from phasentic.validation.wp5.precursor import validate_precursor_crosswalk


SCHEMA_VERSION = "precursor-crosswalk-review-packet-1"


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "content_sha256"}
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _case_occurrences(case_manifest: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    occurrences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in case_manifest.get("cases", []):
        if not isinstance(case, Mapping):
            continue
        metadata = case.get("metadata")
        if not isinstance(metadata, Mapping) or metadata.get("cohort") != "precursor-genome":
            continue
        labels = set(str(value) for value in metadata.get("source_expected_phase_groups", []) if value)
        for phase in metadata.get("phase_labels_source", []):
            if isinstance(phase, Mapping) and phase.get("name"):
                labels.add(str(phase["name"]))
        for label in sorted(labels):
            weight = None
            expected_weights = metadata.get("expected_phase_weights")
            if isinstance(expected_weights, Mapping):
                weight = expected_weights.get(label)
            for phase in metadata.get("phase_labels_source", []):
                if isinstance(phase, Mapping) and str(phase.get("name", "")) == label:
                    weight = phase.get("weight_percent")
                    break
            occurrences[label].append(
                {
                    "case_id": str(case.get("case_id", "")),
                    "sample_id": str(case.get("sample_id", metadata.get("ledger_sample_id", ""))),
                    "target_compound": metadata.get("target_compound"),
                    "weight_percent": weight,
                }
            )
    return {label: sorted(rows, key=lambda row: (row["case_id"], row["sample_id"])) for label, rows in occurrences.items()}


def _candidate_rows(cache_path: Path, reference_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not reference_ids:
        return {}
    resolved = cache_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"POW_COD cache not found: {resolved}")
    rows: dict[str, dict[str, Any]] = {}
    placeholders = ",".join("?" for _ in reference_ids)
    query = (
        "SELECT reference_id, formula, name, space_group, source_url, reflection_count "
        f"FROM phases WHERE reference_id IN ({placeholders}) ORDER BY reference_id"
    )
    with sqlite3.connect(f"file:{resolved}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute(query, sorted(reference_ids)):
            rows[str(row["reference_id"])] = {
                "reference_id": str(row["reference_id"]),
                "formula": row["formula"],
                "name": row["name"],
                "space_group": row["space_group"],
                "source_url": row["source_url"],
                "reflection_count": row["reflection_count"],
            }
    return rows


def build_review_packet(
    crosswalk: Mapping[str, Any],
    case_manifest: Mapping[str, Any],
    candidate_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    checked = validate_precursor_crosswalk(crosswalk)
    occurrences = _case_occurrences(case_manifest)
    records: list[dict[str, Any]] = []
    for entry in checked["entries"]:
        reference_ids = [str(value) for value in entry.get("candidate_reference_ids", [])]
        candidates = [dict(candidate_rows[reference_id]) for reference_id in reference_ids if reference_id in candidate_rows]
        records.append(
            {
                "source_label": entry["source_label"],
                "formula": entry.get("formula"),
                "normalized_formula": entry.get("normalized_formula"),
                "space_group_number": entry.get("space_group_number"),
                "icsd_id": entry.get("icsd_id"),
                "variant": entry.get("variant"),
                "mapping_status": entry["mapping_status"],
                "canonical_group_id": entry.get("canonical_group_id"),
                "parent_family_group_id": entry.get("parent_family_group_id"),
                "selected_reference_ids": list(entry.get("selected_reference_ids", [])),
                "candidate_reference_ids": reference_ids,
                "candidates": candidates,
                "occurrences": occurrences.get(entry["source_label"], []),
                "evidence": list(entry.get("evidence", [])),
                "notes": entry.get("notes"),
                "review_action": "Select an exact POW_COD reference and canonical group only after crystallographic review; otherwise retain ambiguous or unresolved.",
            }
        )
    records.sort(key=lambda record: record["source_label"])
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "crosswalk_sha256": checked["content_sha256"],
        "source_manifest_sha256": checked["source_manifest_sha256"],
        "powcod_cache_sha256": checked["powcod_cache_sha256"],
        "records": records,
        "summary": {
            "entry_count": len(records),
            "status_counts": dict(sorted(Counter(record["mapping_status"] for record in records).items())),
            "candidate_cardinality_counts": dict(
                sorted(Counter(len(record["candidate_reference_ids"]) for record in records).items())
            ),
            "occurrence_case_count": len({occurrence["case_id"] for record in records for occurrence in record["occurrences"]}),
        },
        "limitations": [
            "This packet is an evidence-only review aid; it is not a scientific crosswalk.",
            "Formula and space-group coincidence do not activate a mapping.",
            "Only an explicit reviewed_exact record may enter strict truth metrics.",
        ],
    }
    packet["content_sha256"] = _canonical_hash(packet)
    return packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--powcod-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    crosswalk = json.loads(args.crosswalk.read_text(encoding="utf-8"))
    case_manifest = json.loads(args.case_manifest.read_text(encoding="utf-8"))
    reference_ids = {
        str(reference_id)
        for entry in crosswalk.get("entries", [])
        for reference_id in entry.get("candidate_reference_ids", [])
    }
    packet = build_review_packet(crosswalk, case_manifest, _candidate_rows(args.powcod_cache, reference_ids))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(packet["summary"], sort_keys=True))
    print(f"content_sha256={packet['content_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
