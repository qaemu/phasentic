"""Small, permanently-development WP-5 pilot built from permitted fixtures."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import artifact_record, canonical_sha256, write_json_atomic


class WP5PilotError(ValueError):
    """Raised when the local pilot inputs cannot be assembled safely."""


_PILOT_SOURCES = (
    ("pilot-single-silicon", Path("examples/patterns/silicon-cu-ka.xy"), "single"),
    (
        "pilot-binary-silicon-quartz",
        Path("benchmarks/fixtures/pilot/binary-silicon-quartz.xy"),
        "mixture",
    ),
    (
        "pilot-negative-noise",
        Path("benchmarks/fixtures/pilot/noise-only.xy"),
        "negative",
    ),
)
_VOLATILE_METADATA_ARTIFACTS = frozenset({"source-manifest.json", "case-manifest.json", "protocol.json"})


def _stable_metadata_hash(path: Path) -> str:
    """Hash generated metadata after removing its run-creation timestamp.

    The files remain recorded with their byte hashes for audit.  The pilot's
    semantic content hash must describe the protocol and case/source content,
    however, rather than the wall-clock second in which the bundle was built.
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WP5PilotError(f"generated metadata is not valid JSON: {path.name}") from exc

    def without_creation_timestamps(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): without_creation_timestamps(item)
                for key, item in value.items()
                if key not in {"created_at", "created_at_utc"}
            }
        if isinstance(value, list):
            return [without_creation_timestamps(item) for item in value]
        return value

    return canonical_sha256(without_creation_timestamps(payload))


def _source_record(source_id: str, destination: Path, kind: str, root: Path) -> dict[str, Any]:
    record = artifact_record(destination, root, kind="scan")
    normalization = {"version": "identity-0.1", "sha256": canonical_sha256({"version": "identity-0.1", "input_format": "xy"})}
    return {
        "source_id": source_id,
        "kind": "project_authored_synthetic_scan",
        "source_url": "local-project://phasentic/wp5-pilot",
        "doi": None,
        "original_filename": destination.name,
        "local_path": record["path"],
        "size_bytes": record["size_bytes"],
        "sha256": record["sha256"],
        "license_status": "open",
        "license_evidence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "attribution": "Phasentic project-authored synthetic software-control fixture",
        "local_use_status": "allowed",
        "redistribution_status": "allowed",
        "instrument_metadata_source": "WP-5 pilot protocol",
        "normalization": normalization,
        "status": "eligible",
        "reason": "Project-authored CC0 pilot source with complete byte identity.",
        "label_status": "complete",
        "label_evidence": [{"kind": "project_control", "details": "Expected phase labels are inherited from the WP-4 software-control recipe; not experimental truth."}],
        "metadata": {"source_format": "xy", "pilot_kind": kind},
    }


def build_wp5_pilot(root: Path, output_dir: Path) -> dict[str, Any]:
    """Create a self-contained three-case pilot from existing CC0 fixtures."""

    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise WP5PilotError(f"pilot output already contains files: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = output_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    sources: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    for source_id, source_relative, kind in _PILOT_SOURCES:
        source = root / source_relative
        if not source.is_file() or source.is_symlink():
            raise WP5PilotError(f"pilot source is missing or unsafe: {source_relative}")
        destination = inputs / source.name
        shutil.copyfile(source, destination)
        record = _source_record(source_id, destination, kind, output_dir)
        sources.append(record)
        expected = {
            "single": ["cod-9008566"],
            "mixture": ["cod-9008566", "cod-9000517"],
            "negative": [],
        }[kind]
        cases.append(
            {
                "case_id": source_id,
                "sample_id": source_id,
                "replicate_id": "replicate-01",
                "scan_id": source_id,
                "source_ids": [source_id],
                "raw_path": record["local_path"],
                "raw_sha256": record["sha256"],
                "normalized_path": None,
                "normalized_sha256": None,
                "data_kind": "synthetic" if kind != "negative" else "synthetic_negative",
                "kind": kind,
                "split": "development",
                "group_id": source_id,
                "family_group_ids": ["software-control"],
                "duplicate_group_id": None,
                "parent_group_id": None,
                "instrument_id": "synthetic-cu-ka",
                "acquisition_id": "pilot-acquisition",
                "profile_id": "synthetic-cu-ka",
                "calibration_artifact_id": None,
                "geometry": "reflection_bragg_brentano",
                "angle_unit": "two_theta",
                "radiation": "Cu Ka",
                "scan_range_deg": [10.0, 80.0],
                "expected_phase_groups": expected,
                "uncertain_phase_groups": [],
                "label_completeness": "complete",
                "label_provenance": ["WP-4 software-control manifest; not independent experimental truth"],
                "eligibility": "eligible",
                "eligibility_reasons": [],
                "strata": {"kind": kind, "phase_count": str(len(expected)), "data_kind": "synthetic"},
                "metadata": {"calibration_status": "unverified", "reference_completeness": "complete"},
            }
        )
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source_manifest: dict[str, Any] = {
        "schema_version": "wp5-source-manifest-0.1",
        "manifest_id": "wp5-pilot-sources-v1",
        "status": "inventory",
        "created_at": created,
        "data_root": "inputs",
        "sources": sources,
        "metadata": {"purpose": "development pilot", "rights": "CC0-1.0"},
    }
    case_manifest: dict[str, Any] = {
        "schema_version": "wp5-case-manifest-0.1",
        "manifest_id": "wp5-pilot-cases-v1",
        "status": "draft",
        "source_manifest_id": source_manifest["manifest_id"],
        "created_at": created,
        "cases": cases,
        "metadata": {"purpose": "development pilot"},
    }
    protocol: dict[str, Any] = {
        "schema_version": "wp5-protocol-0.1",
        "protocol_id": "wp5-pilot-protocol-v1",
        "status": "draft",
        "created_at": created,
        "source_manifest_id": source_manifest["manifest_id"],
        "case_manifest_id": case_manifest["manifest_id"],
        "geometry": "reflection_bragg_brentano",
        "angle_unit": "two_theta",
        "radiations": ["Cu Ka"],
        "reference_snapshot": "demo-subset",
        "variants": ["screening", "joint_no_requery", "full_mixture"],
        "preprocessing": {"background_policy": "production-default", "calibration_policy": "record-status", "peak_tolerance_deg": 0.25},
        "query": {"candidate_limit": 100, "max_phases": 3},
        "split_policy": {"tracks": ["family-held-out", "instrument-held-out", "joint-held-out"], "minimum_independent_groups": 3},
        # These are deliberately small, one-factor software controls.  They
        # exercise the production runner on the synthetic pilot; they are not
        # estimates of measured robustness and must not be promoted to a
        # laboratory or publication claim.
        "ablations": [
            {
                "id": "wrong-radiation-metadata",
                "factor": "radiation_metadata",
                "changes": {"radiation": "Co Ka"},
                "limitations": ["The scan remains a Cu Kα synthetic control; this corrupts metadata only."],
            },
            {
                "id": "background-wide",
                "factor": "background_policy",
                "changes": {"background_window_points": 61},
                "limitations": ["The policy seam is represented by a wider deterministic background window."],
            },
            {
                "id": "tolerance-wide",
                "factor": "peak_tolerance",
                "changes": {"peak_tolerance_deg": 0.35},
            },
            {
                "id": "reference-truncated",
                "factor": "reference_completeness",
                "changes": {"candidate_pool": 2},
                "limitations": ["This is a bounded candidate-cap control, not a complete-COD ablation."],
            },
        ],
        "resource_budgets": {"timeout_seconds": 60, "max_rss_bytes": 1000000000},
        "bootstrap": {"method": "cluster", "resamples": 2000, "seed": 0},
        "implementation": {"algorithm_version": "wp5-pilot-0.1", "environment_sha256": "0" * 64},
        "metadata": {"claims": ["descriptive software-control pilot"]},
        "limitations": [
            "All pilot inputs are synthetic controls.",
            "The pilot is development evidence and cannot establish measured performance.",
            "Profile scales are amplitudes, not phase fractions.",
        ],
    }
    write_json_atomic(output_dir / "source-manifest.json", source_manifest)
    write_json_atomic(output_dir / "case-manifest.json", case_manifest)
    write_json_atomic(output_dir / "protocol.json", protocol)
    artifacts = [
        artifact_record(output_dir / name, output_dir, kind=kind)
        for name, kind in (("source-manifest.json", "source-manifest"), ("case-manifest.json", "case-manifest"), ("protocol.json", "protocol"))
    ]
    for source in sources:
        artifacts.append(artifact_record(output_dir / source["local_path"], output_dir, kind="scan"))
    pilot: dict[str, Any] = {
        "schema_version": "wp5-pilot-manifest-0.1",
        "status": "complete",
        "dataset_status": "pilot",
        "source_manifest": "source-manifest.json",
        "case_manifest": "case-manifest.json",
        "protocol": "protocol.json",
        "sources": sources,
        "cases": cases,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "source_hashes": [source["sha256"] for source in sources],
        "artifacts": artifacts,
    }
    # Keep byte hashes in the returned manifest so every artifact remains
    # auditable.  For the semantic pilot hash, normalize only generated
    # metadata artifacts whose bytes include the run creation timestamp.  The
    # protocol, source and case content therefore remains bound while two
    # builds of the same inputs remain reproducible across wall-clock seconds.
    content_payload = json.loads(json.dumps(pilot, ensure_ascii=True))
    for artifact in content_payload["artifacts"]:
        if artifact.get("path") in _VOLATILE_METADATA_ARTIFACTS:
            artifact["sha256"] = _stable_metadata_hash(output_dir / artifact["path"])
    pilot["content_sha256"] = canonical_sha256(content_payload)
    write_json_atomic(output_dir / "pilot-manifest.json", pilot)
    return pilot


__all__ = ["WP5PilotError", "build_wp5_pilot"]
