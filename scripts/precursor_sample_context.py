#!/usr/bin/env python3
"""Build per-case sample context (allowed elements) from the Precursor ledger.

The allowed element set for a case is the union of the elements in its
recorded precursors and target compound, plus O, H and C from the furnace
atmosphere (oxides, hydroxides, hydrates and carbonates). This uses synthesis
inputs only; refinement outcomes/labels are never read. The output is a
separate hash-addressed input to benchmark runs; the frozen bundle is not
modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phasentic.domain.formula import normalize_elements, parse_formula  # noqa: E402
from phasentic.validation.wp5.artifacts import write_json_atomic  # noqa: E402

ATMOSPHERE_ELEMENTS = ("O", "H", "C")
SCHEMA_VERSION = "precursor-sample-context-1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_context(ledger_path: Path, case_manifest_path: Path) -> dict:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    samples = {str(sample.get("sample_id")): sample for sample in ledger.get("samples", [])}
    manifest = json.loads(case_manifest_path.read_text(encoding="utf-8"))
    cases: dict[str, dict] = {}
    missing: list[str] = []
    for case in manifest.get("cases", []):
        sample = samples.get(str(case.get("sample_id")))
        if sample is None:
            missing.append(str(case.get("case_id")))
            continue
        elements: set[str] = set(ATMOSPHERE_ELEMENTS)
        sources: list[str] = []
        unparsed: list[str] = []
        for precursor in sample.get("precursors") or []:
            formula = precursor.get("formula_clean") or precursor.get("formula") or ""
            parsed = parse_formula(str(formula))
            if parsed:
                elements.update(parsed)
                sources.append(str(formula))
            else:
                unparsed.append(str(formula))
        target = sample.get("target_compound")
        parsed_target = parse_formula(str(target or ""))
        if parsed_target:
            elements.update(parsed_target)
        cases[str(case["case_id"])] = {
            "allowed_elements": list(normalize_elements(elements)),
            "precursor_formulas": sources,
            "unparsed_precursor_formulas": unparsed,
            "target_compound": target,
        }
    body = {
        "schema_version": SCHEMA_VERSION,
        "rule": "elements(precursors) | elements(target_compound) | {O, H, C}; molecular organics excluded at retrieval",
        "uses_labels": False,
        "ledger_sha256": _sha256(ledger_path),
        "case_manifest_sha256": _sha256(case_manifest_path),
        "cases": dict(sorted(cases.items())),
        "cases_missing_from_ledger": sorted(missing),
    }
    body["content_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    context = build_context(args.ledger.resolve(), args.case_manifest.resolve())
    write_json_atomic(args.output, context)
    print(json.dumps({"cases": len(context["cases"]), "missing": context["cases_missing_from_ledger"], "content_sha256": context["content_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
