# Laboratory validation protocol

This protocol defines evidence that can be collected later without changing the
application's scientific contract. It does not turn the current research alpha
into a laboratory claim by itself.

## 1. Freeze the claim

Create one validation manifest for each instrument configuration. The scope must
name the instrument, geometry, radiation, coordinate, application version, and
reference snapshot. Start with one reflection Bragg–Brentano configuration and
one radiation (normally Cu Kα). Add another configuration only after it has its
own evidence.

The initial claim is qualitative phase screening. It does not include phase
fractions, chemistry, amorphous quantification, or universal certainty.

## 2. Collect controlled scans

Record the native vendor file and an immutable SHA-256 hash for every scan. For
each standard and known sample, record mounting, sample preparation, holder,
spinner, temperature, scan range, step size, counting time, optics, detector,
operator, date, firmware, and acquisition software.

The first pilot should include repeated standard scans, remounted standard scans,
and known single-phase, mixture, difficult-background, and negative-control
patterns. The laboratory should choose the number of repeats from the precision
it needs; a small repeatability pilot must not be presented as a final accuracy
study.

Use certified line-position material for calibration and retain the certificate
identifier and lot. Known mixtures must retain their preparation record and
independent ground truth. An unknown sample is not ground truth merely because a
human expects a phase to be present.

## 3. Lock evaluation data

Separate development scans from the locked test set. Parameters may be tuned on
development data only. The locked set must contain held-out mounts, days, or
samples so that repeated copies of one scan do not inflate performance.

Report, at minimum, peak-position bias and RMSE, repeatability,
reproducibility, top-k phase recall, false-support rate, unresolved rate, import
success, and provenance integrity. Report results by instrument configuration
and sample family. Keep negative controls visible in the report.

## 4. Review and status

The manifest status moves from `planned` to `pilot`, then `locked`, and finally
`validated`. `validated` requires an independent reviewer, hash-identified
artifacts, a completed uncertainty budget, and a written scope statement.
