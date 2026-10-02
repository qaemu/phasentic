# User guide

1. Start the server and open the local URL.
2. Select the anode material used for the scan.
3. Keep the coordinate at calibrated 2θ for the alpha.
4. Optionally enter vendor/model metadata and upload a line-position standard. Run calibration and inspect its line count, residual, and status.
5. Upload an `.xy`, `.xrdml`, or two-column ASCII `.raw` file.
6. Under *Sample chemistry*, type the precursor and target formulas, and tick *Use the validated method* to analyse with the settings that were tested on held-out data (POW_COD and Cu Kα).
7. Inspect the detected peaks, candidate line evidence, calibration status, quality warnings, and reference source.
8. Press *Download report* for a printable two-page report (HTML; open it and use Print → Save as PDF). It is clearly marked as an automated, unreviewed result, follows the ISO/IEC 17025 report structure, and leaves the laboratory, sample and signature fields blank for you to complete. *Download JSON report* saves the full machine-readable record.
9. Treat `supported` as a screening boundary, not a final certificate. Confirm calibration with a certified standard and perform a full-pattern refinement for a scientific claim.

Use the CLI when a JSON report should be archived with a sample record.
