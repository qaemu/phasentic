# User guide

1. Open Phasentic from its shortcut (or run `phasentic-app`). To use a browser instead, run `phasentic serve` and open <http://127.0.0.1:8000>.
2. Drop one or more scans on the window, or press *Choose files* (`.xy`, `.xrdml` or two-column ASCII `.raw`, up to 10 MB each). Several files run as a batch.
3. Type the precursor and target formulas. Candidates are limited to their elements plus H, C and O. With formulas and Cu Kα, the validated method (the settings tested on held-out scans) is used. Without formulas every phase in the database is a candidate: the result carries a `NO_SAMPLE_CHEMISTRY` warning and is never `supported`.
4. Optionally, open *Search settings* to change the peak tolerance or the maximum number of phases (other values than 0.10° and 5 are not validated), and *Instrument* to record the vendor, model and goniometer radius; they appear in the reports.
5. Under *Reports*, *Laboratory and folder* sets the laboratory name and address printed on the reports and a folder where every analysis is saved (PDF report, powder CIF, JSON data and a copy of the scan). *Export analysis' PDF* downloads a PDF after each analysis, or one ZIP for a batch.
6. Press *Analyze*. The result shows the selected phases and the decision, the fit with its difference curve, the competing hypotheses, the alternatives for each phase, the evidence for each phase, the best single-phase candidates and the quality checks. Drag over the graph to zoom; double-click to reset. *Use this* on an alternative fixes that entry and searches the remaining phases again.
7. Export with *PDF* (plain report of the values), *Formal report* (printable report following the ISO/IEC 17025 structure, marked as an automated, unreviewed result), *CIF* or *JSON* (the full machine-readable record). *Recent analyses* reopens earlier results.
8. Results are at most `tentative`: a `supported` decision would need an attached line-position calibration, which this release does not offer. `phasentic calibrate standard.xy` still checks the instrument's line positions against a standard scan. Confirm any result by a full-pattern refinement before a scientific claim.

Use the CLI (`phasentic analyze`) when a JSON report should be archived with a sample record.
