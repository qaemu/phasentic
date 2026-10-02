"""Strict, immutable contracts for WP-5 evaluation evidence.

WP-5 manifests are data-boundary objects.  They are intentionally separate
from the application's analysis models so a label, split, or rights flag can
never be mistaken for a prediction.  Public validators return detached frozen
dataclasses and never mutate caller-owned mappings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
from types import MappingProxyType
from typing import Any, Mapping, TypeVar

from phasentic.domain.radiation import get_radiation

from .ablations import AblationValidationError, validate_ablation_declarations


SOURCE_MANIFEST_SCHEMA_VERSION = "wp5-source-manifest-0.1"
CASE_MANIFEST_SCHEMA_VERSION = "wp5-case-manifest-0.1"
PROTOCOL_SCHEMA_VERSION = "wp5-protocol-0.1"
RESULT_SCHEMA_VERSION = "wp5-result-0.1"
CONFIDENCE_SCHEMA_VERSION = "wp5-confidence-0.1"
CLOSURE_SCHEMA_VERSION = "wp5-closure-0.1"

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SCHEMA_VERSIONS = {
    SOURCE_MANIFEST_SCHEMA_VERSION,
    CASE_MANIFEST_SCHEMA_VERSION,
    PROTOCOL_SCHEMA_VERSION,
}
_SOURCE_STATUSES = {"eligible", "excluded", "pending_rights", "missing_metadata", "unavailable"}
_MANIFEST_STATUSES = {"draft", "inventory", "frozen", "validated", "blocked"}
_LICENSE_STATUSES = {
    "open",
    "permission_granted",
    "private_only",
    "pending",
    "denied",
    "unknown",
    "not_applicable",
}
_RIGHTS_STATUSES = {"allowed", "pending", "denied", "unknown", "not_applicable"}
_LABEL_STATUSES = {"complete", "incomplete", "unknown", "not_applicable"}
_CALIBRATION_STATUSES = {"passed", "failed", "insufficient_data", "unverified"}
_CASE_KINDS = {
    "measured",
    "measured_negative",
    "synthetic",
    "synthetic_negative",
    "mixed",
}
_CASE_ELIGIBILITY = {"eligible", "excluded", "pending", "unavailable"}
_SPLITS = {"development", "calibration", "test", "unassigned"}
_VARIANTS = {"screening", "joint_no_requery", "full_mixture"}


class WP5ContractError(ValueError):
    """Base error for an invalid WP-5 contract.

    ``code`` is stable enough for command-line and API callers to branch on;
    the human-readable detail remains useful in logs and reports.
    """

    contract = "wp5"

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


class SourceManifestValidationError(WP5ContractError):
    contract = "source_manifest"


class CaseManifestValidationError(WP5ContractError):
    contract = "case_manifest"


class ProtocolValidationError(WP5ContractError):
    contract = "protocol"


def _freeze(value: Any) -> Any:
    """Recursively freeze JSON-compatible values without retaining aliases."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze(item) for item in value))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _object(payload: Any, context: str, error_type: type[WP5ContractError]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise error_type("object_required", f"{context} must be an object")
    return payload


def _reject_unknown(
    payload: Mapping[str, Any],
    allowed: set[str],
    context: str,
    error_type: type[WP5ContractError],
    *,
    compatibility: set[str] | None = None,
) -> None:
    """Reject silently dropped fields at a manifest boundary.

    A small compatibility set is retained for the first WP-5 pilot's legacy
    aliases.  Everything else must be represented explicitly in the contract
    so an injected label or path cannot disappear during normalization.
    """

    accepted = allowed | (compatibility or set())
    unknown = sorted(set(payload).difference(accepted))
    if unknown:
        raise error_type("unknown_field", f"{context} has unknown fields: {', '.join(unknown)}")


def _string(
    payload: Mapping[str, Any],
    key: str,
    context: str,
    error_type: type[WP5ContractError],
    *,
    required: bool = True,
    allow_empty: bool = False,
) -> str | None:
    value = payload.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        code = "field_required" if required else "field_invalid"
        raise error_type(code, f"{context}.{key} must be a non-empty string")
    return value


def _identifier(
    payload: Mapping[str, Any], key: str, context: str, error_type: type[WP5ContractError], *, required: bool = True
) -> str | None:
    value = _string(payload, key, context, error_type, required=required)
    if value is not None and not _IDENTIFIER.fullmatch(value):
        raise error_type("identifier_invalid", f"{context}.{key} contains unsupported identifier characters")
    return value


def _sha(
    payload: Mapping[str, Any], key: str, context: str, error_type: type[WP5ContractError], *, required: bool = True
) -> str | None:
    value = _string(payload, key, context, error_type, required=required)
    if value is not None:
        if not _SHA256.fullmatch(value):
            raise error_type("hash_invalid", f"{context}.{key} must be a SHA-256 hexadecimal string")
        return value.lower()
    return None


def _integer(
    payload: Mapping[str, Any], key: str, context: str, error_type: type[WP5ContractError], *, required: bool = True
) -> int | None:
    value = payload.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise error_type("number_invalid", f"{context}.{key} must be an integer")
    return value


def _finite(
    value: Any,
    context: str,
    error_type: type[WP5ContractError],
    *,
    positive: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error_type("number_invalid", f"{context} must be numeric")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        raise error_type("number_invalid", f"{context} must be finite" + (" and positive" if positive else ""))
    return number


def _timestamp(value: Any, context: str, error_type: type[WP5ContractError]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type("timestamp_invalid", f"{context} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamp must include an explicit timezone")
    except ValueError as exc:
        raise error_type("timestamp_invalid", f"{context} must be an ISO-8601 timestamp") from exc
    return value


def validate_relative_path(value: Any, context: str, error_type: type[WP5ContractError]) -> str:
    """Validate a portable, non-escaping relative path.

    Both POSIX and Windows path syntax are checked because manifests may be
    exchanged between the supported platforms.  Resolution against a real
    root, including symlink handling, is performed by :mod:`sources`.
    """

    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise error_type("path_unsafe", f"{context} must be a non-empty relative path")
    candidate = Path(value)
    windows = PureWindowsPath(value)
    if candidate.is_absolute() or windows.is_absolute() or windows.drive:
        raise error_type("path_unsafe", f"{context} must be relative")
    if candidate == Path("."):
        raise error_type("path_unsafe", f"{context} must identify a file or directory below the root")
    if "\\" in value or any(part in {"", ".", ".."} for part in candidate.parts):
        raise error_type("path_unsafe", f"{context} contains an unsafe path component")
    return value


def _string_array(
    payload: Mapping[str, Any],
    key: str,
    context: str,
    error_type: type[WP5ContractError],
    *,
    required: bool = True,
    allow_empty: bool = True,
) -> tuple[str, ...] | None:
    raw = payload.get(key)
    if raw is None and not required:
        return None
    if not isinstance(raw, (list, tuple)):
        raise error_type("array_invalid", f"{context}.{key} must be a string array")
    values: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise error_type("array_invalid", f"{context}.{key}[{index}] must be a non-empty string")
        values.append(item)
    if not allow_empty and not values:
        raise error_type("array_empty", f"{context}.{key} must not be empty")
    if len(set(values)) != len(values):
        raise error_type("array_duplicate", f"{context}.{key} contains duplicate values")
    return tuple(values)


def _metadata(value: Any, context: str, error_type: type[WP5ContractError], *, default: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    if value is None:
        return {} if default is None else default
    if not isinstance(value, Mapping):
        raise error_type("object_required", f"{context} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise error_type("metadata_invalid", f"{context} keys must be strings")
    try:
        encoded = json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise error_type("metadata_invalid", f"{context} must contain JSON-compatible finite values") from exc
    return json.loads(encoded)


def canonical_contract_sha256(payload: Mapping[str, Any]) -> str:
    """Hash a canonical JSON contract representation independent of formatting."""

    if not isinstance(payload, Mapping):
        raise WP5ContractError("object_required", "contract payload must be an object")
    try:
        encoded = json.dumps(
            _thaw(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WP5ContractError("canonicalization_failed", "contract is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SourceAsset:
    source_id: str
    kind: str
    source_url: str | None
    doi: str | None
    original_filename: str
    local_path: str | None
    raw_local_path: str | None
    raw_size_bytes: int | None
    raw_sha256: str | None
    size_bytes: int | None
    sha256: str | None
    accessed_at: str | None
    license_status: str
    license_evidence_url: str | None
    attribution: str | None
    local_use_status: str
    redistribution_status: str
    instrument_metadata_source: str | None
    normalization: Mapping[str, Any]
    status: str
    reason: str
    label_status: str
    label_evidence: tuple[Any, ...]
    metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _thaw({
            "source_id": self.source_id,
            "kind": self.kind,
            "source_url": self.source_url,
            "doi": self.doi,
            "original_filename": self.original_filename,
            "local_path": self.local_path,
            "raw_local_path": self.raw_local_path,
            "raw_size_bytes": self.raw_size_bytes,
            "raw_sha256": self.raw_sha256,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "accessed_at": self.accessed_at,
            "license_status": self.license_status,
            "license_evidence_url": self.license_evidence_url,
            "attribution": self.attribution,
            "local_use_status": self.local_use_status,
            "redistribution_status": self.redistribution_status,
            "instrument_metadata_source": self.instrument_metadata_source,
            "normalization": self.normalization,
            "status": self.status,
            "reason": self.reason,
            "label_status": self.label_status,
            "label_evidence": self.label_evidence,
            "metadata": self.metadata,
        })


@dataclass(frozen=True)
class SourceManifest:
    schema_version: str
    manifest_id: str
    status: str
    created_at: str
    data_root: str
    sources: tuple[SourceAsset, ...]
    metadata: Mapping[str, Any]


    def to_dict(self) -> dict[str, Any]:
        return _thaw({
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "status": self.status,
            "created_at": self.created_at,
            "data_root": self.data_root,
            "sources": [item.to_dict() for item in self.sources],
            "metadata": self.metadata,
        })


def _validate_source(payload: Mapping[str, Any], index: int) -> SourceAsset:
    context = f"sources[{index}]"
    _reject_unknown(
        payload,
        {
            "source_id", "kind", "source_url", "doi", "original_filename", "local_path", "raw_local_path", "raw_size_bytes", "raw_sha256", "size_bytes", "sha256",
            "accessed_at", "license_status", "license_evidence_url", "attribution", "local_use_status",
            "redistribution_status", "instrument_metadata_source", "normalization", "status", "reason",
            "label_status", "label_evidence", "metadata",
        },
        context,
        SourceManifestValidationError,
    )
    source_id = _identifier(payload, "source_id", context, SourceManifestValidationError)
    assert source_id is not None
    kind = _string(payload, "kind", context, SourceManifestValidationError)
    assert kind is not None
    lowered_kind = kind.strip().lower()
    if "certificate" in lowered_kind and lowered_kind != "certificate_reference":
        raise SourceManifestValidationError(
            "certificate_kind_invalid", f"{context}.kind must use certificate_reference for certificate material"
        )
    source_url = _string(payload, "source_url", context, SourceManifestValidationError, required=False)
    doi = _string(payload, "doi", context, SourceManifestValidationError, required=False)
    if source_url is None and doi is None:
        raise SourceManifestValidationError("source_evidence_missing", f"{context} needs source_url or doi")
    original_filename = _string(payload, "original_filename", context, SourceManifestValidationError)
    assert original_filename is not None
    local_path = _string(payload, "local_path", context, SourceManifestValidationError, required=False)
    if local_path is not None:
        local_path = validate_relative_path(local_path, f"{context}.local_path", SourceManifestValidationError)
    raw_local_path = _string(payload, "raw_local_path", context, SourceManifestValidationError, required=False)
    if raw_local_path is not None:
        raw_local_path = validate_relative_path(raw_local_path, f"{context}.raw_local_path", SourceManifestValidationError)
    raw_size_bytes = _integer(payload, "raw_size_bytes", context, SourceManifestValidationError, required=False)
    if raw_size_bytes is not None and raw_size_bytes < 0:
        raise SourceManifestValidationError("size_invalid", f"{context}.raw_size_bytes must be non-negative")
    raw_sha256 = _sha(payload, "raw_sha256", context, SourceManifestValidationError, required=False)
    if (raw_local_path is None) != (raw_size_bytes is None) or (raw_local_path is None) != (raw_sha256 is None):
        raise SourceManifestValidationError("raw_identity_incomplete", f"{context} raw_local_path, raw_size_bytes, and raw_sha256 must be paired")
    size_bytes = _integer(payload, "size_bytes", context, SourceManifestValidationError, required=False)
    if size_bytes is not None and size_bytes < 0:
        raise SourceManifestValidationError("size_invalid", f"{context}.size_bytes must be non-negative")
    sha256 = _sha(payload, "sha256", context, SourceManifestValidationError, required=False)
    accessed_at = _timestamp(payload["accessed_at"], f"{context}.accessed_at", SourceManifestValidationError) if payload.get("accessed_at") is not None else None
    license_status = _string(payload, "license_status", context, SourceManifestValidationError)
    assert license_status is not None
    if license_status not in _LICENSE_STATUSES:
        raise SourceManifestValidationError("license_status_invalid", f"{context}.license_status is unsupported")
    license_evidence_url = _string(payload, "license_evidence_url", context, SourceManifestValidationError, required=False)
    attribution = _string(payload, "attribution", context, SourceManifestValidationError, required=False)
    local_use_status = _string(payload, "local_use_status", context, SourceManifestValidationError)
    redistribution_status = _string(payload, "redistribution_status", context, SourceManifestValidationError)
    assert local_use_status is not None and redistribution_status is not None
    if local_use_status not in _RIGHTS_STATUSES or redistribution_status not in _RIGHTS_STATUSES:
        raise SourceManifestValidationError("rights_status_invalid", f"{context} has unsupported rights status")
    instrument_metadata_source = _string(
        payload, "instrument_metadata_source", context, SourceManifestValidationError, required=False
    )
    normalization = _metadata(payload.get("normalization"), f"{context}.normalization", SourceManifestValidationError)
    if normalization:
        version = _string(normalization, "version", f"{context}.normalization", SourceManifestValidationError)
        digest = _sha(normalization, "sha256", f"{context}.normalization", SourceManifestValidationError)
        assert version is not None and digest is not None
    status = _string(payload, "status", context, SourceManifestValidationError)
    assert status is not None
    if status not in _SOURCE_STATUSES:
        raise SourceManifestValidationError("status_invalid", f"{context}.status is unsupported")
    reason = _string(payload, "reason", context, SourceManifestValidationError)
    assert reason is not None
    label_status = _string(payload, "label_status", context, SourceManifestValidationError)
    assert label_status is not None
    if label_status not in _LABEL_STATUSES:
        raise SourceManifestValidationError("label_status_invalid", f"{context}.label_status is unsupported")
    raw_label_evidence = payload.get("label_evidence", [])
    if not isinstance(raw_label_evidence, (list, tuple)):
        raise SourceManifestValidationError("label_evidence_invalid", f"{context}.label_evidence must be an array")
    label_evidence_values: list[Any] = []
    for evidence_index, item in enumerate(raw_label_evidence):
        if isinstance(item, Mapping):
            label_evidence_values.append(
                _freeze(_metadata(item, f"{context}.label_evidence[{evidence_index}]", SourceManifestValidationError))
            )
        elif isinstance(item, str) and item.strip():
            label_evidence_values.append(item)
        else:
            raise SourceManifestValidationError(
                "label_evidence_invalid", f"{context}.label_evidence[{evidence_index}] must be a string or object"
            )
    label_evidence = tuple(label_evidence_values)
    if label_status == "complete" and not label_evidence:
        raise SourceManifestValidationError("label_evidence_missing", f"{context} complete labels need evidence")
    metadata = _metadata(payload.get("metadata"), f"{context}.metadata", SourceManifestValidationError)
    if lowered_kind == "certificate_reference" and metadata.get("measured_scan") is True:
        raise SourceManifestValidationError(
            "certificate_scan_conflict", f"{context} certificate_reference cannot be declared as a measured scan"
        )

    if status == "eligible":
        if local_path is None or size_bytes is None or sha256 is None:
            raise SourceManifestValidationError("source_file_missing", f"{context} eligible source needs local_path, size_bytes, and sha256")
        if local_use_status != "allowed":
            raise SourceManifestValidationError("rights_pending", f"{context} eligible source is not allowed for local use")
        if redistribution_status not in {"allowed", "not_applicable"}:
            raise SourceManifestValidationError("rights_pending", f"{context} eligible source has unresolved redistribution rights")
        if lowered_kind.startswith("measured"):
            radiation_value = metadata.get("radiation")
            geometry_value = metadata.get("geometry")
            if (
                not isinstance(radiation_value, str)
                or not radiation_value.strip()
                or radiation_value.strip().casefold()
                in {"unknown", "unknown-until-record-inspected", "record-specific", "not-provided"}
            ):
                raise SourceManifestValidationError(
                    "measurement_metadata_missing", f"{context} eligible measured source needs known radiation"
                )
            try:
                get_radiation(radiation_value)
            except ValueError as exc:
                raise SourceManifestValidationError("radiation_invalid", str(exc)) from exc
            if geometry_value != "reflection_bragg_brentano":
                raise SourceManifestValidationError(
                    "geometry_unsupported",
                    f"{context} eligible measured source requires reflection Bragg-Brentano geometry",
                )
    if (
        status == "pending_rights"
        and local_use_status == "allowed"
        and redistribution_status == "allowed"
        and license_status not in {"pending", "unknown"}
    ):
        raise SourceManifestValidationError("status_inconsistent", f"{context} pending_rights has no pending right")
    if status != "eligible" and not reason.strip():
        raise SourceManifestValidationError("reason_missing", f"{context} non-eligible source needs a reason")
    if license_status in {"open", "permission_granted"} and not license_evidence_url:
        raise SourceManifestValidationError("license_evidence_missing", f"{context} needs license_evidence_url")
    if status == "eligible" and not attribution:
        raise SourceManifestValidationError("attribution_missing", f"{context} eligible source needs attribution")

    return SourceAsset(
        source_id=source_id,
        kind=kind,
        source_url=source_url,
        doi=doi,
        original_filename=original_filename,
        local_path=local_path,
        raw_local_path=raw_local_path,
        raw_size_bytes=raw_size_bytes,
        raw_sha256=raw_sha256,
        size_bytes=size_bytes,
        sha256=sha256,
        accessed_at=accessed_at,
        license_status=license_status,
        license_evidence_url=license_evidence_url,
        attribution=attribution,
        local_use_status=local_use_status,
        redistribution_status=redistribution_status,
        instrument_metadata_source=instrument_metadata_source,
        normalization=_freeze(normalization),
        status=status,
        reason=reason,
        label_status=label_status,
        label_evidence=label_evidence,
        metadata=_freeze(metadata),
    )


def validate_source_manifest(payload: Mapping[str, Any]) -> SourceManifest:
    """Validate a source inventory and return an immutable detached model."""

    context = "source_manifest"
    payload = _object(payload, context, SourceManifestValidationError)
    _reject_unknown(payload, {"schema_version", "manifest_id", "status", "created_at", "data_root", "sources", "metadata"}, context, SourceManifestValidationError)
    required = {"schema_version", "manifest_id", "status", "created_at", "data_root", "sources"}
    missing = sorted(required.difference(payload))
    if missing:
        raise SourceManifestValidationError("field_required", f"{context} is missing: {', '.join(missing)}")
    schema_version = _string(payload, "schema_version", context, SourceManifestValidationError)
    assert schema_version is not None
    if schema_version != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise SourceManifestValidationError("schema_version_unsupported", f"{context}.schema_version is unsupported")
    manifest_id = _identifier(payload, "manifest_id", context, SourceManifestValidationError)
    assert manifest_id is not None
    status = _string(payload, "status", context, SourceManifestValidationError)
    assert status is not None
    if status not in _MANIFEST_STATUSES:
        raise SourceManifestValidationError("status_invalid", f"{context}.status is unsupported")
    created_at = _timestamp(payload["created_at"], f"{context}.created_at", SourceManifestValidationError)
    data_root = validate_relative_path(payload["data_root"], f"{context}.data_root", SourceManifestValidationError)
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, (list, tuple)) or not raw_sources:
        raise SourceManifestValidationError("sources_empty", f"{context}.sources must be a non-empty array")
    sources = tuple(
        _validate_source(_object(item, f"{context}.sources[{index}]", SourceManifestValidationError), index)
        for index, item in enumerate(raw_sources)
    )
    identifiers = [item.source_id for item in sources]
    if len(set(identifiers)) != len(identifiers):
        raise SourceManifestValidationError("identifier_duplicate", f"{context}.sources contains duplicate source_id")
    metadata = _metadata(payload.get("metadata"), f"{context}.metadata", SourceManifestValidationError)
    return SourceManifest(
        schema_version=schema_version,
        manifest_id=manifest_id,
        status=status,
        created_at=created_at,
        data_root=data_root,
        sources=sources,
        metadata=_freeze(metadata),
    )


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    sample_id: str
    scan_id: str
    replicate_id: str | None
    source_ids: tuple[str, ...]
    raw_path: str
    raw_sha256: str
    normalized_path: str | None
    normalized_sha256: str | None
    data_kind: str
    angle_unit: str
    radiation: str
    geometry: str
    scan_range_deg: tuple[float, float]
    acquisition_id: str | None
    instrument_id: str | None
    profile_id: str | None
    calibration_artifact_id: str | None
    expected_phase_groups: tuple[str, ...]
    expected_parent_family_groups: tuple[str, ...]
    uncertain_phase_groups: tuple[str, ...]
    label_completeness: str
    label_provenance: tuple[str, ...]
    family_group_ids: tuple[str, ...]
    duplicate_group_id: str | None
    parent_group_id: str | None
    split: str
    eligibility: str
    eligibility_reasons: tuple[str, ...]
    strata: Mapping[str, Any]
    metadata: Mapping[str, Any]
    kind: str | None = None
    group_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw({
            "case_id": self.case_id,
            "sample_id": self.sample_id,
            "scan_id": self.scan_id,
            "replicate_id": self.replicate_id,
            "source_ids": self.source_ids,
            "raw_path": self.raw_path,
            "raw_sha256": self.raw_sha256,
            "normalized_path": self.normalized_path,
            "normalized_sha256": self.normalized_sha256,
            "data_kind": self.data_kind,
            "angle_unit": self.angle_unit,
            "radiation": self.radiation,
            "geometry": self.geometry,
            "scan_range_deg": self.scan_range_deg,
            "acquisition_id": self.acquisition_id,
            "instrument_id": self.instrument_id,
            "profile_id": self.profile_id,
            "calibration_artifact_id": self.calibration_artifact_id,
            "expected_phase_groups": self.expected_phase_groups,
            "expected_parent_family_groups": self.expected_parent_family_groups,
            "uncertain_phase_groups": self.uncertain_phase_groups,
            "label_completeness": self.label_completeness,
            "label_provenance": self.label_provenance,
            "family_group_ids": self.family_group_ids,
            "duplicate_group_id": self.duplicate_group_id,
            "parent_group_id": self.parent_group_id,
            "split": self.split,
            "eligibility": self.eligibility,
            "eligibility_reasons": self.eligibility_reasons,
            "strata": self.strata,
            "metadata": self.metadata,
        })
        if self.kind is not None:
            payload["kind"] = self.kind
        if self.group_id is not None:
            payload["group_id"] = self.group_id
        return payload


@dataclass(frozen=True)
class CaseManifest:
    schema_version: str
    manifest_id: str
    status: str
    source_manifest_id: str
    created_at: str
    cases: tuple[CaseRecord, ...]
    metadata: Mapping[str, Any]


    def to_dict(self) -> dict[str, Any]:
        return _thaw({
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "status": self.status,
            "source_manifest_id": self.source_manifest_id,
            "created_at": self.created_at,
            "cases": [item.to_dict() for item in self.cases],
            "metadata": self.metadata,
        })


def _validate_case(payload: Mapping[str, Any], index: int) -> CaseRecord:
    context = f"cases[{index}]"
    _reject_unknown(
        payload,
        {
            "case_id", "sample_id", "scan_id", "replicate_id", "source_ids", "raw_path", "raw_sha256",
            "normalized_path", "normalized_sha256", "data_kind", "angle_unit", "radiation", "geometry",
            "scan_range_deg", "acquisition_id", "instrument_id", "profile_id", "calibration_artifact_id",
            "expected_phase_groups", "uncertain_phase_groups", "label_completeness", "label_provenance",
            "expected_parent_family_groups",
            "family_group_ids", "duplicate_group_id", "parent_group_id", "split", "eligibility",
            "eligibility_reasons", "strata", "metadata",
        },
        context,
        CaseManifestValidationError,
        compatibility={"kind", "group_id"},
    )
    case_id = _identifier(payload, "case_id", context, CaseManifestValidationError)
    sample_id = _identifier(payload, "sample_id", context, CaseManifestValidationError)
    scan_id = _identifier(payload, "scan_id", context, CaseManifestValidationError)
    assert case_id is not None and sample_id is not None and scan_id is not None
    replicate_id = _identifier(payload, "replicate_id", context, CaseManifestValidationError, required=False)
    source_ids = _string_array(payload, "source_ids", context, CaseManifestValidationError, allow_empty=False)
    assert source_ids is not None
    raw_path = _string(payload, "raw_path", context, CaseManifestValidationError)
    raw_sha256 = _sha(payload, "raw_sha256", context, CaseManifestValidationError)
    assert raw_path is not None and raw_sha256 is not None
    raw_path = validate_relative_path(raw_path, f"{context}.raw_path", CaseManifestValidationError)
    normalized_path = _string(payload, "normalized_path", context, CaseManifestValidationError, required=False)
    if normalized_path is not None:
        normalized_path = validate_relative_path(normalized_path, f"{context}.normalized_path", CaseManifestValidationError)
    normalized_sha256 = _sha(payload, "normalized_sha256", context, CaseManifestValidationError, required=False)
    if (normalized_path is None) != (normalized_sha256 is None):
        raise CaseManifestValidationError("normalized_pair_invalid", f"{context} normalized_path and normalized_sha256 must be paired")
    data_kind = _string(payload, "data_kind", context, CaseManifestValidationError)
    assert data_kind is not None
    if data_kind not in _CASE_KINDS:
        raise CaseManifestValidationError("data_kind_invalid", f"{context}.data_kind is unsupported")
    angle_unit = _string(payload, "angle_unit", context, CaseManifestValidationError)
    assert angle_unit is not None
    if angle_unit != "two_theta":
        raise CaseManifestValidationError("angle_unit_unsupported", f"{context} requires calibrated two_theta")
    radiation = _string(payload, "radiation", context, CaseManifestValidationError)
    assert radiation is not None
    try:
        radiation = get_radiation(radiation).key
    except ValueError as exc:
        raise CaseManifestValidationError("radiation_invalid", str(exc)) from exc
    geometry = _string(payload, "geometry", context, CaseManifestValidationError)
    assert geometry is not None
    if geometry != "reflection_bragg_brentano":
        raise CaseManifestValidationError("geometry_unsupported", f"{context} supports reflection Bragg-Brentano only")
    raw_range = payload.get("scan_range_deg")
    if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
        raise CaseManifestValidationError("scan_range_invalid", f"{context}.scan_range_deg must contain two values")
    try:
        lower = _finite(raw_range[0], f"{context}.scan_range_deg[0]", CaseManifestValidationError)
        upper = _finite(raw_range[1], f"{context}.scan_range_deg[1]", CaseManifestValidationError)
    except CaseManifestValidationError as exc:
        raise CaseManifestValidationError("scan_range_invalid", exc.detail) from exc
    if not 0.0 <= lower < upper <= 180.0:
        raise CaseManifestValidationError("scan_range_invalid", f"{context}.scan_range_deg must be ordered within 0..180")
    acquisition_id = _identifier(payload, "acquisition_id", context, CaseManifestValidationError, required=False)
    instrument_id = _identifier(payload, "instrument_id", context, CaseManifestValidationError, required=False)
    profile_id = _identifier(payload, "profile_id", context, CaseManifestValidationError, required=False)
    calibration_artifact_id = _identifier(payload, "calibration_artifact_id", context, CaseManifestValidationError, required=False)
    expected = _string_array(payload, "expected_phase_groups", context, CaseManifestValidationError, allow_empty=True)
    expected_parent = _string_array(
        payload,
        "expected_parent_family_groups",
        context,
        CaseManifestValidationError,
        required=False,
        allow_empty=True,
    )
    uncertain = _string_array(payload, "uncertain_phase_groups", context, CaseManifestValidationError, allow_empty=True)
    assert expected is not None and uncertain is not None
    if expected_parent is None:
        expected_parent = ()
    overlap = set(expected) & set(uncertain)
    if overlap:
        raise CaseManifestValidationError("label_overlap", f"{context} known and uncertain phase groups overlap")
    label_completeness = _string(payload, "label_completeness", context, CaseManifestValidationError)
    assert label_completeness is not None
    if label_completeness not in _LABEL_STATUSES:
        raise CaseManifestValidationError("label_status_invalid", f"{context}.label_completeness is unsupported")
    label_provenance = _string_array(payload, "label_provenance", context, CaseManifestValidationError, allow_empty=True)
    assert label_provenance is not None
    if label_completeness == "complete" and not label_provenance:
        raise CaseManifestValidationError("label_provenance_missing", f"{context} complete labels need provenance")
    families = _string_array(payload, "family_group_ids", context, CaseManifestValidationError, allow_empty=True)
    assert families is not None
    duplicate_group_id = _identifier(payload, "duplicate_group_id", context, CaseManifestValidationError, required=False)
    parent_group_id = _identifier(payload, "parent_group_id", context, CaseManifestValidationError, required=False)
    split = _string(payload, "split", context, CaseManifestValidationError)
    assert split is not None
    if split not in _SPLITS:
        raise CaseManifestValidationError("split_invalid", f"{context}.split is unsupported")
    eligibility = _string(payload, "eligibility", context, CaseManifestValidationError)
    assert eligibility is not None
    if eligibility not in _CASE_ELIGIBILITY:
        raise CaseManifestValidationError("eligibility_invalid", f"{context}.eligibility is unsupported")
    eligibility_reasons = _string_array(payload, "eligibility_reasons", context, CaseManifestValidationError, allow_empty=True)
    assert eligibility_reasons is not None
    if eligibility != "eligible" and not eligibility_reasons:
        raise CaseManifestValidationError("eligibility_reason_missing", f"{context} non-eligible case needs a reason")
    strata = _metadata(payload.get("strata"), f"{context}.strata", CaseManifestValidationError)
    metadata = _metadata(payload.get("metadata"), f"{context}.metadata", CaseManifestValidationError)
    calibration_status = metadata.get("calibration_status")
    if calibration_status is not None:
        if not isinstance(calibration_status, str) or calibration_status not in _CALIBRATION_STATUSES:
            raise CaseManifestValidationError(
                "calibration_status_invalid",
                f"{context}.metadata.calibration_status is unsupported",
            )
        if data_kind.startswith("measured") and calibration_status == "passed" and calibration_artifact_id is None:
            raise CaseManifestValidationError(
                "calibration_artifact_required",
                f"{context} measured passed calibration needs calibration_artifact_id",
            )
    legacy_kind = _string(payload, "kind", context, CaseManifestValidationError, required=False)
    legacy_group_id = _identifier(payload, "group_id", context, CaseManifestValidationError, required=False)
    return CaseRecord(
        case_id=case_id,
        sample_id=sample_id,
        scan_id=scan_id,
        replicate_id=replicate_id,
        source_ids=source_ids,
        raw_path=raw_path,
        raw_sha256=raw_sha256,
        normalized_path=normalized_path,
        normalized_sha256=normalized_sha256,
        data_kind=data_kind,
        angle_unit=angle_unit,
        radiation=radiation,
        geometry=geometry,
        scan_range_deg=(lower, upper),
        acquisition_id=acquisition_id,
        instrument_id=instrument_id,
        profile_id=profile_id,
        calibration_artifact_id=calibration_artifact_id,
        expected_phase_groups=expected,
        expected_parent_family_groups=expected_parent,
        uncertain_phase_groups=uncertain,
        label_completeness=label_completeness,
        label_provenance=label_provenance,
        family_group_ids=families,
        duplicate_group_id=duplicate_group_id,
        parent_group_id=parent_group_id,
        split=split,
        eligibility=eligibility,
        eligibility_reasons=eligibility_reasons,
        strata=_freeze(strata),
        metadata=_freeze(metadata),
        kind=legacy_kind,
        group_id=legacy_group_id,
    )


def validate_case_manifest(payload: Mapping[str, Any]) -> CaseManifest:
    """Validate and freeze a case inventory."""

    context = "case_manifest"
    payload = _object(payload, context, CaseManifestValidationError)
    _reject_unknown(payload, {"schema_version", "manifest_id", "status", "source_manifest_id", "created_at", "cases", "metadata"}, context, CaseManifestValidationError)
    required = {"schema_version", "manifest_id", "status", "source_manifest_id", "created_at", "cases"}
    missing = sorted(required.difference(payload))
    if missing:
        raise CaseManifestValidationError("field_required", f"{context} is missing: {', '.join(missing)}")
    schema_version = _string(payload, "schema_version", context, CaseManifestValidationError)
    assert schema_version is not None
    if schema_version != CASE_MANIFEST_SCHEMA_VERSION:
        raise CaseManifestValidationError("schema_version_unsupported", f"{context}.schema_version is unsupported")
    manifest_id = _identifier(payload, "manifest_id", context, CaseManifestValidationError)
    source_manifest_id = _identifier(payload, "source_manifest_id", context, CaseManifestValidationError)
    assert manifest_id is not None and source_manifest_id is not None
    status = _string(payload, "status", context, CaseManifestValidationError)
    assert status is not None
    if status not in _MANIFEST_STATUSES:
        raise CaseManifestValidationError("status_invalid", f"{context}.status is unsupported")
    created_at = _timestamp(payload["created_at"], f"{context}.created_at", CaseManifestValidationError)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, (list, tuple)) or not raw_cases:
        raise CaseManifestValidationError("cases_empty", f"{context}.cases must be a non-empty array")
    cases = tuple(
        _validate_case(_object(item, f"{context}.cases[{index}]", CaseManifestValidationError), index)
        for index, item in enumerate(raw_cases)
    )
    identifiers = [item.case_id for item in cases]
    if len(set(identifiers)) != len(identifiers):
        raise CaseManifestValidationError("identifier_duplicate", f"{context}.cases contains duplicate case_id")
    if status in {"frozen", "validated"} and any(item.split == "unassigned" for item in cases):
        raise CaseManifestValidationError("split_unassigned", f"{context} frozen cases need explicit split assignments")
    metadata = _metadata(payload.get("metadata"), f"{context}.metadata", CaseManifestValidationError)
    return CaseManifest(
        schema_version=schema_version,
        manifest_id=manifest_id,
        status=status,
        source_manifest_id=source_manifest_id,
        created_at=created_at,
        cases=cases,
        metadata=_freeze(metadata),
    )


@dataclass(frozen=True)
class Protocol:
    schema_version: str
    protocol_id: str
    status: str
    created_at: str
    source_manifest_id: str
    case_manifest_id: str
    angle_unit: str
    geometry: str
    radiations: tuple[str, ...]
    reference_snapshot: str
    variants: tuple[str, ...]
    preprocessing: Mapping[str, Any]
    query: Mapping[str, Any]
    split_policy: Mapping[str, Any]
    ablations: tuple[Mapping[str, Any], ...]
    resource_budgets: Mapping[str, Any]
    bootstrap: Mapping[str, Any]
    implementation: Mapping[str, Any]
    metadata: Mapping[str, Any]
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw({
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "status": self.status,
            "created_at": self.created_at,
            "source_manifest_id": self.source_manifest_id,
            "case_manifest_id": self.case_manifest_id,
            "angle_unit": self.angle_unit,
            "geometry": self.geometry,
            "radiations": self.radiations,
            "reference_snapshot": self.reference_snapshot,
            "variants": self.variants,
            "preprocessing": self.preprocessing,
            "query": self.query,
            "split_policy": self.split_policy,
            "ablations": self.ablations,
            "resource_budgets": self.resource_budgets,
            "bootstrap": self.bootstrap,
            "implementation": self.implementation,
            "metadata": self.metadata,
        })
        if self.limitations:
            payload["limitations"] = list(self.limitations)
        return payload


def validate_protocol(payload: Mapping[str, Any]) -> Protocol:
    """Validate a frozen evaluation protocol and return an immutable model."""

    context = "protocol"
    payload = _object(payload, context, ProtocolValidationError)
    _reject_unknown(
        payload,
        {
            "schema_version", "protocol_id", "status", "created_at", "source_manifest_id", "case_manifest_id",
            "angle_unit", "geometry", "radiations", "reference_snapshot", "variants", "preprocessing", "query",
            "split_policy", "ablations", "resource_budgets", "bootstrap", "implementation", "metadata",
        },
        context,
        ProtocolValidationError,
        compatibility={"limitations"},
    )
    required = {
        "schema_version", "protocol_id", "status", "created_at", "source_manifest_id", "case_manifest_id",
        "angle_unit", "geometry", "radiations", "reference_snapshot", "variants", "preprocessing", "query",
        "split_policy", "ablations", "resource_budgets", "bootstrap", "implementation",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ProtocolValidationError("field_required", f"{context} is missing: {', '.join(missing)}")
    schema_version = _string(payload, "schema_version", context, ProtocolValidationError)
    assert schema_version is not None
    if schema_version != PROTOCOL_SCHEMA_VERSION:
        raise ProtocolValidationError("schema_version_unsupported", f"{context}.schema_version is unsupported")
    protocol_id = _identifier(payload, "protocol_id", context, ProtocolValidationError)
    source_manifest_id = _identifier(payload, "source_manifest_id", context, ProtocolValidationError)
    case_manifest_id = _identifier(payload, "case_manifest_id", context, ProtocolValidationError)
    assert protocol_id is not None and source_manifest_id is not None and case_manifest_id is not None
    status = _string(payload, "status", context, ProtocolValidationError)
    assert status is not None
    if status not in _MANIFEST_STATUSES:
        raise ProtocolValidationError("status_invalid", f"{context}.status is unsupported")
    created_at = _timestamp(payload["created_at"], f"{context}.created_at", ProtocolValidationError)
    angle_unit = _string(payload, "angle_unit", context, ProtocolValidationError)
    assert angle_unit is not None
    if angle_unit != "two_theta":
        raise ProtocolValidationError("angle_unit_unsupported", f"{context} requires calibrated two_theta")
    geometry = _string(payload, "geometry", context, ProtocolValidationError)
    assert geometry is not None
    if geometry != "reflection_bragg_brentano":
        raise ProtocolValidationError("geometry_unsupported", f"{context} supports reflection Bragg-Brentano only")
    raw_radiations = _string_array(payload, "radiations", context, ProtocolValidationError, allow_empty=False)
    assert raw_radiations is not None
    radiations: list[str] = []
    for radiation in raw_radiations:
        try:
            radiations.append(get_radiation(radiation).key)
        except ValueError as exc:
            raise ProtocolValidationError("radiation_invalid", str(exc)) from exc
    if len(set(radiations)) != len(radiations):
        raise ProtocolValidationError("radiation_duplicate", f"{context}.radiations contains duplicates")
    reference_snapshot = _string(payload, "reference_snapshot", context, ProtocolValidationError)
    assert reference_snapshot is not None
    variants = _string_array(payload, "variants", context, ProtocolValidationError, allow_empty=False)
    assert variants is not None
    if any(item not in _VARIANTS for item in variants):
        raise ProtocolValidationError("variant_invalid", f"{context}.variants contains an unsupported analysis variant")
    for key in ("preprocessing", "query", "split_policy", "resource_budgets", "bootstrap", "implementation"):
        if not isinstance(payload.get(key), Mapping):
            raise ProtocolValidationError("object_required", f"{context}.{key} must be an object")
    preprocessing = _metadata(payload["preprocessing"], f"{context}.preprocessing", ProtocolValidationError)
    query = _metadata(payload["query"], f"{context}.query", ProtocolValidationError)
    split_policy = _metadata(payload["split_policy"], f"{context}.split_policy", ProtocolValidationError)
    resource_budgets = _metadata(payload["resource_budgets"], f"{context}.resource_budgets", ProtocolValidationError)
    implementation = _metadata(payload["implementation"], f"{context}.implementation", ProtocolValidationError)
    bootstrap = _metadata(payload["bootstrap"], f"{context}.bootstrap", ProtocolValidationError)
    method = bootstrap.get("method")
    if method != "cluster":
        raise ProtocolValidationError("bootstrap_method_invalid", f"{context}.bootstrap.method must be cluster")
    seed = bootstrap.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ProtocolValidationError("bootstrap_seed_invalid", f"{context}.bootstrap.seed must be a non-negative integer")
    resamples = bootstrap.get("resamples")
    if isinstance(resamples, bool) or not isinstance(resamples, int) or not 100 <= resamples <= 100_000:
        raise ProtocolValidationError("bootstrap_resamples_invalid", f"{context}.bootstrap.resamples must be between 100 and 100000")
    raw_ablations = payload.get("ablations")
    if not isinstance(raw_ablations, (list, tuple)):
        raise ProtocolValidationError("array_invalid", f"{context}.ablations must be an array")
    try:
        declared_ablations = validate_ablation_declarations(raw_ablations)
    except AblationValidationError as exc:
        code, _, detail = str(exc).partition(":")
        if not detail:
            code, detail = "ablation_invalid", str(exc)
        raise ProtocolValidationError(code.strip() or "ablation_invalid", detail.strip() or str(exc)) from exc
    ablations = tuple(
        _freeze(_metadata(item, f"{context}.ablations", ProtocolValidationError))
        for item in declared_ablations
    )
    metadata = _metadata(payload.get("metadata"), f"{context}.metadata", ProtocolValidationError)
    raw_limitations = payload.get("limitations", [])
    limitations = _string_array(
        {"limitations": raw_limitations}, "limitations", context, ProtocolValidationError, allow_empty=True
    )
    assert limitations is not None
    return Protocol(
        schema_version=schema_version,
        protocol_id=protocol_id,
        status=status,
        created_at=created_at,
        source_manifest_id=source_manifest_id,
        case_manifest_id=case_manifest_id,
        angle_unit=angle_unit,
        geometry=geometry,
        radiations=tuple(radiations),
        reference_snapshot=reference_snapshot,
        variants=variants,
        preprocessing=_freeze(preprocessing),
        query=_freeze(query),
        split_policy=_freeze(split_policy),
        ablations=ablations,
        resource_budgets=_freeze(resource_budgets),
        bootstrap=_freeze(bootstrap),
        implementation=_freeze(implementation),
        metadata=_freeze(metadata),
        limitations=limitations,
    )


_T = TypeVar("_T")


def _load_json(path: str | Path, context: str, error_type: type[WP5ContractError]) -> Mapping[str, Any]:
    resolved = Path(path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise error_type("read_failed", f"cannot read {context}: {resolved}") from exc
    return _object(payload, context, error_type)


def load_source_manifest(path: str | Path) -> SourceManifest:
    return validate_source_manifest(_load_json(path, "source manifest", SourceManifestValidationError))


def load_case_manifest(path: str | Path) -> CaseManifest:
    return validate_case_manifest(_load_json(path, "case manifest", CaseManifestValidationError))


def load_protocol(path: str | Path) -> Protocol:
    return validate_protocol(_load_json(path, "protocol", ProtocolValidationError))


__all__ = [
    "SOURCE_MANIFEST_SCHEMA_VERSION",
    "CASE_MANIFEST_SCHEMA_VERSION",
    "PROTOCOL_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "CONFIDENCE_SCHEMA_VERSION",
    "CLOSURE_SCHEMA_VERSION",
    "WP5ContractError",
    "SourceManifestValidationError",
    "CaseManifestValidationError",
    "ProtocolValidationError",
    "SourceAsset",
    "SourceManifest",
    "CaseRecord",
    "CaseManifest",
    "Protocol",
    "canonical_contract_sha256",
    "validate_relative_path",
    "validate_source_manifest",
    "validate_case_manifest",
    "validate_protocol",
    "load_source_manifest",
    "load_case_manifest",
    "load_protocol",
]
