"""Resumable, local WP-5 evaluation execution.

The runner has one narrow dependency: a callable receiving an immutable input
path and a case mapping, and returning a JSON-serialisable analysis result.
The caller supplies a wrapper around ``phasentic.reporting.service`` when
production execution is wanted.  Keeping that wrapper outside this module
prevents benchmark fixtures from becoming an accidental replacement for the
production reference store.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from types import MappingProxyType
from typing import Any, TypeAlias


class RunnerValidationError(ValueError):
    """Raised when a run or case contract cannot be safely executed."""


class RunnerIdentityError(RunnerValidationError):
    """Raised when a prior run cannot be reused under the requested identity."""


AnalysisCallable: TypeAlias = Callable[[Path, Mapping[str, Any]], Any]

_SCHEMA_VERSION = "wp5-run-0.1"
_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_MANIFEST = "run.json"


def _canonical_payload(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunnerValidationError("run metadata/result is not canonical JSON") from exc


def canonical_run_sha256(value: Any) -> str:
    """Hash JSON semantics independently of dictionary insertion order."""

    return hashlib.sha256(_canonical_payload(value)).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RunnerValidationError(f"cannot read benchmark input: {path}") from exc
    return digest.hexdigest()


def _safe_case_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or not _CASE_ID.fullmatch(value.strip()):
        raise RunnerValidationError("case_id must contain only safe filename characters")
    return value.strip()


def _safe_hash(value: Any, context: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or not _SHA256.fullmatch(value.lower()):
        raise RunnerValidationError(f"{context} must be a lowercase SHA-256 hash")
    return value.lower()


def _input_path(case: Mapping[str, Any], data_root: Path) -> Path:
    # A normalized copy is preferred when present.  Raw-only measured inputs
    # remain valid benchmark cases, so an explicit ``None`` normalized path
    # must fall through to the raw/input path instead of becoming a missing
    # path error.
    raw = case.get("normalized_path") or case.get("input_path") or case.get("path") or case.get("raw_path")
    if not isinstance(raw, (str, Path)) or not str(raw).strip():
        raise RunnerValidationError(f"case {_safe_case_id(case.get('case_id'))} has no normalized input path")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = data_root / candidate
    if candidate.is_symlink():
        raise RunnerValidationError(f"benchmark input must not be a symlink: {raw}")
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise RunnerValidationError(f"benchmark input is not a regular file: {raw}")
    return resolved


def _declared_path(value: Any, data_root: Path, *, context: str) -> Path:
    """Resolve one manifest path without allowing a caller to escape root."""

    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise RunnerValidationError(f"{context} is missing")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = data_root / candidate
    if candidate.is_symlink():
        raise RunnerValidationError(f"benchmark input must not be a symlink: {value}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(data_root.resolve())
    except ValueError as exc:
        raise RunnerValidationError(f"{context} escapes the benchmark data root") from exc
    if not resolved.is_file():
        raise RunnerValidationError(f"benchmark input is not a regular file: {value}")
    return resolved


def _serializable_output(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
    elif isinstance(value, Mapping):
        value = dict(value)
    try:
        # Round-trip also rejects NaN/Infinity and custom objects that would
        # otherwise make an artifact impossible to replay.
        return json.loads(_canonical_payload(value).decode("utf-8"))
    except RunnerValidationError:
        raise
    except (TypeError, ValueError) as exc:
        raise RunnerValidationError("analysis callable returned a non-JSON result") from exc


def _atomic_write(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_payload(payload)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerValidationError(f"cannot read run artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise RunnerValidationError(f"run artifact must contain an object: {path}")
    return payload


def _identity_payload(
    cases: Sequence[Mapping[str, Any]], identity: Mapping[str, Any], data_root: Path
) -> dict[str, Any]:
    if not isinstance(identity, Mapping):
        raise RunnerValidationError("run identity must be an object")
    if isinstance(cases, (str, bytes)) or not cases:
        raise RunnerValidationError("run cases must contain at least one case")
    # These five identities are the minimum boundary required to prove that a
    # resumed result used the same scientific computation.  The input hash
    # manifest is derived below from the actual bytes for every case.
    for field in ("settings_hash", "index_hash", "protocol_hash", "algorithm_hash", "environment_hash"):
        if field not in identity:
            raise RunnerValidationError(f"run identity is missing {field}")
        _safe_hash(identity[field], f"identity.{field}")
    normalised_cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise RunnerValidationError(f"case {index} must be an object")
        case_id = _safe_case_id(case.get("case_id", case.get("id")))
        if case_id in seen:
            raise RunnerValidationError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        input_file = _input_path(case, data_root)
        actual_hash = _hash_file(input_file)
        if "input_sha256" in case:
            declared_value = case.get("input_sha256")
        elif case.get("normalized_path"):
            declared_value = case.get("normalized_sha256")
        else:
            declared_value = case.get("raw_sha256")
        declared_hash = _safe_hash(declared_value, f"case {case_id}.input_sha256")
        if declared_hash and declared_hash != actual_hash:
            raise RunnerIdentityError(f"input hash for case {case_id} does not match the local file")
        # WP-5 case manifests always retain raw bytes even when a normalized
        # copy is used for analysis.  Authenticate that second identity too,
        # so a resumed run cannot pair a valid normalized export with a
        # different source scan.
        if case.get("raw_path") is not None and case.get("raw_sha256") is not None:
            raw_file = _declared_path(case.get("raw_path"), data_root, context=f"case {case_id}.raw_path")
            raw_hash = _hash_file(raw_file)
            declared_raw = _safe_hash(case.get("raw_sha256"), f"case {case_id}.raw_sha256")
            if declared_raw != raw_hash:
                raise RunnerIdentityError(f"raw hash for case {case_id} does not match the local file")
        normalised_cases.append({"case_id": case_id, "input_sha256": actual_hash})
    normalised_cases.sort(key=lambda item: item["case_id"])
    # Retain all caller-provided semantic identities.  The input manifest is
    # derived from bytes, so moving the same input file does not invalidate a
    # run while changing the bytes necessarily does.
    try:
        identity_copy = json.loads(_canonical_payload(dict(identity)).decode("utf-8"))
    except RunnerValidationError:
        raise RunnerValidationError("run identity must be JSON serialisable")
    return {
        "fields": identity_copy,
        "input_manifest": normalised_cases,
    }



class EvaluationRunner:
    """Run case rows one at a time with atomic artifacts and strict resume."""

    def __init__(
        self,
        output_dir: str | Path,
        analysis_callable: AnalysisCallable,
        *,
        data_root: str | Path | None = None,
    ) -> None:
        if not callable(analysis_callable):
            raise RunnerValidationError("analysis_callable must be callable")
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.data_root = Path(data_root).expanduser().resolve() if data_root is not None else Path.cwd().resolve()
        self.analysis_callable = analysis_callable
        self.artifacts_dir = self.output_dir / "cases"
        self.manifest_path = self.output_dir / _RUN_MANIFEST

    def _initial_manifest(
        self,
        cases: Sequence[Mapping[str, Any]],
        identity: Mapping[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        identity_payload = _identity_payload(cases, identity, self.data_root)
        identity_sha = canonical_run_sha256(identity_payload)
        normalised_cases = identity_payload["input_manifest"]
        case_rows = [
            {
                "case_id": item["case_id"],
                "input_sha256": item["input_sha256"],
                "status": "pending",
                "artifact": f"cases/{item['case_id']}.json",
                "artifact_sha256": None,
                "error": None,
            }
            for item in normalised_cases
        ]
        manifest = {
            "schema_version": _SCHEMA_VERSION,
            "status": "running",
            "identity": identity_payload,
            "identity_sha256": identity_sha,
            "case_count": len(case_rows),
            "completed_case_count": 0,
            "failure_count": 0,
            "pending_case_count": len(case_rows),
            "cases": case_rows,
        }
        return manifest, case_rows

    def _load_or_create(
        self,
        cases: Sequence[Mapping[str, Any]],
        identity: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected, _ = self._initial_manifest(cases, identity)
        if self.manifest_path.exists():
            if self.manifest_path.is_symlink():
                raise RunnerIdentityError("existing run manifest must not be a symlink")
            current = _read_json(self.manifest_path)
            if current.get("schema_version") != _SCHEMA_VERSION:
                raise RunnerIdentityError("existing run uses an unsupported schema version")
            if current.get("identity_sha256") != expected["identity_sha256"]:
                raise RunnerIdentityError("existing run identity differs; prior case results cannot be reused")
            if current.get("identity") != expected["identity"]:
                raise RunnerIdentityError("existing run identity payload differs")
            expected_ids = [row["case_id"] for row in expected["cases"]]
            current_rows = current.get("cases")
            if not isinstance(current_rows, list) or [row.get("case_id") for row in current_rows] != expected_ids:
                raise RunnerIdentityError("existing run case manifest differs")
            return current
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.manifest_path, expected)
        return expected

    def _load_compatible_artifact(
        self,
        summary: Mapping[str, Any],
        *,
        run_identity_sha256: str,
    ) -> dict[str, Any] | None:
        if summary.get("status") not in {"complete", "failed"}:
            return None
        relative = summary.get("artifact")
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise RunnerValidationError(f"case {summary.get('case_id')} has an unsafe artifact path")
        candidate_artifact = self.output_dir / relative
        if candidate_artifact.is_symlink():
            raise RunnerIdentityError(f"case {summary.get('case_id')} artifact must not be a symlink")
        artifact = candidate_artifact.resolve()
        try:
            artifact.relative_to(self.output_dir)
        except ValueError as exc:
            raise RunnerValidationError(f"case {summary.get('case_id')} artifact escapes run directory") from exc
        if not artifact.is_file():
            raise RunnerIdentityError(f"case {summary.get('case_id')} artifact is missing")
        actual_hash = _hash_file(artifact)
        if actual_hash != summary.get("artifact_sha256"):
            raise RunnerIdentityError(f"case {summary.get('case_id')} artifact hash does not match manifest")
        payload = _read_json(artifact)
        if (
            payload.get("schema_version") != _SCHEMA_VERSION
            or payload.get("run_identity_sha256") != run_identity_sha256
            or payload.get("status") != summary.get("status")
        ):
            raise RunnerIdentityError(f"case {summary.get('case_id')} artifact belongs to another run")
        if payload.get("case_id") != summary.get("case_id") or payload.get("input_sha256") != summary.get("input_sha256"):
            raise RunnerIdentityError(f"case {summary.get('case_id')} artifact identity does not match manifest")
        return payload

    def _write_case(
        self,
        case: Mapping[str, Any],
        *,
        run_identity_sha256: str,
    ) -> tuple[dict[str, Any], str]:
        case_id = _safe_case_id(case.get("case_id", case.get("id")))
        input_file = _input_path(case, self.data_root)
        input_hash = _hash_file(input_file)
        declared = _safe_hash(case.get("input_sha256", case.get("normalized_sha256")), f"case {case_id}.input_sha256")
        if declared and declared != input_hash:
            raise RunnerIdentityError(f"input hash for case {case_id} changed during execution")
        payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "case_id": case_id,
            "input_sha256": input_hash,
            "run_identity_sha256": run_identity_sha256,
            "status": "complete",
            "result": None,
            "error": None,
        }
        try:
            result = self.analysis_callable(input_file, MappingProxyType(dict(case)))
            payload["result"] = _serializable_output(result)
            if _hash_file(input_file) != input_hash:
                raise RunnerIdentityError(f"input file for case {case_id} changed during analysis")
        except Exception as exc:  # Per-case failures are evidence, not a run abort.
            payload["status"] = "failed"
            payload["result"] = None
            payload["error"] = {"type": type(exc).__name__, "message": str(exc)}
        relative = Path("cases") / f"{case_id}.json"
        artifact_hash = _atomic_write(self.output_dir / relative, payload)
        summary = {
            "case_id": case_id,
            "input_sha256": input_hash,
            "status": payload["status"],
            "artifact": relative.as_posix(),
            "artifact_sha256": artifact_hash,
            "error": payload["error"],
        }
        return summary, artifact_hash

    def run(
        self,
        cases: Sequence[Mapping[str, Any]],
        *,
        identity: Mapping[str, Any],
        max_cases: int | None = None,
    ) -> dict[str, Any]:
        """Execute or resume cases under one immutable run identity.

        ``max_cases`` is useful for controlled interruption tests and for an
        operator who wants bounded foreground work.  A normal invocation
        leaves no pending rows unless an external interruption occurs.
        """

        if max_cases is not None and (
            isinstance(max_cases, bool) or not isinstance(max_cases, int) or max_cases < 1
        ):
            raise RunnerValidationError("max_cases must be a positive integer when provided")
        expected, _ = self._initial_manifest(cases, identity)
        manifest = self._load_or_create(cases, identity)
        run_identity_sha = str(manifest["identity_sha256"])
        rows_by_id = {str(row["case_id"]): row for row in cases}
        processed = 0
        for summary in list(manifest["cases"]):
            case_id = str(summary["case_id"])
            if summary.get("status") in {"complete", "failed"}:
                self._load_compatible_artifact(summary, run_identity_sha256=run_identity_sha)
                continue
            if max_cases is not None and processed >= max_cases:
                break
            case = rows_by_id[case_id]
            updated, _ = self._write_case(case, run_identity_sha256=run_identity_sha)
            summary.clear()
            summary.update(updated)
            processed += 1
            completed = sum(row.get("status") in {"complete", "failed"} for row in manifest["cases"])
            failures = sum(row.get("status") == "failed" for row in manifest["cases"])
            pending = len(manifest["cases"]) - completed
            manifest["completed_case_count"] = completed
            manifest["failure_count"] = failures
            manifest["pending_case_count"] = pending
            manifest["status"] = "complete" if pending == 0 else "running"
            _atomic_write(self.manifest_path, manifest)
        # The initial manifest is deliberately not rewritten before any case
        # runs, so a hard interruption leaves a truthful running/pending state.
        completed = sum(row.get("status") in {"complete", "failed"} for row in manifest["cases"])
        failures = sum(row.get("status") == "failed" for row in manifest["cases"])
        pending = len(manifest["cases"]) - completed
        manifest["completed_case_count"] = completed
        manifest["failure_count"] = failures
        manifest["pending_case_count"] = pending
        manifest["status"] = "complete" if pending == 0 else "partial"
        _atomic_write(self.manifest_path, manifest)
        return _read_json(self.manifest_path)


def run_evaluation(
    cases: Sequence[Mapping[str, Any]],
    analysis_callable: AnalysisCallable,
    output_dir: str | Path,
    *,
    identity: Mapping[str, Any],
    data_root: str | Path | None = None,
    max_cases: int | None = None,
) -> dict[str, Any]:
    """Functional convenience wrapper around :class:`EvaluationRunner`."""

    return EvaluationRunner(output_dir, analysis_callable, data_root=data_root).run(
        cases,
        identity=identity,
        max_cases=max_cases,
    )


def run_wp5_cases(
    cases: Sequence[Mapping[str, Any]],
    analysis_callable: AnalysisCallable,
    output_dir: str | Path,
    *,
    identity: Mapping[str, Any],
    data_root: str | Path | None = None,
    max_cases: int | None = None,
) -> dict[str, Any]:
    """Explicitly named alias for benchmark orchestration code."""

    return run_evaluation(
        cases,
        analysis_callable,
        output_dir,
        identity=identity,
        data_root=data_root,
        max_cases=max_cases,
    )


__all__ = [
    "AnalysisCallable",
    "EvaluationRunner",
    "RunnerIdentityError",
    "RunnerValidationError",
    "canonical_run_sha256",
    "run_evaluation",
    "run_wp5_cases",
]
