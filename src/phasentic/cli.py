from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from phasentic import __version__
from phasentic.acquisition.calibration import calibrate_standard_file
from phasentic.domain.models import AnalysisSettings, AngleUnit, analysis_mode_controls
from phasentic.presets import chemistry_elements, validated_preset
from phasentic.references.factory import POWCOD_CACHE_NAME, POWCOD_DATABASE_NAME, default_reference_source, phasentic_home
from phasentic.references.powcod import (
    PowCodReferenceStore,
    build_powcod_cache,
    verify_powcod_source,
    write_powcod_manifest,
)
from phasentic.references.equivalence import build_equivalence_sidecar
from phasentic.reporting.service import analyze_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phasentic", description="Powder X-ray diffraction phase identification")
    parser.add_argument("--version", action="version", version=f"phasentic {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze one .xy, .xrdml, or ASCII .raw file")
    analyze.add_argument("file", type=Path)
    analyze.add_argument("--radiation", default="Cu Ka")
    analyze.add_argument("--angle-unit", default="two_theta", choices=[unit.value for unit in AngleUnit])
    analyze.add_argument(
        "--preset",
        choices=["validated"],
        help="use the settings of the validated method (needs POW_COD and --chemistry); other tuning flags are ignored",
    )
    analyze.add_argument(
        "--chemistry",
        help='precursor and target formulas, e.g. "Ag2O BaCO3 Ba2Ag2C2O7"; restricts candidates to their elements plus H, C and O',
    )
    analyze.add_argument("--reference-source", choices=["demo", "pow_cod"], help="default: POW_COD when installed, else demo")
    analyze.add_argument("--powcod-db", type=Path, help="Trusted POW_COD SQLite database when --reference-source=pow_cod")
    analyze.add_argument("--powcod-cache", type=Path, help="Normalized POW_COD sidecar cache")
    analyze.add_argument("--powcod-equivalence", type=Path, help="Curated POW_COD equivalence sidecar")
    analyze.add_argument(
        "--analysis-mode",
        default="screening",
        choices=["screening", "joint_no_requery", "full_mixture", "mixture"],
        help="Analysis variant; mixture is a legacy alias for full_mixture",
    )
    analyze.add_argument("--max-phases", type=int, default=3)
    analyze.add_argument("--candidate-pool", type=int, default=100)
    analyze.add_argument(
        "--candidate-lookup-budget",
        type=int,
        help="maximum indexed references to rank before candidate-pool fitter truncation (defaults to --candidate-pool)",
    )
    analyze.add_argument(
        "--candidate-retrieval-mode",
        choices=["bounded_coarse", "exhaustive_exact"],
        default="bounded_coarse",
        help="POW_COD retrieval policy; exhaustive_exact scans the full cached phase universe",
    )
    analyze.add_argument("--retained-branches", type=int, default=3)
    analyze.add_argument("--min-independent-evidence", type=int, default=2)
    analyze.add_argument("--min-objective-improvement", type=float, default=0.02)
    analyze.add_argument("--complexity-penalty", type=float, default=0.02)
    analyze.add_argument("--ambiguity-margin", type=float, default=0.01)
    analyze.add_argument("--inactive-scale-relative-tolerance", type=float, default=1e-6)
    analyze.add_argument("--profile-width-deg", type=float, default=0.20)
    analyze.add_argument(
        "--d-spacing-scale-tolerance",
        type=float,
        default=0.0,
        help="optional bounded per-reference d-spacing adjustment for mixture screening (0 disables)",
    )
    analyze.add_argument("--max-fit-attempts", type=int, default=300)
    analyze.add_argument("--output", type=Path)

    calibrate = subparsers.add_parser("calibrate", help="Calibrate line positions from a standard scan")
    calibrate.add_argument("file", type=Path)
    calibrate.add_argument("--standard", default="silicon_srm_640g")
    calibrate.add_argument("--radiation", default="Cu Ka")
    calibrate.add_argument("--output", type=Path)

    serve = subparsers.add_parser("serve", help="Start the localhost web interface")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    setup = subparsers.add_parser("setup-powcod", help="Install POW_COD 2205 from the downloaded zip (one step)")
    setup.add_argument("source", type=Path, help="powcod-2205.zip as downloaded from CNR, or an extracted cod2205.sq")

    powcod = subparsers.add_parser("powcod", help="Prepare and verify a local CNR POW_COD release")
    powcod_subparsers = powcod.add_subparsers(dest="powcod_command", required=True)
    prepare = powcod_subparsers.add_parser("prepare", help="Build a deterministic read-only query cache")
    prepare.add_argument("database", type=Path)
    prepare.add_argument("--cache", type=Path, required=True)
    prepare.add_argument("--info", type=Path)
    prepare.add_argument("--release", default="2205")
    prepare.add_argument("--manifest", type=Path)
    powcod_verify = powcod_subparsers.add_parser("verify", help="Verify a POW_COD source and normalized cache")
    powcod_verify.add_argument("database", type=Path)
    powcod_verify.add_argument("--cache", type=Path, required=True)
    powcod_verify.add_argument("--info", type=Path)
    equivalence = powcod_subparsers.add_parser("equivalence-build", help="Build a curated POW_COD equivalence sidecar")
    equivalence.add_argument("database", type=Path)
    equivalence.add_argument("--cache", type=Path, required=True)
    equivalence.add_argument("--input", type=Path, required=True, help="JSON curation mapping")
    equivalence.add_argument("--output", type=Path, required=True)
    return parser


POWCOD_ZIP_SHA256 = "75b74f9544e8677edb2c6dc46196ee4331e27f21d943a70b08c68f18c010f9df"


def _emit(payload: dict, output: Path | None) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


def _setup_powcod(source: Path) -> int:
    """Extract POW_COD into ~/.phasentic/powcod and build the query cache."""

    import hashlib
    import shutil
    import zipfile

    source = source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Not found: {source}")
    target = phasentic_home() / "powcod"
    target.mkdir(parents=True, exist_ok=True)
    database = target / POWCOD_DATABASE_NAME
    info = target / (POWCOD_DATABASE_NAME + ".info")
    if source.suffix.lower() == ".zip":
        print("Checking the archive checksum...", flush=True)
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != POWCOD_ZIP_SHA256:
            raise SystemExit(
                "This is not the expected POW_COD 2205 (FULL) archive "
                f"(sha256 {digest.hexdigest()}, expected {POWCOD_ZIP_SHA256})."
            )
        print(f"Extracting to {target} (about 6 GB)...", flush=True)
        with zipfile.ZipFile(source) as archive:
            for name in (database.name, info.name):
                with archive.open(name) as src, (target / name).open("wb") as dst:
                    shutil.copyfileobj(src, dst, 16 * 1024 * 1024)
    else:
        if source != database:
            print(f"Copying {source.name} to {target}...", flush=True)
            shutil.copy2(source, database)
            sidecar = source.with_name(source.name + ".info")
            if sidecar.is_file():
                shutil.copy2(sidecar, info)
    print("Building the query cache (one time; this can take 20-60 minutes)...", flush=True)
    result = build_powcod_cache(
        database,
        target / POWCOD_CACHE_NAME,
        info_path=info if info.is_file() else None,
    )
    write_powcod_manifest(target / "powcod-2205.manifest.json", result)
    print(
        f"POW_COD {result.release} is ready: {result.phase_count} phases.\n"
        "Phasentic now uses it by default. Start the interface with: phasentic serve"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        reference_source = args.reference_source or default_reference_source()
        try:
            allowed = chemistry_elements(args.chemistry) if args.chemistry else None
        except ValueError as exc:
            raise SystemExit(f"--chemistry: {exc}") from exc
        if args.preset == "validated":
            if not allowed:
                raise SystemExit("--preset validated needs --chemistry (precursor and target formulas)")
            settings = AnalysisSettings(
                **validated_preset(),
                radiation=args.radiation,
                angle_unit=AngleUnit(args.angle_unit),
                reference_source=reference_source,
                allowed_elements=allowed,
            )
            payload = analyze_file(
                args.file,
                settings,
                powcod_path=args.powcod_db,
                powcod_cache_path=args.powcod_cache,
                powcod_equivalence_path=args.powcod_equivalence,
            ).to_dict()
            _emit(payload, args.output)
            return 0
        analysis_mode, residual_candidate_queries = analysis_mode_controls(args.analysis_mode)
        settings = AnalysisSettings(
            radiation=args.radiation,
            angle_unit=AngleUnit(args.angle_unit),
            reference_source=reference_source,
            allowed_elements=allowed,
            analysis_mode=analysis_mode,
            residual_candidate_queries=residual_candidate_queries,
            max_phases=args.max_phases,
            candidate_pool=args.candidate_pool,
            candidate_lookup_budget=args.candidate_lookup_budget,
            candidate_retrieval_mode=args.candidate_retrieval_mode,
            retained_branches=args.retained_branches,
            min_independent_evidence=args.min_independent_evidence,
            min_objective_improvement=args.min_objective_improvement,
            complexity_penalty=args.complexity_penalty,
            ambiguity_margin=args.ambiguity_margin,
            inactive_scale_relative_tolerance=args.inactive_scale_relative_tolerance,
            profile_width_deg=args.profile_width_deg,
            d_spacing_scale_tolerance=args.d_spacing_scale_tolerance,
            max_fit_attempts=args.max_fit_attempts,
        )
        payload = analyze_file(
            args.file,
            settings,
            powcod_path=args.powcod_db,
            powcod_cache_path=args.powcod_cache,
            powcod_equivalence_path=args.powcod_equivalence,
        ).to_dict()
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(serialized + "\n", encoding="utf-8")
        else:
            print(serialized)
        return 0
    if args.command == "calibrate":
        payload = calibrate_standard_file(args.file, args.standard, args.radiation).to_dict()
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(serialized + "\n", encoding="utf-8")
        else:
            print(serialized)
        return 0
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit("uvicorn is missing; reinstall Phasentic: pip install --force-reinstall phasentic") from exc
        os.environ["PHASENTIC_BIND_HOST"] = args.host  # the app accepts only this host name besides loopback
        uvicorn.run("phasentic.api.main:app", host=args.host, port=args.port, reload=False)
        return 0
    if args.command == "setup-powcod":
        return _setup_powcod(args.source)
    if args.command == "powcod":
        if args.powcod_command == "prepare":
            result = build_powcod_cache(
                args.database,
                args.cache,
                info_path=args.info,
                release=args.release,
            )
            if args.manifest is not None:
                write_powcod_manifest(args.manifest, result)
            print(json.dumps({
                "database": str(result.source_path),
                "cache": str(result.cache_path),
                "release": result.release,
                "schema_version": result.schema_version,
                "source_sha256": result.source_sha256,
                "cache_sha256": result.cache_sha256,
                "phase_count": result.phase_count,
                "line_count": result.line_count,
            }, indent=2, sort_keys=True))
            return 0
        if args.powcod_command == "verify":
            source_verification = verify_powcod_source(args.database, info_path=args.info)
            with PowCodReferenceStore(args.database, cache_path=args.cache, info_path=args.info) as store:
                print(json.dumps({
                    "status": "complete",
                    "source_verification": source_verification,
                    "provenance": store.provenance(),
                    "phase_count": store.metadata().get("phase_count"),
                    "line_count": store.metadata().get("line_count"),
                }, indent=2, sort_keys=True))
            return 0
        if args.powcod_command == "equivalence-build":
            with PowCodReferenceStore(args.database, cache_path=args.cache) as store:
                metadata = store.metadata()
            mapping = json.loads(args.input.read_text(encoding="utf-8"))
            result = build_equivalence_sidecar(
                args.output,
                source_sha256=str(metadata["source_sha256"]),
                cache_sha256=str(metadata["cache_sha256"]),
                groups=mapping.get("groups", []),
                members=mapping.get("members", []),
            )
            print(json.dumps({
                "status": "complete",
                "output": str(result.path),
                "content_sha256": result.content_sha256,
                "group_count": result.group_count,
                "member_count": result.member_count,
            }, indent=2, sort_keys=True))
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
