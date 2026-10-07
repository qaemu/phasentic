# Validation

This page states how accurate Phasentic is, how that was measured, and how to
check it.

## Result

The validated method (`--preset validated`, frozen as
[`validation/wp5-precursor-frozen-v6.json`](../validation/wp5-precursor-frozen-v6.json))
was run once on 200 sealed held-out scans:

| Level | Correct | Rate | Wilson 95% interval | Declared target |
|---|---|---|---|---|
| Right compounds and structures (strict) | 74 / 200 | 37.0% | 30.6–43.9% | ≥ 35% |
| Right compounds, any polymorph (family) | 99 / 200 | 49.5% | 42.6–56.4% | ≥ 45% |

| Phases in the label | Scans | Strict | Family |
|---|---|---|---|
| 1 | 8 | 2 | 3 |
| 2 | 125 | 67 | 87 |
| 3 | 43 | 4 | 8 |
| 4 or more | 24 | 1 | 1 |

Mean strict recall 0.68, precision 0.79. No runtime failures, no abstentions.
Receipt: [`validation/outcome-v2.json`](../validation/outcome-v2.json).

**How to read it.** The point estimates meet the targets that were declared
before tuning; the lower interval bounds do not, so the claim is about point
rates. The result describes Precursor Genome-like samples (solid-state
synthesis products, Cu Kα, laboratory diffractometers) analysed with their
precursor chemistry. It says nothing about other sample types, other anodes,
or other settings.

## Protocol

1. **Data.** [Precursor Genome](https://github.com/lauren-walters/precursor-genome)
   scans with accepted human Rietveld refinements and human quality score 1.
   Each label is the set of refined phases.
2. **Scoring.** Each reported phase is paired one-to-one with a labelled
   phase. *Strict* requires the same elements, compatible stoichiometry and
   the same space group (the right compound in the right crystal structure);
   *family* requires the same elements and stoichiometry, in any space group
   (the right compound, possibly another polymorph). H/D below 5 at.% is
   treated as trace. Rules: `src/phasentic/validation/wp5/phase_scoring.py`.
3. **Development set.** 100 scans (`validation/selection-dev-100-v3.json`),
   split 70/30 into tune and check by a label-blind hash
   (`phasentic.validation.wp5.staged_tuning.split_case_ids`, seed 20260930).
   All tuning used only these.
4. **Target.** Declared in writing before tuning:
   [`validation/wp5-precursor-target-v1.json`](../validation/wp5-precursor-target-v1.json).
5. **Freeze.** Settings and a SHA-256 of all analysis and runner code are
   frozen in one file. `scripts/run_wp5_parallel.py --frozen-config` refuses to
   run if the code differs, and only runs a sealed cohort with a frozen config.
6. **Sealed test, run once.** Cohorts are drawn from scans used by nothing
   else, with proportional phase-count strata
   (`scripts/prepare_precursor_campaign.py`).

## History

| Cohort | Method version | Strict | Family | Outcome |
|---|---|---|---|---|
| `heldout-200-v1` (seed 20260930) | frozen v1 | 64 / 200 (32%) | 84 / 200 (42%) | targets missed |
| `heldout-200-v2` (seed 20261001) | frozen v2 | 74 / 200 (37%) | 99 / 200 (49.5%) | targets met |

After the first held-out run missed both targets, the misses were analysed on
the development set only. Two fixes improved development results without
losing any case: reading POW_COD entries whose formulas were stored in unusual
notation (for example `\b-Ga2 O3` for β-Ga₂O₃, which had been invisible), and
preferring a charge-balanced entry among equivalent entries of the same
material. Because the method changed, it was tested on a new sealed cohort;
the first cohort was not reused. The two cohorts are different samples, so
part of the difference is sampling variation (the intervals overlap).

## Code changes after the test

Code changes invalidate the frozen hash. A change is accepted as
behaviour-preserving only if both the 100 development scans and the 200
held-out scans reproduce exactly: the same selected phases, objective values
(to 1e-10), full hypothesis ranking and scores. Receipts:

- [`validation/equivalence-v3.json`](../validation/equivalence-v3.json): removal of unused subsystems (frozen v2 → v3).
- [`validation/equivalence-v4.json`](../validation/equivalence-v4.json): rename to Phasentic, packaging and installer (frozen v3 → v4).
  The same receipt records that `phasentic analyze --preset validated` reproduces the runner's selection exactly on six held-out scans.
- [`validation/equivalence-v5.json`](../validation/equivalence-v5.json): SQLite connections closed before files are replaced, so the reference setup works on Windows (frozen v4 → v5).
- [`validation/equivalence-v6.json`](../validation/equivalence-v6.json): security and correctness review (frozen v5 → v6).
  All 100 development scans reproduce exactly. Of the 200 held-out scans, 198 reproduce exactly and 2 differ only in the
  order of two exactly tied alternative hypotheses (objectives equal to 1e-16). The replay ran on a different machine, and
  the unmodified v5 code there gives the same order, so the cause is floating point, not the change. Selections,
  decisions and scores are unchanged (74 strict, 99 family).

These replays are equivalence checks, not new evaluations.

## Known failure modes

From the analysis of 54 missed labels above 5 wt% on the first cohort:

- **Weakly scattering phases** (Li, B, K carbonates and hydroxides next to Pb,
  Ba or La phases) give peaks tens of times smaller per weight fraction and
  are often missed or rejected.
- **Three or more phases**: the search rarely recovers every minor phase.
- **Indistinguishable labels**: some label pairs cannot be separated by XRD
  (Fe₃O₄ / Fe₅O₈ spinels, solid solutions) and count as misses.
- **Reference gaps**: a few labelled phases are not in POW_COD.

## Reproducing

You need the Precursor Genome raw scans and POW_COD 2205.

```bash
git clone https://github.com/qaemu/phasentic && cd phasentic
pip install -e .
phasentic setup-powcod path/to/powcod-2205.zip

# Build a bundle from the Precursor Genome ledger and raw scans
python scripts/prepare_precursor_campaign.py --ledger LEDGER.json --raw-root RAW/ \
  --output data/benchmarks/wp5/my-cohort/intake --count 200 --seed 20261001 \
  --max-human-quality-score 1 --split test
python scripts/benchmark_wp5.py freeze --cases data/benchmarks/wp5/my-cohort/intake/case-manifest.json \
  --protocol data/benchmarks/wp5/my-cohort/intake/protocol.json \
  --sources data/benchmarks/wp5/my-cohort/intake/source-manifest.json \
  --output data/benchmarks/wp5/my-cohort/frozen
python scripts/precursor_sample_context.py --ledger LEDGER.json \
  --case-manifest data/benchmarks/wp5/my-cohort/frozen/case-manifest.json \
  --output data/benchmarks/wp5/my-cohort/sample-context.json

# Run with the frozen method
python scripts/run_wp5_parallel.py --bundle data/benchmarks/wp5/my-cohort/frozen \
  --split test --allow-sealed-test --output data/benchmarks/wp5/my-cohort/run \
  --sample-context data/benchmarks/wp5/my-cohort/sample-context.json \
  --powcod-path ~/.phasentic/powcod/cod2205.sq \
  --powcod-cache-path ~/.phasentic/powcod/powcod-2205.xrd.sqlite \
  --frozen-config validation/wp5-precursor-frozen-v6.json
```

The exact case lists of the published cohorts are in `validation/selection-*.json`
(case IDs, scan files, labels and SHA-256 of each raw scan), with their
label-free chemistry inputs in `validation/sample-context-*.json`.
