"""Atomic, hash-addressed WP-5 artifact helpers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


class WP5ArtifactError(ValueError):
    """Raised when a WP-5 artifact cannot be trusted."""


def canonical_bytes(value: Any) -> bytes:
    """Encode JSON semantically, independent of whitespace or key order."""

    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WP5ArtifactError("payload is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# Multi-gigabyte reference files (POW_COD source and cache) are hashed for
# every run identity. Re-reading ~6 GB per call dominated per-case runs, so
# digests are memoized in-process, keyed by the file's full stat identity
# (device, inode, size, mtime_ns, ctime_ns). Any rewrite changes that identity
# and forces a fresh hash; nothing is persisted across processes.
_SHA256_MEMO: dict[tuple[str, int, int, int, int, int], str] = {}


def _stat_identity(path: Path) -> tuple[str, int, int, int, int, int]:
    resolved = Path(path).resolve()
    stat = resolved.stat()
    return (str(resolved), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def sha256_file(path: Path) -> str:
    try:
        identity = _stat_identity(path)
    except OSError as exc:
        raise WP5ArtifactError(f"cannot read artifact: {path}") from exc
    cached = _SHA256_MEMO.get(identity)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise WP5ArtifactError(f"cannot read artifact: {path}") from exc
    value = digest.hexdigest()
    try:
        if _stat_identity(path) == identity:
            _SHA256_MEMO[identity] = value
    except OSError:
        pass
    return value


def _safe_relative(path: str, root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute() and ".." in candidate.parts:
        raise WP5ArtifactError(f"artifact path is not safe: {path}")
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        return target.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise WP5ArtifactError(f"artifact path escapes root: {path}") from exc


def write_json_atomic(path: Path, payload: Any) -> None:
    """Write canonical human-readable JSON without exposing partial output."""

    path = Path(path)
    if path.exists() and path.is_symlink():
        raise WP5ArtifactError(f"artifact must not be a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def artifact_record(path: Path, root: Path, *, kind: str = "artifact", extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a relative, hash-addressed record for a file under ``root``."""

    path = Path(path)
    root = Path(root).resolve()
    if not path.is_file() or path.is_symlink():
        raise WP5ArtifactError(f"artifact is missing or unsafe: {path}")
    relative = _safe_relative(str(path), root)
    record: dict[str, Any] = {
        "path": relative,
        "kind": str(kind),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }
    if extra:
        record.update({str(key): value for key, value in extra.items()})
    return record


def verify_artifact_record(record: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Verify one record and return a small status payload."""

    if not isinstance(record, Mapping):
        raise WP5ArtifactError("artifact record must be an object")
    relative = record.get("path")
    if not isinstance(relative, str) or not relative.strip():
        raise WP5ArtifactError("artifact record path is missing")
    relative = _safe_relative(relative, Path(root).resolve())
    path = Path(root).resolve() / relative
    if not path.is_file() or path.is_symlink():
        raise WP5ArtifactError(f"artifact is missing or unsafe: {relative}")
    expected_hash = record.get("sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise WP5ArtifactError(f"artifact hash is invalid: {relative}")
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash.lower():
        raise WP5ArtifactError(f"artifact hash does not match: {relative}")
    expected_size = record.get("size_bytes")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size != path.stat().st_size:
        raise WP5ArtifactError(f"artifact size does not match: {relative}")
    return {"status": "valid", "path": relative, "sha256": actual_hash, "size_bytes": expected_size}


