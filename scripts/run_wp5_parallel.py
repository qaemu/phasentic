#!/usr/bin/env python3
"""Run a WP5 bundle one case per worker process, then aggregate (step 4).

Each case runs through the normal ``run_bundle`` path in its own output
directory (``<output>/cases/<case_id>``) and is marked complete by a
``done.json`` receipt, so an interrupted invocation resumes where it stopped.
``--time-budget`` stops *submitting* new cases after that many seconds and
waits for the ones in flight, which keeps each invocation inside a bounded
command window. Once every selected case is done, ``aggregate.json`` holds the
rows, the WP5 metrics and a per-case timing table.

Hashing the multi-gigabyte POW_COD source and cache for the run identity is
done once per output directory: digests are stored in ``hash-cache.json``
keyed by each file's full stat identity (device, inode, size, mtime_ns,
ctime_ns) and seeded into every worker. Any change to a file changes its
identity and forces a fresh hash.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from scripts.benchmark_wp5 import WP5CommandError, _load_bundle, run_bundle  # noqa: E402
from phasentic.validation.wp5 import artifacts as wp5_artifacts  # noqa: E402
from phasentic.validation.wp5.metrics import compute_wp5_metrics  # noqa: E402

HASH_CACHE_SCHEMA = "wp5-parallel-hash-cache-v1"
FROZEN_CONFIG_SCHEMA = "wp5-frozen-config-1"


def code_sha256() -> str:
    """Hash of every analysis/runner source file, for frozen-config checks."""

    import hashlib

    files = sorted((ROOT / "src" / "phasentic").rglob("*.py")) + [
        ROOT / "scripts" / "benchmark_wp5.py",
        ROOT / "scripts" / "run_wp5_parallel.py",
    ]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_frozen_config(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if payload.get("schema") != FROZEN_CONFIG_SCHEMA:
        raise WP5CommandError(f"frozen_config_invalid: {path}")
    actual = code_sha256()
    if payload.get("code_sha256") != actual:
        raise WP5CommandError(
            f"frozen_config_code_mismatch: frozen {payload.get('code_sha256', '')[:12]}, current {actual[:12]}"
        )
    return payload
AGGREGATE_SCHEMA = "wp5-parallel-aggregate-v1"

_WORKER: dict[str, Any] = {}


def _identity_key(identity: Sequence[Any]) -> str:
    return json.dumps(list(identity))


def _load_hash_cache(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if payload.get("schema") != HASH_CACHE_SCHEMA or not isinstance(payload.get("digests"), dict):
        return {}
    return {str(key): str(value) for key, value in payload["digests"].items()}


def prepare_reference_hashes(paths: Sequence[Path], cache_file: Path) -> dict[str, str]:
    """Return {stat-identity-json: sha256} for ``paths``, hashing only on change."""

    cached = _load_hash_cache(cache_file)
    result: dict[str, str] = {}
    for path in paths:
        identity = wp5_artifacts._stat_identity(path)
        key = _identity_key(identity)
        digest = cached.get(key)
        if digest is None:
            digest = wp5_artifacts.sha256_file(path)
        result[key] = digest
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_file.with_suffix(".tmp")
    temporary.write_text(json.dumps({"schema": HASH_CACHE_SCHEMA, "digests": result}, indent=1))
    os.replace(temporary, cache_file)
    return result


def _seed_hash_memo(digests: Mapping[str, str]) -> None:
    for key, digest in digests.items():
        identity = tuple(json.loads(key))
        wp5_artifacts._SHA256_MEMO[identity] = digest  # type: ignore[index]


def _worker_init(config: Mapping[str, Any]) -> None:
    _WORKER.clear()
    _WORKER.update(config)
    _seed_hash_memo(config["digests"])


def _run_case(case_id: str) -> dict[str, Any]:
    config = _WORKER
    case_dir = Path(config["output"]) / "cases" / case_id
    started = time.time()
    cpu_started = time.process_time()
    try:
        result = run_bundle(
            Path(config["bundle"]),
            config["split"],
            config["variant"],
            case_dir,
            reference_source="pow_cod",
            powcod_path=Path(config["powcod_path"]),
            powcod_cache_path=Path(config["powcod_cache_path"]),
            settings_overrides=config["overrides"],
            case_ids=[case_id],
            sample_context=config["sample_context"],
        )
        row = result["cases"][0] if result.get("cases") else None
        error = None
    except Exception as exc:  # recorded, never silently dropped
        row = None
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}"
    receipt = {
        "case_id": case_id,
        "seconds": round(time.time() - started, 3),
        "cpu_seconds": round(time.process_time() - cpu_started, 3),
        "worker_pid": os.getpid(),
        "row": row,
        "error": error,
        "timings": _case_timings(case_dir),
    }
    if error is None:
        temporary = case_dir / "done.json.tmp"
        temporary.write_text(json.dumps(receipt, default=str))
        os.replace(temporary, case_dir / "done.json")
    return receipt


def _case_timings(case_dir: Path) -> dict[str, Any] | None:
    for artifact in sorted(case_dir.glob("**/*.json")):
        if artifact.name in {"done.json", "result.json", "run.json"}:
            continue
        try:
            payload = json.loads(artifact.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        report = payload.get("result") or payload.get("report") or payload
        provenance = report.get("provenance") if isinstance(report, dict) else None
        if isinstance(provenance, dict) and isinstance(provenance.get("timings"), dict):
            return provenance["timings"]
    return None


def select_case_ids(
    bundle: Path, split: str, requested: Sequence[str] | None, *, allow_sealed_test: bool = False
) -> list[str]:
    _manifest, _source, case_manifest, _protocol = _load_bundle(bundle)
    if not allow_sealed_test and any(
        case.split == "test" and (split in {"test", "all"}) for case in case_manifest.cases
    ):
        raise WP5CommandError(
            "sealed_test_split: this bundle holds the sealed held-out cohort; it runs once, with frozen "
            "parameters, via --allow-sealed-test (see validation/wp5-precursor-target-v2.json)"
        )
    eligible = [
        case.case_id
        for case in case_manifest.cases
        if case.eligibility == "eligible" and (split == "all" or case.split == split)
    ]
    if requested is None:
        return sorted(eligible)
    missing = sorted(set(requested).difference(eligible))
    if missing:
        raise WP5CommandError("case_selection_invalid: not eligible in split: " + ", ".join(missing))
    return list(dict.fromkeys(requested))


def aggregate(output: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    receipts = []
    for case_id in case_ids:
        done = output / "cases" / case_id / "done.json"
        if done.is_file():
            receipts.append(json.loads(done.read_text()))
    rows = [receipt["row"] for receipt in receipts if receipt.get("row") is not None]
    rows.sort(key=lambda row: row["case_id"])
    seconds = sorted(float(receipt["seconds"]) for receipt in receipts)
    timing = {
        "case_count": len(seconds),
        "total_case_seconds": round(sum(seconds), 1),
        "mean_case_seconds": round(sum(seconds) / len(seconds), 2) if seconds else None,
        "median_case_seconds": round(seconds[len(seconds) // 2], 2) if seconds else None,
        "max_case_seconds": round(seconds[-1], 2) if seconds else None,
        "per_case": {receipt["case_id"]: receipt["seconds"] for receipt in receipts},
    }
    payload = {
        "schema": AGGREGATE_SCHEMA,
        "complete": len(receipts) == len(case_ids),
        "selected_case_count": len(case_ids),
        "completed_case_count": len(receipts),
        "rows": rows,
        "metrics": compute_wp5_metrics(rows) if rows else None,
        "timing": timing,
    }
    temporary = output / "aggregate.json.tmp"
    temporary.write_text(json.dumps(payload, indent=1, default=str))
    os.replace(temporary, output / "aggregate.json")
    return payload


def run_parallel(
    *,
    bundle: Path,
    split: str,
    variant: str,
    output: Path,
    powcod_path: Path,
    powcod_cache_path: Path,
    workers: int,
    time_budget: float | None,
    case_ids: Sequence[str] | None,
    overrides: Mapping[str, Any],
    sample_context: Mapping[str, Any] | None,
    allow_sealed_test: bool = False,
) -> dict[str, Any]:
    started = time.time()
    output = output.expanduser().resolve()
    selected = select_case_ids(bundle, split, case_ids, allow_sealed_test=allow_sealed_test)
    output.mkdir(parents=True, exist_ok=True)
    pending = [case_id for case_id in selected if not (output / "cases" / case_id / "done.json").is_file()]
    digests = prepare_reference_hashes((powcod_path, powcod_cache_path), output / "hash-cache.json")
    config = {
        "bundle": str(bundle),
        "split": split,
        "variant": variant,
        "output": str(output),
        "powcod_path": str(powcod_path),
        "powcod_cache_path": str(powcod_cache_path),
        "overrides": dict(overrides),
        "sample_context": sample_context,
        "digests": digests,
    }
    failures: list[dict[str, Any]] = []
    finished: list[dict[str, Any]] = []
    if pending:
        with ProcessPoolExecutor(max_workers=max(1, workers), initializer=_worker_init, initargs=(config,)) as pool:
            queue = list(pending)
            in_flight = {}
            while queue or in_flight:
                while queue and len(in_flight) < max(1, workers) and (
                    time_budget is None or time.time() - started < time_budget
                ):
                    case_id = queue.pop(0)
                    in_flight[pool.submit(_run_case, case_id)] = case_id
                if not in_flight:
                    break
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    in_flight.pop(future)
                    receipt = future.result()
                    (failures if receipt["error"] else finished).append(receipt)
                    print(
                        f"{receipt['case_id']} {receipt['seconds']:.1f}s"
                        + (" FAILED" if receipt["error"] else ""),
                        flush=True,
                    )
    summary = aggregate(output, selected)
    remaining = sum(not (output / "cases" / case_id / "done.json").is_file() for case_id in selected)
    return {
        "selected": len(selected),
        "completed_this_invocation": len(finished),
        "failures_this_invocation": [{"case_id": item["case_id"], "error": item["error"]} for item in failures],
        "remaining": remaining,
        "wall_seconds": round(time.time() - started, 1),
        "aggregate_complete": summary["complete"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--split", default="development")
    parser.add_argument("--variant", default="full_mixture")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--powcod-path", type=Path, default=ROOT / "data/references/powcod/raw/cod2205.sq")
    parser.add_argument("--powcod-cache-path", type=Path, default=ROOT / "data/references/powcod/powcod-2205.xrd.sqlite")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--time-budget", type=float, default=None, help="stop submitting new cases after N seconds")
    parser.add_argument("--case-ids", default=None, help="comma-separated case ids")
    parser.add_argument("--selection", type=Path, default=None, help="JSON file with a case_ids list")
    parser.add_argument("--overrides", default="{}", help="JSON object of settings overrides")
    parser.add_argument("--sample-context", type=Path, default=None)
    parser.add_argument("--allow-sealed-test", action="store_true", help="run the sealed held-out split (once, frozen parameters)")
    parser.add_argument("--frozen-config", type=Path, default=None, help="frozen settings; code must match its hash")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    case_ids: list[str] | None = None
    if args.case_ids:
        case_ids = [value.strip() for value in args.case_ids.split(",") if value.strip()]
    elif args.selection is not None:
        case_ids = list(json.loads(args.selection.read_text())["case_ids"])
    sample_context = json.loads(args.sample_context.read_text()) if args.sample_context else None
    overrides = json.loads(args.overrides)
    try:
        if args.frozen_config is not None:
            frozen = load_frozen_config(args.frozen_config)
            if overrides:
                raise WP5CommandError("frozen_config_conflict: --overrides cannot be combined with --frozen-config")
            overrides = dict(frozen["overrides"])
        elif args.allow_sealed_test:
            raise WP5CommandError("sealed_test_requires_frozen_config: pass --frozen-config")
        summary = run_parallel(
            bundle=args.bundle,
            split=args.split,
            variant=args.variant,
            output=args.output,
            powcod_path=args.powcod_path,
            powcod_cache_path=args.powcod_cache_path,
            workers=args.workers,
            time_budget=args.time_budget,
            case_ids=case_ids,
            overrides=overrides,
            sample_context=sample_context,
            allow_sealed_test=args.allow_sealed_test,
        )
    except WP5CommandError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 2
    print(json.dumps(summary, indent=1))
    return 0 if not summary["failures_this_invocation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
