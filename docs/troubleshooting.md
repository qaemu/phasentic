# Troubleshooting

- **`phasentic: command not found`** after installing: open a new terminal (the installer adds Phasentic to your PATH for new terminals).
- **The interface says no reference database is configured**: run the install command again; it downloads and installs the database (or finishes an interrupted download).
- **`setup-powcod` reports a checksum mismatch**: the download is incomplete or a different release; download POW_COD 2205 (FULL) again.
- **A binary `.raw` file is rejected**: export `.xy` or `.xrdml`, or set `GSASII_PATH` to a local GSAS-II installation.
- **No peaks are reported**: check the scan range, the background warning and the step size before changing thresholds.
- **Two candidates score almost the same**: treat the result as ambiguous and confirm with a full-pattern fit.
- **Calibration is `insufficient_data`**: at least three distinct standard lines must be detected; check the standard scan range. Recalibrate after changing the anode.
