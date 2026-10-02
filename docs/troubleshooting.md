# Troubleshooting

- **`phasentic: command not found`** after `pipx install`: run `pipx ensurepath` and open a new terminal.
- **The interface says POW_COD is not configured**: run `phasentic setup-powcod path/to/powcod-2205.zip`, or set `PHASENTIC_POWCOD_PATH` and `PHASENTIC_POWCOD_CACHE_PATH`.
- **`setup-powcod` reports a checksum mismatch**: the download is incomplete or a different release; download POW_COD 2205 (FULL) again.
- **A binary `.raw` file is rejected**: export `.xy` or `.xrdml`, or set `GSASII_PATH` to a local GSAS-II installation.
- **No peaks are reported**: check the scan range, the background warning and the step size before changing thresholds.
- **Two candidates score almost the same**: treat the result as ambiguous and confirm with a full-pattern fit.
- **Calibration is `insufficient_data`**: at least three distinct standard lines must be detected; check the standard scan range. Recalibrate after changing the anode.
