"""Hash-authenticated local source handling for WP-5 manifests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .contracts import SourceManifest, SourceManifestValidationError, validate_relative_path, validate_source_manifest


class SourcePathError(ValueError):
    """Raised when a source path or byte identity cannot be trusted."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def hash_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return a streaming SHA-256 digest for one regular file."""

    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
        raise SourcePathError("chunk_size_invalid", "hash chunk_size must be a positive integer")
    candidate = Path(path)
    try:
        if not candidate.is_file() or candidate.is_symlink():
            raise SourcePathError("file_missing", f"source file is not a regular file: {candidate.name}")
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(chunk_size), b""):
                digest.update(chunk)
    except SourcePathError:
        raise
    except OSError as exc:
        raise SourcePathError("file_unreadable", "source file cannot be read") from exc
    return digest.hexdigest()


def resolve_contained_path(
    root: str | Path,
    relative_path: str,
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve a manifest path and prove it stays inside ``root``.

    Resolution follows symlinks before containment is checked, preventing a
    seemingly safe path such as ``link/scan.xy`` from escaping the data root.
    """

    try:
        validate_relative_path(relative_path, "source path", SourceManifestValidationError)
    except SourceManifestValidationError as exc:
        raise SourcePathError(exc.code, exc.detail) from exc
    root_path = Path(root).expanduser().resolve(strict=False)
    candidate = root_path / relative_path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root_path)
    except (OSError, ValueError) as exc:
        raise SourcePathError("path_unsafe", "source path escapes the configured data root") from exc
    if must_exist and (not resolved.is_file() or candidate.is_symlink()):
        raise SourcePathError("file_missing", "source path does not resolve to a regular file")
    return resolved


def validate_source_file(
    path: str | Path,
    *,
    root: str | Path,
    relative_path: str,
    expected_sha256: str | None = None,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    """Authenticate one source file against its contained manifest identity."""

    resolved = resolve_contained_path(root, relative_path, must_exist=True)
    supplied = Path(path).expanduser().resolve(strict=False)
    if supplied != resolved:
        raise SourcePathError("path_mismatch", "source path does not match its contained manifest path")
    try:
        size_bytes = resolved.stat().st_size
    except OSError as exc:
        raise SourcePathError("file_unreadable", "source file cannot be inspected") from exc
    if max_bytes is not None and (isinstance(max_bytes, bool) or max_bytes < 0 or size_bytes > max_bytes):
        raise SourcePathError("size_limit", "source file exceeds the configured size limit")
    digest = hash_file(resolved)
    if expected_sha256 is not None and digest != expected_sha256.lower():
        raise SourcePathError("hash_mismatch", "source file hash does not match the manifest")
    return {
        "path": relative_path,
        "resolved_path": str(resolved),
        "size_bytes": size_bytes,
        "sha256": digest,
    }


def verify_source_manifest_files(
    manifest: SourceManifest | Mapping[str, Any],
    data_root: str | Path,
    *,
    max_bytes: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """Verify every eligible source asset and preserve status for exclusions.

    Non-eligible records are returned with their explicit status/reason and do
    not get silently converted into missing-file failures.  Eligible records
    must have a contained path and matching byte identity.
    """

    typed = manifest if isinstance(manifest, SourceManifest) else validate_source_manifest(manifest)
    results: list[dict[str, Any]] = []
    for source in typed.sources:
        base = {"source_id": source.source_id, "status": source.status, "reason": source.reason}
        if source.status != "eligible":
            results.append(base)
            continue
        if source.local_path is None or source.sha256 is None or source.size_bytes is None:
            raise SourcePathError("source_file_missing", f"eligible source {source.source_id} lacks file identity")
        checked = validate_source_file(
            Path(data_root) / source.local_path,
            root=data_root,
            relative_path=source.local_path,
            expected_sha256=source.sha256,
            max_bytes=max_bytes,
        )
        if checked["size_bytes"] != source.size_bytes:
            raise SourcePathError("size_mismatch", f"source {source.source_id} size does not match the manifest")
        if source.raw_local_path is not None and source.raw_sha256 is not None and source.raw_size_bytes is not None:
            raw_checked = validate_source_file(
                Path(data_root) / source.raw_local_path,
                root=data_root,
                relative_path=source.raw_local_path,
                expected_sha256=source.raw_sha256,
                max_bytes=max_bytes,
            )
            if raw_checked["size_bytes"] != source.raw_size_bytes:
                raise SourcePathError("raw_size_mismatch", f"source {source.source_id} raw size does not match the manifest")
            results.append({**base, **checked, "raw_path": source.raw_local_path, "raw_size_bytes": raw_checked["size_bytes"], "raw_sha256": raw_checked["sha256"]})
        else:
            results.append({**base, **checked})
    return tuple(results)


__all__ = [
    "SourcePathError",
    "hash_file",
    "resolve_contained_path",
    "validate_source_file",
    "verify_source_manifest_files",
]
