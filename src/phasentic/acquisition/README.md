# Acquisition adapters

Instrument metadata and line-position calibration live here. The deterministic calibration fits zero shift and wavelength scale against the certified NIST SRM 640g manifest in `configs/calibration-standards.json`; it preserves residuals, manifest hash, standard-scan hash, source reference, and status in the report.

GSAS-II remains an optional adapter boundary for vendor RAW normalization and later whole-pattern diagnostics. The mapping registry is in `gsas2.py` and is backed by the real fixture manifest in `tests/fixtures/vendor/manifest.json`. Every adapter must normalize into the domain `Pattern` contract and preserve source metadata.
