"""Safe local intake and inventory for measured WP-5 sources.

WP-5 acquisition is deliberately separated from evaluation.  This module does
not fetch from the network and does not infer missing experimental metadata. It
stages already obtained bytes into a caller-owned directory, authenticates the
result, probes only the application's supported ``.xy`` and ``.xrdml``
readers, and emits a strict :class:`SourceManifest` with an explicit state for
every catalog record.

The source catalog is the authority for provenance, rights, and labels.  A
local byte hash authenticates what was staged; it never upgrades uncertain
rights or labels.  Files with a bad hash, unsupported format, missing bytes,
or failed parsing remain represented with a named reason.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence

from phasentic.domain.radiation import get_radiation
from phasentic.importers.xrdml import parse_xrdml
from phasentic.importers.xy import parse_xy

from .artifacts import write_json_atomic
from .contracts import (
    SOURCE_MANIFEST_SCHEMA_VERSION,
    SourceManifest,
    SourceManifestValidationError,
    validate_relative_path,
    validate_source_manifest,
)


INTAKE_SCHEMA_VERSION = "wp5-local-intake-0.1"
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_ALLOWED_EXTENSIONS = (".xy", ".xrdml")
_SHA256_LENGTH = 64
_ALLOWED_LICENSES = {
    "open",
    "permission_granted",
    "private_only",
    "pending",
    "denied",
    "unknown",
    "not_applicable",
}
_ALLOWED_RIGHTS = {"allowed", "pending", "denied", "unknown", "not_applicable"}
_ALLOWED_LABELS = {"complete", "incomplete", "unknown", "not_applicable"}
_ALLOWED_SOURCE_STATUSES = {"eligible", "excluded", "pending_rights", "missing_metadata", "unavailable"}
_UNKNOWN_METADATA = {"", "unknown", "unknown-until-record-inspected", "record-specific", "not-provided"}


class IntakeError(ValueError):
    """A named, fail-closed local intake error."""

    contract = "wp5_local_intake"

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class StagedFile:
    """Identity of one atomically staged source file."""

    relative_path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, *, field: str, allow_empty: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise IntakeError("field_invalid", f"{field} must be a string")
    return value


def _required_text(value: Any, *, field: str) -> str:
    result = _text(value, field=field)
    if result is None:
        raise IntakeError("field_required", f"{field} is required")
    return result


def _validate_sha(value: Any, *, field: str) -> str:
    result = _required_text(value, field=field).lower()
    if len(result) != _SHA256_LENGTH or any(character not in "0123456789abcdef" for character in result):
        raise IntakeError("hash_invalid", f"{field} must be a SHA-256 hexadecimal string")
    return result


def _validate_size(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IntakeError("size_invalid", f"{field} must be a non-negative integer")
    return value


def _validate_limit(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IntakeError("size_limit_invalid", "max_bytes must be a non-negative integer")
    return value


def _json_copy(value: Any, *, field: str) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise IntakeError("metadata_invalid", f"{field} must contain JSON-compatible finite values") from exc


def _absolute_without_resolution(path: Path) -> Path:
    """Return an absolute lexical path without following symlinks."""

    return path.expanduser().absolute()


def _assert_no_symlink_components(path: Path, *, code: str = "symlink_rejected") -> None:
    """Reject symlinks in an existing lexical path and its parents."""

    candidate = _absolute_without_resolution(path)
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            raise IntakeError(code, f"path contains a symlink: {path}")


def _has_symlink_components(path: Path) -> bool:
    """Return whether a lexical path contains a symlink component."""

    candidate = _absolute_without_resolution(path)
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _safe_root(path: str | Path, *, create: bool = False) -> Path:
    candidate = _absolute_without_resolution(Path(path))
    _assert_no_symlink_components(candidate)
    if candidate.exists() and not candidate.is_dir():
        raise IntakeError("root_invalid", f"root is not a directory: {path}")
    if not candidate.exists():
        if not create:
            raise IntakeError("root_missing", f"root directory does not exist: {path}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise IntakeError("root_unavailable", f"cannot create root directory: {path}") from exc
    # Do not resolve the root after the checks above: the lexical path is the
    # path that callers asked us to trust, and every component was checked.
    return candidate


def _hash_file(path: Path, *, max_bytes: int | None = None) -> tuple[int, str, os.stat_result]:
    try:
        before = path.stat()
        if not path.is_file() or path.is_symlink():
            raise IntakeError("file_unavailable", "source is not a regular file")
        if max_bytes is not None and before.st_size > max_bytes:
            raise IntakeError("size_limit", "source exceeds max_bytes")
        digest = hashlib.sha256()
        count = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                count += len(chunk)
                if max_bytes is not None and count > max_bytes:
                    raise IntakeError("size_limit", "source exceeds max_bytes")
                digest.update(chunk)
        after = path.stat()
    except IntakeError:
        raise
    except OSError as exc:
        raise IntakeError("file_unreadable", "source cannot be read") from exc
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise IntakeError("source_changed", "source changed while it was being read")
    return count, digest.hexdigest(), after


def _validate_relative(value: Any, *, field: str) -> str:
    try:
        return validate_relative_path(value, field, SourceManifestValidationError)
    except SourceManifestValidationError as exc:
        raise IntakeError(exc.code, exc.detail) from exc


def stage_local_file(
    source_path: str | Path,
    destination_root: str | Path,
    relative_path: str,
    *,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
) -> StagedFile:
    """Atomically copy one regular local file beneath ``destination_root``.

    The source may live outside the destination root, but neither source nor
    destination may contain symlink components. Existing identical bytes are
    accepted for resumable, idempotent intake; conflicting bytes never get
    overwritten. The returned digest is the digest of the staged bytes.
    """

    limit = _validate_limit(max_bytes)
    relative = _validate_relative(relative_path, field="destination relative path")
    source = _absolute_without_resolution(Path(source_path))
    _assert_no_symlink_components(source)
    if not source.exists() or not source.is_file():
        raise IntakeError("file_unavailable", f"source is not a regular file: {source_path}")

    root = _safe_root(destination_root, create=True)
    destination = root / relative
    _assert_no_symlink_components(destination)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IntakeError("destination_unavailable", "cannot create destination directory") from exc
    _assert_no_symlink_components(destination.parent)

    try:
        source_stat = source.stat()
    except OSError as exc:
        raise IntakeError("file_unreadable", "source cannot be inspected") from exc
    if limit is not None and source_stat.st_size > limit:
        raise IntakeError("size_limit", "source exceeds max_bytes")

    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            raise IntakeError("symlink_rejected", "destination is a symlink")
        if not destination.is_file():
            raise IntakeError("destination_conflict", "destination is not a regular file")
        existing_size, existing_hash, _ = _hash_file(destination, max_bytes=limit)
        if existing_size == source_stat.st_size:
            # The source is read below as a stream so we can compare bytes,
            # rather than trusting a mutable source's size and timestamp.
            source_size, source_hash, _ = _hash_file(source, max_bytes=limit)
            if source_size == existing_size and source_hash == existing_hash:
                return StagedFile(relative, existing_size, existing_hash)
        raise IntakeError("destination_conflict", "destination contains different bytes")

    temporary_name: str | None = None
    digest = hashlib.sha256()
    count = 0
    try:
        fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent)
        with os.fdopen(fd, "wb") as output:
            with source.open("rb") as input_stream:
                for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                    count += len(chunk)
                    if limit is not None and count > limit:
                        raise IntakeError("size_limit", "source exceeds max_bytes")
                    output.write(chunk)
                    digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        after = source.stat()
        if after.st_size != source_stat.st_size or after.st_mtime_ns != source_stat.st_mtime_ns:
            raise IntakeError("source_changed", "source changed while it was staged")
        _assert_no_symlink_components(destination.parent)
        try:
            # Hard-linking the private temporary file publishes it without an
            # overwrite race. The temporary name is removed afterwards.
            os.link(temporary_name, destination)
        except FileExistsError:
            if destination.is_symlink() or not destination.is_file():
                raise IntakeError("destination_conflict", "destination appeared as an unsafe path")
            existing_size, existing_hash, _ = _hash_file(destination, max_bytes=limit)
            if existing_size != count or existing_hash != digest.hexdigest():
                raise IntakeError("destination_conflict", "destination contains different bytes")
        return StagedFile(relative, count, digest.hexdigest())
    except IntakeError:
        raise
    except OSError as exc:
        raise IntakeError("stage_failed", "source could not be staged") from exc
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def _safe_reason(value: Any, default: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    return " ".join(value.split())[:500]


def _probe_scan(path: Path, suffix: str) -> dict[str, Any]:
    """Probe only a registered application parser; never infer by content."""

    parser: Callable[[Path], Any]
    if suffix == ".xy":
        parser = parse_xy
    elif suffix == ".xrdml":
        parser = parse_xrdml
    else:
        raise IntakeError("unsupported_format", f"no registered benchmark reader for {suffix or '<none>'}")
    try:
        pattern = parser(path)
    except Exception as exc:  # parser errors become explicit source states
        detail = " ".join(str(exc).split())[:240] or type(exc).__name__
        raise IntakeError("format_validation_failed", detail) from exc
    return {
        "status": "valid",
        "parser": str(pattern.metadata.get("parser", parser.__name__)),
        "source_format": pattern.source_format,
        "point_count": len(pattern.angles_deg),
        "angle_unit": pattern.angle_unit.value,
        "scan_range_deg": [pattern.angles_deg[0], pattern.angles_deg[-1]],
    }


def _record_metadata(value: Any, *, source_id: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise IntakeError("metadata_invalid", f"source {source_id} metadata must be an object")
    copied = _json_copy(value, field=f"source {source_id} metadata")
    if not isinstance(copied, dict):
        raise IntakeError("metadata_invalid", f"source {source_id} metadata must be an object")
    return copied


def _record_label_evidence(value: Any, *, source_id: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise IntakeError("label_evidence_invalid", f"source {source_id} label_evidence must be an array")
    return _json_copy(list(value), field=f"source {source_id} label_evidence")


def _measurement_metadata_issues(kind: str, metadata: Mapping[str, Any], *, source_id: str) -> list[str]:
    """Return explicit eligibility issues for unresolved scan metadata.

    A source URL or file suffix never supplies an anode or geometry. Measured
    records therefore need both values in the curated record before they can
    become eligible. Certificate/reference records are intentionally exempt.
    """

    if not kind.strip().lower().startswith("measured"):
        return []
    issues: list[str] = []
    radiation = metadata.get("radiation")
    if not isinstance(radiation, str) or radiation.strip().casefold() in _UNKNOWN_METADATA:
        issues.append("metadata_missing:radiation" if radiation is None else "metadata_unknown:radiation")
    else:
        try:
            get_radiation(radiation)
        except ValueError:
            issues.append("radiation_invalid")
    geometry = metadata.get("geometry")
    if not isinstance(geometry, str) or geometry.strip().casefold() in _UNKNOWN_METADATA:
        issues.append("metadata_missing:geometry" if geometry is None else "metadata_unknown:geometry")
    elif geometry != "reflection_bragg_brentano":
        issues.append("geometry_unsupported")
    return issues


def _effective_rights(
    record: Mapping[str, Any], metadata: dict[str, Any], source_id: str
) -> tuple[str, str, str, str | None, str | None, list[str]]:
    license_status = _text(record.get("license_status"), field=f"source {source_id}.license_status") or "unknown"
    local_use = _text(record.get("local_use_status"), field=f"source {source_id}.local_use_status") or "unknown"
    redistribution = (
        _text(record.get("redistribution_status"), field=f"source {source_id}.redistribution_status") or "unknown"
    )
    if license_status not in _ALLOWED_LICENSES:
        raise IntakeError("license_status_invalid", f"source {source_id} has unsupported license_status")
    if local_use not in _ALLOWED_RIGHTS or redistribution not in _ALLOWED_RIGHTS:
        raise IntakeError("rights_status_invalid", f"source {source_id} has unsupported rights status")
    license_evidence = _text(record.get("license_evidence_url"), field=f"source {source_id}.license_evidence_url")
    attribution = _text(record.get("attribution"), field=f"source {source_id}.attribution")
    rights_reasons: list[str] = []
    if license_status in {"open", "permission_granted"} and not license_evidence:
        metadata["declared_license_status"] = license_status
        license_status = "unknown"
        rights_reasons.append("license_evidence_missing")
    if not license_evidence and license_status == "unknown":
        rights_reasons.append("license_status_unknown")
    elif license_status in {"pending", "unknown"}:
        rights_reasons.append("license_status_unresolved")
    if local_use in {"unknown", "pending"}:
        rights_reasons.append("local_use_status_unresolved")
    if redistribution in {"unknown", "pending"}:
        rights_reasons.append("redistribution_status_unresolved")
    return license_status, local_use, redistribution, license_evidence, attribution, rights_reasons


def _inventory_record(
    root: Path,
    record: Mapping[str, Any],
    *,
    created_at: str,
    data_root: str,
    max_bytes: int | None,
    allowed_extensions: set[str],
    required_metadata: tuple[str, ...],
) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise IntakeError("record_invalid", "each source catalog entry must be an object")
    source_id = _required_text(record.get("source_id"), field="source_id")
    kind = _required_text(record.get("kind", "measured_scan"), field=f"source {source_id}.kind")
    declared_status = _text(record.get("status"), field=f"source {source_id}.status")
    if declared_status is not None and declared_status not in _ALLOWED_SOURCE_STATUSES:
        raise IntakeError("status_invalid", f"source {source_id} has unsupported status")
    source_url = _text(record.get("source_url"), field=f"source {source_id}.source_url")
    doi = _text(record.get("doi"), field=f"source {source_id}.doi")
    if source_url is None and doi is None:
        raise IntakeError("source_evidence_missing", f"source {source_id} needs source_url or doi")
    local_path_raw = record.get("local_path")
    local_path = (
        None
        if local_path_raw is None
        else _validate_relative(local_path_raw, field=f"source {source_id}.local_path")
    )
    raw_local_path_raw = record.get("raw_local_path")
    raw_local_path = (
        None
        if raw_local_path_raw is None
        else _validate_relative(raw_local_path_raw, field=f"source {source_id}.raw_local_path")
    )
    original_filename = _required_text(
        record.get("original_filename", Path(local_path).name if local_path else None),
        field=f"source {source_id}.original_filename",
    )
    metadata = _record_metadata(record.get("metadata"), source_id=source_id)
    label_evidence = _record_label_evidence(record.get("label_evidence"), source_id=source_id)
    label_status = _text(record.get("label_status"), field=f"source {source_id}.label_status") or "unknown"
    if label_status not in _ALLOWED_LABELS:
        raise IntakeError("label_status_invalid", f"source {source_id} has unsupported label_status")
    normalization = _json_copy(record.get("normalization", {}), field=f"source {source_id}.normalization")
    if not isinstance(normalization, dict):
        raise IntakeError("metadata_invalid", f"source {source_id}.normalization must be an object")

    expected_sha_raw = record.get("expected_sha256", record.get("sha256"))
    expected_sha = (
        None
        if expected_sha_raw is None
        else _validate_sha(expected_sha_raw, field=f"source {source_id}.expected_sha256")
    )
    expected_size_raw = record.get("expected_size_bytes", record.get("size_bytes"))
    expected_size = (
        None
        if expected_size_raw is None
        else _validate_size(expected_size_raw, field=f"source {source_id}.expected_size_bytes")
    )
    raw_expected_sha_raw = record.get("raw_expected_sha256", record.get("raw_sha256"))
    raw_expected_sha = (
        None
        if raw_expected_sha_raw is None
        else _validate_sha(raw_expected_sha_raw, field=f"source {source_id}.raw_expected_sha256")
    )
    raw_expected_size_raw = record.get("raw_expected_size_bytes", record.get("raw_size_bytes"))
    raw_expected_size = (
        None
        if raw_expected_size_raw is None
        else _validate_size(raw_expected_size_raw, field=f"source {source_id}.raw_expected_size_bytes")
    )

    license_status, local_use, redistribution, license_evidence, attribution, rights_reasons = _effective_rights(
        record, metadata, source_id
    )
    metadata["intake_schema_version"] = INTAKE_SCHEMA_VERSION
    metadata["observed_suffix"] = Path(original_filename).suffix.lower()
    if expected_sha is not None:
        metadata["expected_sha256"] = expected_sha
    if expected_size is not None:
        metadata["expected_size_bytes"] = expected_size
    if raw_expected_sha is not None:
        metadata["raw_expected_sha256"] = raw_expected_sha
    if raw_expected_size is not None:
        metadata["raw_expected_size_bytes"] = raw_expected_size

    observed_sha: str | None = None
    observed_size: int | None = None
    observed_raw_sha: str | None = None
    observed_raw_size: int | None = None
    status = "eligible"
    reasons: list[str] = []
    reasons.extend(_measurement_metadata_issues(kind, metadata, source_id=source_id))
    path = None
    declared_root = root / data_root
    if local_path is not None:
        # Manifests in the wild use both documented layouts: paths relative
        # to the manifest root (``data/scan.xy``) and paths relative to the
        # declared data_root (``scan.xy`` with data_root ``data``). Support
        # both only when they do not produce conflicting bytes.
        candidates = [root / local_path]
        if declared_root != root:
            candidates.append(declared_root / local_path)
        existing = [candidate for candidate in candidates if candidate.exists() or candidate.is_symlink()]
        if len(existing) > 1 and all(
            not _has_symlink_components(candidate) and candidate.is_file() for candidate in existing
        ):
            identities = {_hash_file(candidate, max_bytes=max_bytes)[1] for candidate in existing}
            if len(identities) > 1:
                raise IntakeError("path_ambiguous", f"source {source_id} resolves to conflicting local files")
        path = existing[0] if existing else candidates[0]
    if path is None:
        status = "unavailable"
        reasons.append("local_file_not_provided")
    else:
        # Traversal is a malformed catalog and is rejected before any file
        # operation. A symlink is retained as an explicit exclusion.
        if _has_symlink_components(path):
            status = "excluded"
            reasons.append("symlink_rejected")
        elif not path.exists():
            status = "unavailable"
            reasons.append("local_file_missing")
        elif not path.is_file():
            status = "unavailable"
            reasons.append("local_file_not_regular")
        else:
            try:
                observed_size, observed_sha, _ = _hash_file(path, max_bytes=max_bytes)
            except IntakeError as exc:
                status = "excluded" if exc.code in {"size_limit", "source_changed"} else "unavailable"
                reasons.append(exc.code)
            if observed_sha is not None:
                suffix = path.suffix.lower()
                if expected_sha is not None and observed_sha != expected_sha:
                    status = "excluded"
                    reasons.append("hash_mismatch")
                if expected_size is not None and observed_size != expected_size:
                    status = "excluded"
                    reasons.append("size_mismatch")
                if suffix not in allowed_extensions:
                    status = "excluded"
                    reasons.append(f"unsupported_format:{suffix or '<none>'}")
                    metadata["format_validation"] = "not_registered"
                else:
                    try:
                        probe = _probe_scan(path, suffix)
                    except IntakeError as exc:
                        status = "excluded"
                        reasons.append(exc.code)
                        metadata["format_validation"] = "failed"
                        metadata["format_validation_error"] = exc.detail
                    else:
                        metadata["format_validation"] = "valid"
                        metadata["format_probe"] = probe

    # A converted benchmark source keeps its original legacy bytes alongside
    # the normalized reader input. Authenticate those bytes independently;
    # losing the raw audit source makes the record unavailable even if the
    # normalized copy parses successfully.
    if raw_local_path is not None:
        raw_candidates = [root / raw_local_path]
        if declared_root != root:
            raw_candidates.append(declared_root / raw_local_path)
        existing_raw = [candidate for candidate in raw_candidates if candidate.exists() or candidate.is_symlink()]
        raw_path = existing_raw[0] if existing_raw else raw_candidates[0]
        if _has_symlink_components(raw_path):
            status = "excluded"
            reasons.append("raw_symlink_rejected")
        elif not raw_path.exists():
            status = "unavailable"
            reasons.append("raw_file_missing")
        elif not raw_path.is_file():
            status = "unavailable"
            reasons.append("raw_file_not_regular")
        else:
            try:
                observed_raw_size, observed_raw_sha, _ = _hash_file(raw_path, max_bytes=max_bytes)
            except IntakeError as exc:
                status = "excluded" if exc.code in {"size_limit", "source_changed"} else "unavailable"
                reasons.append(f"raw_{exc.code}")
            if observed_raw_sha is not None:
                if raw_expected_sha is not None and observed_raw_sha != raw_expected_sha:
                    status = "excluded"
                    reasons.append("raw_hash_mismatch")
                if raw_expected_size is not None and observed_raw_size != raw_expected_size:
                    status = "excluded"
                    reasons.append("raw_size_mismatch")

    # Preserve rights findings alongside metadata/file findings, even when a
    # different blocker determines the final status.
    if rights_reasons:
        reasons.extend(rights_reasons)

    if status == "eligible":
        if any(reason.startswith(("metadata_missing:", "metadata_unknown:")) for reason in reasons):
            status = "missing_metadata"
        elif any(reason in {"radiation_invalid", "geometry_unsupported"} for reason in reasons):
            status = "excluded"
        elif any(
            reason in {"local_file_missing", "local_file_not_provided", "local_file_not_regular"}
            for reason in reasons
        ):
            status = "unavailable"
        elif rights_reasons:
            status = "missing_metadata" if "license_evidence_missing" in rights_reasons else "pending_rights"
            reasons.extend(rights_reasons)
        elif local_use == "denied" or redistribution == "denied" or license_status in {"denied", "private_only"}:
            status = "excluded"
            reasons.append("rights_denied")
        elif label_status == "complete" and not label_evidence:
            metadata["declared_label_status"] = label_status
            label_status = "unknown"
            status = "missing_metadata"
            reasons.append("label_evidence_missing")
        elif not attribution:
            status = "missing_metadata"
            reasons.append("attribution_missing")
        else:
            missing_metadata = [key for key in required_metadata if key not in record and key not in metadata]
            if missing_metadata:
                status = "missing_metadata"
                reasons.extend(f"metadata_missing:{key}" for key in missing_metadata)
    if local_use == "denied" or redistribution == "denied" or license_status in {"denied", "private_only"}:
        if status not in {"unavailable", "excluded"}:
            status = "excluded"
        reasons.append("rights_denied")

    # A catalog may intentionally quarantine an otherwise readable source
    # while a curator resolves rights or labels. Preserve every explicit
    # non-eligible state; never upgrade it merely because local bytes happen
    # to be present. ``pending_rights`` with fully resolved rights is a
    # contradictory catalog and fails closed rather than being rewritten.
    if declared_status == "pending_rights":
        rights_resolved = license_status in {"open", "permission_granted", "not_applicable"}
        if local_use == "allowed" and redistribution == "allowed" and rights_resolved:
            raise IntakeError(
                "status_inconsistent",
                f"source {source_id} declares pending_rights with resolved rights",
            )
        status = "pending_rights"
        reasons.append("declared_status:pending_rights")
    elif declared_status in {"excluded", "missing_metadata", "unavailable"}:
        status = declared_status
        reasons.append(f"declared_status:{declared_status}")

    reason = _safe_reason(record.get("reason"), "")
    if not reason:
        reason = "; ".join(dict.fromkeys(reasons))
    else:
        reason = "; ".join(dict.fromkeys([reason, *reasons]))
    if status == "eligible" and not reason:
        reason = "File authenticated; source evidence and rights metadata recorded."
    if not reason:
        reason = "Source was retained with an explicit intake state."

    payload: dict[str, Any] = {
        "source_id": source_id,
        "kind": kind,
        "source_url": source_url,
        "doi": doi,
        "original_filename": original_filename,
        "local_path": local_path,
        "raw_local_path": raw_local_path if observed_raw_sha is not None else None,
        "raw_size_bytes": observed_raw_size,
        "raw_sha256": observed_raw_sha,
        "size_bytes": observed_size,
        "sha256": observed_sha,
        "accessed_at": _text(record.get("accessed_at"), field=f"source {source_id}.accessed_at") or created_at,
        "license_status": license_status,
        "license_evidence_url": license_evidence,
        "attribution": attribution,
        "local_use_status": local_use,
        "redistribution_status": redistribution,
        "instrument_metadata_source": _text(
            record.get("instrument_metadata_source"), field=f"source {source_id}.instrument_metadata_source"
        ),
        "normalization": normalization,
        "status": status,
        "reason": reason,
        "label_status": label_status,
        "label_evidence": label_evidence,
        "metadata": metadata,
    }
    if raw_local_path is not None:
        payload["metadata"] = {
            **dict(payload["metadata"]),
            "raw_local_path_declared": raw_local_path,
            "raw_identity_status": "authenticated" if observed_raw_sha is not None else "unavailable",
        }
    return payload


def inventory_source_manifest(
    manifest_root: str | Path,
    records: Iterable[Mapping[str, Any]],
    *,
    manifest_id: str,
    data_root: str = "inputs",
    created_at: str | None = None,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
    allowed_extensions: Sequence[str] = DEFAULT_ALLOWED_EXTENSIONS,
    required_metadata: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> SourceManifest:
    """Inventory a curated local catalog into a validated source manifest.

    ``manifest_root`` is the directory against which each catalog
    ``local_path`` is resolved. The returned manifest is sorted by
    ``source_id`` and can be written with :func:`write_source_manifest`.
    Missing or unusable local files are represented in the result; malformed
    catalog paths, records, and provenance fields fail closed with
    :class:`IntakeError`.
    """

    root = _safe_root(manifest_root)
    limit = _validate_limit(max_bytes)
    created = created_at or _now()
    if not isinstance(created, str) or not created.strip():
        raise IntakeError("timestamp_invalid", "created_at must be an ISO-8601 timestamp")
    try:
        data_root_value = _validate_relative(data_root, field="data_root")
        # Reuse the source contract's timestamp checker by validating the
        # completed manifest below; this keeps errors consistent.
        allowed = {str(item).lower() for item in allowed_extensions}
        if any(not item.startswith(".") or item != item.lower() for item in allowed):
            raise IntakeError("extension_invalid", "allowed_extensions must contain lower-case dotted suffixes")
        required = tuple(_required_text(item, field="required_metadata") for item in required_metadata)
        catalog = list(records)
    except TypeError as exc:
        raise IntakeError("records_invalid", "records must be an iterable of objects") from exc
    if not catalog:
        raise IntakeError("records_empty", "source catalog must contain at least one record")

    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for record in catalog:
        if not isinstance(record, Mapping):
            raise IntakeError("record_invalid", "each source catalog entry must be an object")
        source_id = record.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise IntakeError("field_required", "source_id is required")
        if source_id in seen:
            raise IntakeError("identifier_duplicate", f"duplicate source_id: {source_id}")
        seen.add(source_id)
        entries.append(
            _inventory_record(
                root,
                record,
                created_at=created,
                data_root=data_root_value,
                max_bytes=limit,
                allowed_extensions=allowed,
                required_metadata=required,
            )
        )
    entries.sort(key=lambda item: item["source_id"])

    # Byte duplicates are preserved and grouped; no source is removed.
    by_hash: dict[str, list[str]] = {}
    for entry in entries:
        if entry.get("sha256"):
            by_hash.setdefault(str(entry["sha256"]), []).append(str(entry["source_id"]))
    duplicate_groups: list[dict[str, Any]] = []
    for digest, source_ids in sorted(by_hash.items()):
        if len(source_ids) < 2:
            continue
        group_id = f"byte-{digest[:16]}"
        for entry in entries:
            if entry.get("sha256") == digest:
                entry["metadata"] = {
                    **dict(entry["metadata"]),
                    "duplicate_group_id": group_id,
                }
        duplicate_groups.append({"group_id": group_id, "source_ids": sorted(source_ids)})

    manifest_metadata = _json_copy(metadata or {}, field="manifest metadata")
    if not isinstance(manifest_metadata, dict):
        raise IntakeError("metadata_invalid", "manifest metadata must be an object")
    manifest_metadata.update(
        {
            "intake_schema_version": INTAKE_SCHEMA_VERSION,
            "allowed_extensions": sorted(allowed),
            "max_bytes": limit,
            "duplicate_groups": duplicate_groups,
        }
    )
    payload = {
        "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "status": "inventory",
        "created_at": created,
        "data_root": data_root_value,
        "sources": entries,
        "metadata": manifest_metadata,
    }
    try:
        return validate_source_manifest(payload)
    except SourceManifestValidationError as exc:
        raise IntakeError("manifest_invalid", exc.detail) from exc


def source_status_counts(manifest: SourceManifest | Mapping[str, Any]) -> dict[str, int]:
    """Return non-zero source-state counts after strict validation."""

    typed = manifest if isinstance(manifest, SourceManifest) else validate_source_manifest(manifest)
    counts = Counter(source.status for source in typed.sources)
    return {status: counts[status] for status in sorted(_ALLOWED_SOURCE_STATUSES) if counts[status]}


def write_source_manifest(path: str | Path, manifest: SourceManifest | Mapping[str, Any]) -> None:
    """Write a validated source manifest using the shared atomic JSON writer."""

    typed = manifest if isinstance(manifest, SourceManifest) else validate_source_manifest(manifest)
    destination = Path(path).expanduser()
    _assert_no_symlink_components(destination.parent)
    write_json_atomic(destination, typed.to_dict())


__all__ = [
    "DEFAULT_ALLOWED_EXTENSIONS",
    "DEFAULT_MAX_BYTES",
    "INTAKE_SCHEMA_VERSION",
    "IntakeError",
    "StagedFile",
    "inventory_source_manifest",
    "source_status_counts",
    "stage_local_file",
    "write_source_manifest",
]
