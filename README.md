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
peaks, searches a reference database built from the
[Crystallography Open Database](https://www.crystallography.net/cod/) (or CNR's [POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/)),
and fits mixtures of up to five phases. It returns ranked
phase hypotheses with every setting, hash and warning recorded in a JSON
report. It runs locally, in the browser or from the command line.

<p align="center">
  <img src="docs/images/interface.png" alt="Phasentic interface: a tentative result of ZrO2 and LiOH·H2O with the fit plot and the competing hypotheses" width="900">
  <br>
  <sub>A development scan from the Precursor Genome dataset (PG_2452, Cu Kα), picked at random. Phasentic finds ZrO₂ and LiOH·H₂O; the human-refined label also contains Li₂CO₃, which this run misses. The leftover signal is visible under <i>Evidence per phase</i>.</sub>
</p>

## How accurate is it

The settings were tuned on 485 Precursor Genome scans (human-refined labels)
and then run on 200 locked scans that tuning never saw, with the
COD-derived database PXRD_COD 2026.11 (COD plus a Materials Project
supplement). Abstentions count as failures.

| Level | Correct | Rate |
|---|---|---|
| Right compounds and crystal structures (strict) | 85 / 200 | 42.5% |
| Right compounds, any polymorph (family) | 104 / 200 | 52.0% |

This is the second run on these 200 scans. The first (72 and 99) used the
COD-only database; the database supplement, restored hydrogen formulas and a
preference for the highest-symmetry description of a material were developed
on the 485 tuning scans only. The untuned method scored 71 and 96.
These numbers apply to the validated preset with PXRD_COD 2026.11, Cu Kα and
the sample's precursor chemistry; other settings are untested.

## Install

The install sets up Python 3.12, Phasentic and its reference database (an
8.6 GB download from Zenodo; keep about 10 GB free). No admin rights needed.

Windows: paste these four lines into PowerShell (the first one is the official
installer of [uv](https://docs.astral.sh/uv/), which installs Python):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/heads/main.zip
phasentic setup
```

macOS and Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/main/install.sh | sh
```

On Windows `phasentic setup` downloads the database, adds a **Phasentic**
shortcut to the Desktop and Start Menu and opens Phasentic in its own window;
close Phasentic before reinstalling. On macOS the installer adds Phasentic to
Applications, on Linux to the applications menu. If the download is
interrupted, run the same commands again; it resumes.

### Using POW_COD instead

If you have **POW_COD 2205 (FULL)** from the
[CNR download page](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/),
install it with the command below; Phasentic then uses it instead of the COD
database. The published accuracy figures were measured with the COD database,
not with POW_COD.

```bash
phasentic setup-powcod ~/Downloads/powcod-2205.zip
```

## Quick start

Open Phasentic from its shortcut, or run `phasentic-app`. To use it in a browser
instead, run the command below and open <http://127.0.0.1:8000>:

```bash
phasentic serve
```

Choose a scan, type the precursor and target formulas, keep *Validated method*
selected (the default) and press *Analyze*. *PDF* saves a plain report of the
measured and calculated values; *Formal report* opens a printable report (fit
plot, per-phase evidence, competing hypotheses, method and traceability);
*CIF* and *JSON* give the data.

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

- **For phase fractions.** Fit scales are screening amplitudes, not weight
  percentages.
- **For samples with three or more phases**, where it identified all the compounds
  only 11% of the time in testing.
- **For minor or weakly scattering phases** (for example Li, B or K salts next
  to heavy-element phases), which it often misses.

## How it works

1. Import the scan, estimate the background, detect peaks (noise-aware).
2. Retrieve candidates from the reference database, restricted to the sample's elements.
3. Fit non-negative mixtures of reference profiles with a bounded beam search,
   residual re-queries and phase swaps; reject phases whose strong lines are
   missing from the scan.
4. Rank hypotheses, report ambiguity, and record provenance (input hash,
   settings, database identity, algorithm versions).

Details: [docs/scientific-method.md](docs/scientific-method.md) and
[PARAMETERS.md](PARAMETERS.md).

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
