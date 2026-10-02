#!/usr/bin/env python3
"""Report whether each Precursor label exists in the POW_COD reference at all.

This is an intake check, run once before any campaign. A label with no
chemically compatible POW_COD entry cannot be found by any search setting;
it stays in the campaign denominator but is reported as a reference gap
rather than an algorithm failure. The output is never read by the analysis.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phasentic.validation.wp5.artifacts import write_json_atomic  # noqa: E402
from phasentic.validation.wp5.phase_scoring import (  # noqa: E402
    PHASE_SCORING_VERSION,
    ChemicalPhase,
    composition_fractions,
    labels_from_source,
    match_level,
    space_group_to_number,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_coverage(case_manifest: Path, cache: Path) -> dict:
    manifest = json.loads(case_manifest.read_text(encoding="utf-8"))
    labels: dict[str, ChemicalPhase] = {}
    unparseable: set[str] = set()
    for case in manifest.get("cases", []):
        metadata = case.get("metadata") or {}
        parsed, problems = labels_from_source(
            metadata.get("source_expected_phase_groups") or [], metadata.get("expected_phase_weights") or {}
        )
        for label in parsed:
            labels.setdefault(label.identifier, label)
        unparseable.update(item["source_label"] for item in problems if item["reason"] == "label_unparseable")
    by_elements: dict[frozenset[str], list[ChemicalPhase]] = defaultdict(list)
    for label in labels.values():
        fractions = composition_fractions(label.formula)
        if fractions:
            by_elements[frozenset(fractions)].append(label)
    counts = {identifier: {"strict": 0, "family": 0, "elements": 0} for identifier in labels}
    examples: dict[str, list[str]] = defaultdict(list)
    connection = sqlite3.connect(f"file:{cache}?mode=ro", uri=True)
    space_groups: dict[str, int | None] = {}
    scanned = 0
    for reference_id, formula, space_group in connection.execute(
        "SELECT reference_id, formula, space_group FROM phases"
    ):
        scanned += 1
        fractions = composition_fractions(str(formula or ""))
        if not fractions:
            continue
        candidates = by_elements.get(frozenset(fractions))
        if not candidates:
            continue
        key = str(space_group or "")
        if key not in space_groups:
            space_groups[key] = space_group_to_number(key or None)
        predicted = ChemicalPhase(str(reference_id), str(formula), space_groups[key])
        for label in candidates:
            level = match_level(label, predicted)
            if level is None:
                continue
            counts[label.identifier]["elements"] += 1
            if level in {"family", "strict"}:
                counts[label.identifier]["family"] += 1
            if level == "strict":
                counts[label.identifier]["strict"] += 1
                if len(examples[label.identifier]) < 5:
                    examples[label.identifier].append(str(reference_id))
    connection.close()
    return {
        "schema_version": "precursor-reference-coverage-1",
        "scoring_version": PHASE_SCORING_VERSION,
        "case_manifest_sha256": _sha256(case_manifest),
        "reference_cache_name": cache.name,
        "scanned_reference_count": scanned,
        "label_count": len(labels),
        "labels": {
            identifier: {**counts[identifier], "strict_examples": examples.get(identifier, [])}
            for identifier in sorted(labels)
        },
        "unparseable_labels": sorted(unparseable),
        "labels_absent_at_family_level": sorted(i for i in labels if counts[i]["family"] == 0),
        "semantics": "intake reference-coverage check; never consulted by retrieval, ranking or selection",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--powcod-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build_coverage(args.case_manifest.resolve(), args.powcod_cache.resolve())
    write_json_atomic(args.output, result)
    print(json.dumps({key: result[key] for key in ("label_count", "scanned_reference_count")}))
    print("absent at family level:", len(result["labels_absent_at_family_level"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
