#!/usr/bin/env python3
"""Create an evidence-only Precursor-to-POW_COD crosswalk draft.

The generated file never activates a mapping.  Unique formula/space-group
matches remain ``unresolved`` until a crystallographic reviewer records an
explicit ``reviewed_exact`` decision; multiple matches remain ``ambiguous``.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phasentic.validation.wp5.artifacts import sha256_file, write_json_atomic
from phasentic.validation.wp5.contracts import canonical_contract_sha256
from phasentic.validation.wp5.precursor import (
    PrecursorCrosswalkError,
    build_precursor_crosswalk,
    suggest_powcod_candidates,
)


def _load(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrecursorCrosswalkError(f"read_failed: {path}") from exc
    if not isinstance(value, Mapping):
        raise PrecursorCrosswalkError(f"object_required: {path}")
    return value


def build_draft(case_manifest_path: str | Path, source_manifest_path: str | Path, cache_manifest_path: str | Path, cache_path: str | Path) -> dict[str, Any]:
    case_manifest = _load(Path(case_manifest_path).expanduser().resolve())
    source_manifest = _load(Path(source_manifest_path).expanduser().resolve())
    cache_manifest = _load(Path(cache_manifest_path).expanduser().resolve())
    labels: set[str] = set()
    for case in case_manifest.get("cases", []):
        if not isinstance(case, Mapping):
            continue
        metadata = case.get("metadata")
        if not isinstance(metadata, Mapping) or metadata.get("cohort") != "precursor-genome":
            continue
        labels.update(str(item) for item in metadata.get("source_expected_phase_groups", []) if isinstance(item, str) and item.strip())
    if not labels:
        raise PrecursorCrosswalkError("source_labels_empty: case manifest contains no Precursor labels")
    suggestions = suggest_powcod_candidates(cache_path, sorted(labels))
    source_hash = canonical_contract_sha256(source_manifest)
    cache_hash = cache_manifest.get("cache_sha256")
    if not isinstance(cache_hash, str) or len(cache_hash) != 64:
        raise PrecursorCrosswalkError("cache_manifest_hash_missing: cache_sha256 is required")
    crosswalk = build_precursor_crosswalk(
        sorted(labels),
        suggestions,
        source_manifest_sha256=source_hash,
        powcod_cache_sha256=cache_hash.lower(),
        status="draft",
        limitations=(
            "This draft contains algorithmic suggestions only.",
            "No formula/space-group coincidence activates strict truth.",
            "A crystallographic reviewer must select an exact POW_COD reference or retain unresolved/ambiguous status.",
        ),
    )
    crosswalk["metadata"] = {
        "source_manifest_sha256": source_hash,
        "powcod_cache_sha256": cache_hash.lower(),
        "powcod_cache_path_sha256": sha256_file(Path(cache_path).expanduser().resolve()),
        "candidate_method": "formula_and_space_group_only",
        "label_count": len(labels),
        "suggestion_status_counts": dict(sorted(Counter(item["mapping_status"] for item in crosswalk["entries"]).items())),
    }
    # Recompute content hash with metadata included; the validator intentionally
    # rejects unknown top-level fields, so metadata is kept in the review
    # receipt instead of the strict crosswalk file.
    crosswalk.pop("metadata", None)
    return crosswalk


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--cache-manifest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = build_draft(args.case_manifest, args.source_manifest, args.cache_manifest, args.cache)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(args.output, payload)
        print(json.dumps({"entry_count": len(payload["entries"]), "status_counts": dict(Counter(item["mapping_status"] for item in payload["entries"]))}, sort_keys=True))
    except (PrecursorCrosswalkError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

