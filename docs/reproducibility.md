# Reproducibility checklist

Save the input file, report JSON, exact application version, Python lock file,
instrument/anode metadata, scan geometry, calibration standard result. For POW_COD-backed analysis
retain the source database and companion `.sq.info` file, the normalized cache,
manifest, source/cache SHA-256 values, POW_COD release, adapter/schema version,
cache index kind, d-spacing bin width/overflow limit, and reflection-encoding version,
exact COD entry IDs and source URLs, radiation policy, and candidate-query
settings. Retain the retrieval mode (`bounded_coarse` for interactive screening
or the opt-in `exhaustive_exact` evaluation path), candidate count, returned
count, scanned phase count, selection policy and explicit truncation flag. A
bounded pool must never be mistaken for exhaustive full-library recall; the
exhaustive path proves that the cached phase universe was scanned but still
records downstream pool truncation when the result budget is smaller than the
exact match set. A report
without these artifacts is a screening note, not a reproducible scientific
result.

The POW_COD cache status must be `complete`, and its source size/mtime and
SHA-256 binding must still match the downloaded database. Run
`phasentic powcod verify` after acquisition or before publishing a cache;
that command performs the full SQLite integrity scan of the `.sq` and
companion `.sq.info` files and reports their row counts and hashes. Unknown,
changed, or incomplete source/cache artifacts are rejected by the read-only
runtime store.
The physical laboratory validation set and instrument uncertainty budget are
separate deferred milestones.

For phase screening, preserve both the candidate score profile and the fitter
shortlist policy. The shortlist record includes its algorithm version, global
rank quota, number of peak-diversity slots actually filled, selected reference
IDs, and which strong observed peaks nominated those IDs. This is necessary
because retrieval may be broad while only a bounded subset reaches mixture
fitting; the lookup budget and fitter budget are distinct controls.

## WP-5 evaluation package

WP-5 uses five hash-authenticated local artifacts: a source inventory, case
inventory, frozen protocol, frozen bundle, and per-variant run directories.
`scripts/benchmark_wp5.py import` verifies every eligible source byte against
its manifest and preserves excluded, pending-rights, missing-metadata, and
unavailable records. `freeze` copies authenticated bytes below one bundle root
and records the manifest and split-policy hashes. A bundle cannot be served to
the runner if an artifact is missing, changed, a symlink, or outside the root.

`run` calls the same deterministic `analyze_file` service used by the
application. Each case is written atomically and carries the input hash and a
run identity containing settings, reference index, protocol, algorithm, and
environment hashes. Interrupted runs retain pending rows; failures are
persisted and remain visible to the independent metric evaluator. Resume is
allowed only when every identity field and input hash matches.

The result rows preserve expected/uncertain phase groups, label completeness,
candidate ordering, selected/tentative/supported sets, decision, errors,
instrument/radiation/calibration strata, and library-completeness status.
`compute_wp5_metrics` recomputes top-k recall, equivalence-group-aware
selection and exact-set metrics, false-support and negative-control rates,
abstention/failure/missing-library counts, and fixed-seed cluster bootstrap
intervals from those rows. A zero denominator is serialized as `null` with a
reason and is never replaced with a zero.

For the active Precursor campaign, the primary matching window is the
versioned 0–100° calibrated 2θ policy. Reports retain a full-scan audit trace
and record the configured window. Phase agreement is evaluated on the five
highest-weight reference groups with an 80% recall-and-precision gate; the
candidate search pool is not reduced to five. This policy is part of the run
identity and must be changed by versioned configuration before a result can be
compared with an earlier campaign.

Validated runs use `scripts/run_wp5_parallel.py`, which runs one case per
worker and, with `--frozen-config`, refuses to run when the analysis code
differs from the frozen hash. Retain the frozen configuration file and the
run directory with its per-case results.

## POW_COD equivalence provenance

When a curated POW_COD equivalence sidecar is enabled, reports retain the
POW_COD source and cache hashes together with the sidecar content hash and
method version. Exact equivalence-group matches are used for duplicate
collapse and mixture uniqueness. Parent-family relationships remain separate
partial evidence and cannot upgrade a strict phase match. Rebuilding the
sidecar from the same sorted curation mappings must produce the same content
hash; stale source or cache hashes fail closed.

The Precursor continuation adds a second, source-label crosswalk boundary.
The curated crosswalk (schema
`configs/schemas/precursor-crosswalk.schema.json`) is hash-bound to the public-100
source manifest and the POW_COD cache content identity. It records every
distinct ICSD/space-group label, candidate reference IDs, review status, and
the evidence note. Only `reviewed_exact` entries can populate strict
`expected_phase_groups`; family-only, ambiguous, and unresolved entries stay
in metadata and keep the case label incomplete. The derived receipt records a
deterministic 35-case training/15-case holdout split and its split hash. Native
parameter manifests repeat the protocol, crosswalk, split, and training truth
hashes; they cannot be frozen with zero reviewed training cases.
