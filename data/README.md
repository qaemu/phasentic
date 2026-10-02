# Data directory

Large or third-party data stays out of Git:

- `data/references/powcod/` - a local POW_COD copy, if you keep it inside the
  repository instead of `~/.phasentic/powcod` (see `phasentic setup-powcod`).
- `data/benchmarks/wp5/` - Precursor Genome bundles and run artifacts used to
  reproduce the validation (docs/validation.md).

The three-phase demo reference subset ships inside the package
(`src/phasentic/resources/demo-references.json`).
