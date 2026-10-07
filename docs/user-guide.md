# User guide

1. Start the server with `phasentic serve` and open <http://127.0.0.1:8000>.
2. Under *Sample*, choose the scan (`.xy`, `.xrdml` or two-column ASCII `.raw`) and type the precursor and target formulas. Candidates are limited to their elements plus H, C and O.
3. Under *Method*, keep *Validated method* selected to use the settings that were tested on held-out data (POW_COD and Cu Kα). Unticking it enables *Custom settings*, which are not validated. Without the formulas every POW_COD phase is a candidate: the result carries a `NO_SAMPLE_CHEMISTRY` warning and is never `supported`.
4. Optionally, open *Instrument and calibration* to record vendor and model and to calibrate line positions with a standard scan. A `supported` decision requires a passed calibration. The server signs each calibration it produces and only accepts its own, so calibrate again after restarting `phasentic serve`.
5. Press *Analyze*. The result shows the decision, the selected phases, the fit with its difference curve, the evidence for each phase, the competing hypotheses, the best single-phase candidates, and the quality checks. Full provenance is folded at the bottom.
6. Press *Download report* for a printable two-page report (HTML; open it and use Print → Save as PDF). It is clearly marked as an automated, unreviewed result, follows the ISO/IEC 17025 report structure, and leaves the laboratory, sample and signature fields blank for you to complete. *JSON* saves the full machine-readable record.
7. Treat `supported` as a screening boundary, not a final certificate. Confirm calibration with a certified standard and perform a full-pattern refinement for a scientific claim.

Use the CLI when a JSON report should be archived with a sample record.
