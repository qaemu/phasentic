# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## [1.0.0] - 2026-11-09

### Changed
- New interface: neutral greys with one blue accent, IBM Plex type bundled for
  offline use, a drop target for scans, flat sections instead of cards, and an
  English file picker that follows the language menu.
- The validated method is used automatically when formulas are given with Cu Kα
  (no checkbox); peak tolerance and maximum phases stay editable.
- Reports include the typed formulas, instrument vendor, model and goniometer
  radius, the laboratory and the report folder.
- Windows install: uv's installer, `uv tool install`, then `phasentic setup`
  (install.ps1 removed after Defender flagged its command line).

### Removed
- The demo reference subset; the installed reference database is the only source.
- Line-position calibration in the interface; results are therefore at most
  `tentative` (`phasentic calibrate` still checks a standard scan).
- Reference database PXRD_COD 2026.11 (new Zenodo version): 23,611 Materials
  Project structures of experimentally known phases missing from COD, and
  hydrogen restored in 9,437 COD formulas. Published on Zenodo,
  doi:10.5281/zenodo.24059658; the installer downloads and verifies it.
- Among near-equal fits of the same material, the highest-symmetry space
  group wins (Fd-3m over F-43m for Co3O4).
- Locked test (200 scans): 42.5% exact, 52.0% family (was 36.0% / 49.5%).

### Removed
- Validation and testing tooling: `scripts/`, the `phasentic.validation`
  package, `benchmarks/`, the WP-5 and crosswalk schemas, and the `evaluation`
  extra. It remains available at commit `14fc94f`.

### Changed
- The reference 2θ window is now 0–90° (was 0–120°), set once in
  `domain/radiation.py`; the validated preset matches up to 90° (was 100°).
  The published validation figures were measured at 100° and must be re-run.

### Security
- A calibration result is accepted only if this server issued it (HMAC
  signature). A hand-made `passed` result could previously unlock a
  `supported` decision.
- Requests with a foreign `Host` (DNS rebinding) or a foreign browser
  `Origin` (cross-site requests) are refused.
- Each web analysis and calibration runs in its own worker process, one at a
  time: it is stopped when the client disconnects, after
  `PHASENTIC_ANALYSIS_TIMEOUT_SECONDS` (default 300), or when the server dies.
  A single request with maximum search settings could previously run for
  20+ minutes, use 5 GB of memory and outlive its client.

### Changed
- Searching POW_COD without the sample chemistry adds a `NO_SAMPLE_CHEMISTRY`
  warning and can no longer produce a `supported` decision (service
  algorithm `research-alpha-0.10-…-chemistry-gate`). The validated method
  always has chemistry and is unaffected (`validation/equivalence-v6.json`).
- The printable report no longer lists candidates that matched no peak.
- `silicon-cu-ka.raw` and `.xrdml` now hold the same scan as the `.xy`
  example (they were 8- and 5-point stubs).

### Fixed
- A calibration with fewer than three standard lines reported a line count
  its own validation rejected, so the next analysis failed.
- Numbers written with digit separators (`1_0`) were read as `10`.

### Removed
- `/api/docs` and `/redoc`: they loaded scripts from a CDN that the page's
  content security policy blocks, so they never worked.

## [0.1.0] - 2026-10-01

First public release. The project was developed privately as "XRD Workbench".

### Added
- `phasentic setup-powcod`: installs POW_COD 2205 from the downloaded zip in one step.
- Validated preset (`--preset validated` / *Validated method*, on by default in
  the interface) and sample chemistry input (`--chemistry`).
- Validation receipts and cohort case lists in `validation/`.
- Printable analysis report (*Download report*): two A4 pages with fit,
  per-phase evidence and competing-hypothesis figures, structured after
  ISO/IEC 17025 §7.8.
- Redesigned local interface: light, report-matched layout with the sample and
  method on the left; fit, per-phase evidence, hypotheses and quality checks on
  the right; English and Spanish.

### Validated
- Frozen method tested once on 200 sealed held-out Precursor Genome scans:
  37.0% exact, 49.5% family (docs/validation.md).

### Removed (before release)
- GSAS-II whole-pattern diagnostic, COD index source, sample-context
  assistant, in-app code-review pipeline, DARA comparison and WP-4 tooling.
