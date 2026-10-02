# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

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
