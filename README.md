<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/wordmark-dark.svg">
    <img src="assets/wordmark-light.svg" alt="phasentic" width="360">
  </picture>
</p>

<p align="center">
  Powder X-ray diffraction phase identification with a validated, reproducible method.
</p>

<p align="center">
  <b>English</b> | <a href="README/README_es.md">Español</a> | <a href="README/README_fr.md">Français</a> | <a href="README/README_cn.md">简体中文</a> | <a href="README/README_ar.md">العربية</a> | <a href="README/README_de.md">Deutsch</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%E2%80%933.13-3776ab" alt="Python 3.10–3.13">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#how-accurate-is-it">Validation</a> ·
  <a href="docs/">Docs</a> ·
  <a href="#how-this-was-built">How this was built</a>
</p>

Phasentic reads a powder XRD scan (`.xy`, `.xrdml` or ASCII `.raw`), detects
peaks, searches the CNR [POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/)
reference database, and fits mixtures of up to five phases. It returns ranked
phase hypotheses with every setting, hash and warning recorded in a JSON
report. It runs locally, in the browser or from the command line.

<p align="center">
  <img src="docs/images/interface.png" alt="Phasentic interface: a tentative result of ZrO2 and LiOH·H2O with the fit plot and the competing hypotheses" width="900">
  <br>
  <sub>A development scan from the Precursor Genome dataset (PG_2452, Cu Kα), picked at random. Phasentic finds ZrO₂ and LiOH·H₂O; the human-refined label also contains Li₂CO₃, which this run misses. The leftover signal is visible under <i>Evidence per phase</i>.</sub>
</p>

## How accurate is it

The method was frozen before testing, together with a declared target, and
run once on 200 scans it had never seen (Precursor Genome, human-refined
labels). Abstentions count as failures.

| Level | Correct | Rate | 95% interval (Wilson) | Declared target |
|---|---|---|---|---|
| Right compounds and crystal structures (strict) | 74 / 200 | 37.0% | 30.6–43.9% | ≥ 35% |
| Right compounds, any polymorph (family) | 99 / 200 | 49.5% | 42.6–56.4% | ≥ 45% |

Both point estimates meet their targets; both lower bounds fall below them.
Accuracy depends strongly on the number of phases:

| Phases in the sample | Scans | Correct at family level |
|---|---|---|
| 1 | 8 | 3 |
| 2 | 125 | 87 (70%) |
| 3 or more | 67 | 9 (13%) |

The protocol, the earlier held-out run (32% / 42% for the previous version),
the failure analysis and the receipts are in [docs/validation.md](docs/validation.md).
These numbers apply to the validated preset with POW_COD, Cu Kα and the
sample's precursor chemistry; other settings are untested.

## Install

You need Python 3.10–3.13. The simplest way installs the `phasentic` command
in its own environment:

```bash
pipx install git+https://github.com/qaemu/phasentic
```

or, with [uv](https://docs.astral.sh/uv/): `uv tool install git+https://github.com/qaemu/phasentic`,
or with plain pip: `pip install git+https://github.com/qaemu/phasentic`.

Check it worked:

```bash
phasentic --version
```

### Add the POW_COD reference database (once)

Without POW_COD, Phasentic runs on a three-phase demo subset that is only good
for trying the interface. For real work:

1. Download **POW_COD 2205 (FULL)** (about 1.9 GB) from the
   [CNR download page](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/).
2. Run:

   ```bash
   phasentic setup-powcod ~/Downloads/powcod-2205.zip
   ```

This checks the archive, extracts it to `~/.phasentic/powcod` (about 6 GB),
and builds a query cache once (20–60 minutes). After that, Phasentic uses
POW_COD by default.

## Quick start

Start the local interface and open <http://127.0.0.1:8000>:

```bash
phasentic serve
```

Choose a scan, type the precursor and target formulas, keep *Validated method*
selected (the default) and press *Analyze*. *Download report* gives a printable
two-page report (fit plot, per-phase evidence, competing hypotheses, method and
traceability) that you can save as PDF; *JSON* gives the full machine-readable
record.

From the command line, the same validated method:

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

`--chemistry` restricts candidates to the elements of those formulas plus H, C
and O (carbonates, hydroxides, hydrates). Without `--preset`, every analysis
setting can be tuned by flags (`phasentic analyze --help`); those
combinations are not validated.

A `supported` decision additionally requires a line-position calibration with
a standard scan (NIST SRM 640g silicon by default): `phasentic calibrate standard.xy`.

## When not to use it

- **To prove a phase is present.** Results are ranked hypotheses for a
  scientist to confirm, ideally by Rietveld refinement.
- **For phase fractions.** Fit scales are screening amplitudes, not weight
  percentages.
- **For samples with three or more phases**, where it identified all the compounds
  only 13% of the time in testing.
- **For minor or weakly scattering phases** (for example Li, B or K salts next
  to heavy-element phases), which it often misses.
- **Without the sample chemistry or with anodes other than Cu**, which were
  not part of the validation.

## How it works

1. Import the scan, estimate the background, detect peaks (noise-aware).
2. Retrieve candidates from POW_COD, restricted to the sample's elements.
3. Fit non-negative mixtures of reference profiles with a bounded beam search,
   residual re-queries and phase swaps; reject phases whose strong lines are
   missing from the scan.
4. Rank hypotheses, report ambiguity, and record provenance (input hash,
   settings, database identity, algorithm versions).

Details: [docs/scientific-method.md](docs/scientific-method.md) and
[PARAMETERS.md](PARAMETERS.md).

## Reproducing the validation

Clone the repository and install it:

```bash
git clone https://github.com/qaemu/phasentic && cd phasentic
pip install -e .
```

The validated runs use `scripts/run_wp5_parallel.py`, which refuses to run if
the analysis code differs from the hash in the frozen configuration
(`validation/wp5-precursor-frozen-v6.json`). The cohorts' case lists and the
outcome receipts are in [`validation/`](validation/); the scans themselves come
from the [Precursor Genome](https://github.com/lauren-walters/precursor-genome)
dataset (CC BY 4.0). Step-by-step instructions are in
[docs/validation.md](docs/validation.md).

## How this was built

Phasentic was written almost entirely by **Claude Code**, Anthropic's coding
agent, working under my direction. I am a single developer. I chose the
problem, the methods and the validation protocol, reviewed the results, and
I am responsible for every claim in this repository.

The parts that make the claims checkable were set before results were seen:
the accuracy target was declared before tuning, tuning used only 100
development scans, the held-out set was sealed and run once, settings and code
were hash-frozen, and later refactors had to reproduce all 300 results exactly
([docs/validation.md](docs/validation.md)). Commits made with AI assistance
carry an `Assisted-by: Claude Code` trailer. See [AI_USE.md](AI_USE.md).

## Citing

If Phasentic contributes to your work, cite the release you used. GitHub's
*Cite this repository* button (from [CITATION.cff](CITATION.cff)) gives APA
and BibTeX. Also cite POW_COD and the Crystallography Open Database.

## License

MIT for the code. POW_COD, COD and Precursor Genome data are distributed under
their own terms and are not included in this repository.
