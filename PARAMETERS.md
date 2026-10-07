# Research-alpha parameters

This file is a living, testable contract. Values below are starting boundaries, not validated universal truths. Each change should cite a fixture, a metric, and a reason in the validation log.

## Socratic calibration questions

1. What would make a scientist reject a result immediately? A wrong wavelength, an unreported angle coordinate, or a peak outside the measured range. Therefore the alpha validates radiation, requires calibrated 2θ, and records both in every report.
2. What evidence should make a phase a good *major-phase seed*? Balance support from the strongest measured peaks against whether a reference explains its own strongest predicted reflections. The provisional Cu Kα profile v0.8 uses 25% peak-position agreement, 35% measured-intensity-weighted coverage of the ten strongest observed peaks, 10% relative-intensity agreement among matched top-ten peaks, and 30% intensity-weighted coverage of the ten strongest predicted reflections. This reduces the dense-coincidence advantage seen in PG_1018 while keeping relative-intensity agreement secondary because mixtures and specimen effects can alter it. The observed-peak term weights each detected peak by its corrected height; it is not a comparison to calculated CIF intensities. If fewer than ten peaks are present, use all available peaks. All visible reference lines still contribute to ordinary coverage. Require `matched_peaks >= 2` for a non-unresolved match. These weights rank candidates; they are not probabilities, phase fractions, or calibrated certainty. The weights are exploratory and have not been calibrated across the cohort.
3. How much preprocessing can be applied without hiding evidence? Start with a rolling 20th-percentile background estimate and no smoothing of the raw series. Record the baseline fraction and keep raw arrays available to the caller.
4. What does “certainty” mean here? A score is a reproducible ranking metric, not a calibrated probability. Until a labeled benchmark and calibration curve exist, use `supported`, `tentative`, `ambiguous`, and `unresolved`.
5. When is accuracy credible? Only after an instrument-specific benchmark includes mixtures, preferred orientation, amorphous backgrounds, line broadening, and negative controls. Report recall, precision, top-k recall, false-support rate, and unresolved rate by sample family.

## Initial values

| Parameter | Alpha value | Rationale | Change trigger |
|---|---:|---|---|
| upload limit | 10 MiB | protects localhost service from accidental huge files | real instrument export distribution |
| peak tolerance | 0.20° 2θ | conservative first pass for unrefined lab scans | certified standard + instrument profile |
| prominence threshold | 2.5% of corrected maximum | avoids noise-only candidates while retaining weaker lines | benchmark ROC and visual review |
| background window | 31 points, rolling 20th percentile | inspectable, no smoothing of raw data | scan step size and background class |
| supported decision | score ≥ 0.75, ≥2 matches, no low-S/N warning, sample chemistry given when POW_COD is searched | provisional evidence boundary; without chemistry every POW_COD phase competes and dense line lists fit almost anything | labeled reference benchmark |
| tentative decision | score ≥ 0.50 | candidate requires scientist review | benchmark calibration |
| ambiguity | top-two scores within 0.05 | report competing hypotheses | multi-phase benchmark |
| max report peaks | 40 | stable UI and matching cost | high-resolution scans |
| calibration minimum lines | 3 unique standard lines | identifies an underdetermined correction | certified standard fixture study |
| calibration RMSE gate | ≤ 0.05° 2θ | provisional line-position repeatability boundary | instrument precision benchmark |
| calibration max residual | ≤ 0.10° 2θ | prevents one bad line from hiding in a mean | outlier and overlap study |
| calibration wavelength deviation | ≤ 0.5% | catches anode or wavelength metadata errors | certified wavelength benchmark |
| supported calibration gate | status `passed` required | prevents unverified coordinates from receiving the strongest label | held-out false-support study |
| candidate ranking profile | v0.8 exploratory: Cu 25/35/10/30 for position / measured-intensity-weighted top-ten coverage / relative intensity / strongest-reference coverage; non-Cu 60/30/10 position / unweighted top-ten hit fraction / unweighted reference coverage | balances major measured-peak support against evidence that a candidate explains its own strongest predicted lines; non-Cu remains position-only | declared training split, frozen configuration, then held-out evaluation |
| fitter shortlist retention | v0.1: keep 70% of fitter slots by global rank; use up to 30% for round-robin candidates matching distinct strongest measured peaks; return to global rank when support is absent | prevents a scalar aggregate rank from excluding every candidate supporting a major measured peak while leaving the fitter cap unchanged | shortlist recall and runtime on the declared training split, then frozen held-out evaluation |

## Mixture-screening starting bounds

The following values are development controls, not accuracy claims:

| Parameter | Starting value | Socratic revision question |
|---|---:|---|
| maximum phases | 3 (user cap 5) | Does each extra phase explain independent reproducible evidence? |
| candidate fitter pool | up to 100 ranked reference entries before duplicate/equivalence collapse | Could a weak true phase be excluded before residual search, and how many distinct fitter groups remain after collapse? |
| candidate lookup budget | follows the fitter pool by default; PG_1018 development diagnostic uses 20,000 lookup / 100 fitters | How much broader retrieval is worth the extra ranking time before expensive profile fitting? Measure candidate recall and runtime on the frozen development split. |
| candidate retrieval mode | `bounded_coarse` for interactive use; `exhaustive_exact` for qualification | Does the full cached phase universe need to be scanned, and can the resulting runtime be justified by the evaluation budget? |
| retained branches | 3 | Do alternative seeds produce materially different explanations? |
| residual fit order | v0.7: query from detected peaks not assigned to active branch phases; prioritize that branch-local shortlist before stale global candidates | Are remaining measured features searched without turning profile-width/background mismatch at already-explained peaks into extra phases? |
| independent evidence groups | 2 distinct reference reflections | Is an apparent addition only one coincident reflection? Resolved Kα1/Kα2 components of a single CIF line count once. |
| relative objective improvement | 2% | Does the gain exceed the negative-control envelope? |
| complexity penalty | 0.02 per additional active phase | Does a lower residual justify the extra phase under independent evidence? |
| ambiguity margin | 0.01 selection-score units | Are competing phase sets too close to select automatically? |
| inactive scale relative tolerance | 1e-6 of the largest fitted scale | Is a component numerically active or only retained by the fit basis? |
| maximum fit attempts | 300 | Is the bounded search complete enough for the declared candidate pool? |
| profile width | 0.20° 2θ Gaussian FWHM (provisional, fixed) | PG_1018's leading fit changed at 0.10° and 0.30°; what instrument- and sample-aware profile recipe is supported on the declared development split? |

Mixture scales are arbitrary nonnegative profile amplitudes. The implementation
must keep the background fixed for a run, preserve the signed residual, report
truncation, and never derive quantitative phase fractions from these settings.
The 0.2 selection algorithm retains parent hypotheses, applies the complexity
penalty only to active components, and returns no selected hypothesis when a
materially different alternative remains within the ambiguity boundary. These
values are provisional development controls; the measured Zenodo and QARR
results remain evidence for tuning and are not independent validation after
this change.

Mixture-screening v0.6 prioritizes each branch's current residual-query
shortlist before unused candidates from earlier global lookups. This fixes a
budget-ordering defect: with a full global pool and a reached fit-attempt cap,
newly retrieved residual candidates could otherwise be appended after the old
pool and never evaluated. The cap itself is unchanged; fit-attempt exhaustion
must remain visible in the report. Its minimum-evidence gate groups all spectral
components generated by one reference line as one crystallographic reflection.
The report distinguishes peaks matched by a phase profile from peak indices
used as that phase's independent evidence, so shared peaks are not presented as
new evidence for every phase in a mixture.

Mixture-screening v0.7 changes only residual-query peak selection. For each
branch, it queries from detected experimental peak centers that have not
already been assigned as independent evidence to an active phase in that
branch. Positive residual maxima from the fitted grid are no longer passed
directly to reference retrieval: profile-width or fixed-background mismatch
can leave shoulders around a peak already explained by a phase and otherwise
cause it to be reintroduced as apparent new-phase evidence. The query input is
sorted by measured peak intensity and its source is recorded in the mixture
query provenance. This is an exploratory search-policy correction, not a
physical refinement or an accuracy claim. On PG_1018 it retained several
Cr2O3 crosswalk proxies in residual fitter inputs, but no source proxy appeared
in the retained final hypotheses; the case still fails. (The PG_1018 gate on the
100-case loop was retired on 2026-09-30.)

Candidate ranking profile v0.8 is an initial development hypothesis, not a
validated optimum. For Cu Kα, its four terms are peak-position agreement
(25%), measured-intensity-weighted coverage of the ten strongest observed
peaks (35%), relative-intensity agreement restricted to matched top-ten peaks
(10%), and intensity-weighted coverage of the ten strongest predicted
reflections (30%). The observed-peak term uses each detected peak's corrected
height as its weight; it does not use integrated peak area or calculated CIF
intensity. The reference-reflection term asks whether a proposed structure's
own strongest expected lines are present, which penalizes dense accidental
coincidences. It remains vulnerable to preferred orientation, overlap, and
limited acquisition range, so its weight needs cohort-level evaluation.
For non-Cu radiation, reference intensity comparison is unsupported: the
fallback profile remains 60% position agreement, 30% unweighted top-ten
observed-peak hit fraction, and 10% unweighted in-range reference-line
coverage. The word
“precision” refers to an evaluation metric over predicted phases in a labeled
benchmark; it is not an extra per-candidate ranking term. Scores remain ranking
metrics. This v0.8 reweighting is exploratory and must be evaluated on the
declared development split before it is frozen; rerunning PG_1018 after choosing
these weights is diagnostic development evidence, not held-out validation. The
10% relative-intensity agreement term remains secondary because ideal
single-phase intensities can differ from measured multiphase intensities.

### Minimum independent-reflection support gate

The configured default remains 2 independent reflections. A label-blind
PG_1018 diagnostic raised this gate to 4 while leaving the other run settings
unchanged. It removed weak two-reflection third-phase alternatives and moved
Cr2O3-formula references into the top two hypotheses. The In2O3 + Cr2O3
formula families appeared together at ranks 6 and 9, but only alongside an
additional RbFeO2 candidate; the leading alternatives still substituted
Hf2N2O for In2O3. The analysis remained ambiguous. This suggests 4 is a useful
development value for suppressing weak coincidences, not a validated default:
the case is label-exposed, its exact reference crosswalk is unresolved, and
the source refinement is marked `automated_db`. Do not freeze the value until
its candidate recall, false-support rate, runtime, and unresolved rate are
measured on the declared training and held-out splits.

### Experimental d-spacing scale adjustment

The optional `d_spacing_scale_tolerance` is **disabled by default** at `0.0`.
An exploratory PG_1018 run used `0.015`, which searches a 31-point grid over
the multiplicative d-spacing scale interval `[0.985, 1.015]` for each
candidate. This shifts predicted reference-line positions for screening; it
does not change the CIF, refine a unit cell, alter the selected radiation, or
represent a physical calibration. The current implementation fits that scale
against the full measured scan, so reflections from unrelated phases may
influence it. The scale-grid profile fits are also outside the
`max_fit_attempts` budget. These are known false-positive and runtime risks.

On PG_1018, the adjustment surfaced In2O3 and a Cr2O3-formula reference in
separate top-three mixture hypotheses, but it did not produce the pair in one
hypothesis and the analysis remained ambiguous. The case is label-exposed and
its exact source-to-POW_COD crosswalk remains pending, so this is not a passing
case or accuracy score. Keep the adjustment at zero for normal use until its
scale is constrained by an independent calibration or a branch-residual
method, the grid work is explicitly budgeted, and it is evaluated on a
declared development set.

A paired PG_1018 diagnostic at the four-reflection gate compared the `0.015`
scale search against the disabled `0.0` default. With scaling enabled, the
In2O3 + Cr2O3 formula families appeared only at ranks 6 and 9 and each
hypothesis also included RbFeO2. With scaling disabled, In2O3 was absent from
the top ten and Cr2O3-formula entries were paired with unrelated candidates.
Both runs abstained as ambiguous; the enabled run took 833 seconds versus 537
seconds disabled. The result shows strong sensitivity to this nuisance scale,
not that the enabled result is more accurate. Keep the default at zero until
an independent calibration or instrument-aware model justifies the scale and
its behavior is evaluated across the declared development cohort.

POW_COD bounded coarse lookup uses the versioned
`compactness-major-support-exact-backfill-v2` policy. The lookup first orders
the full coarse-bin union through compact reflection support and measured
major-peak support. It then decodes those candidates in that deterministic
order and verifies that each has at least one exact d-spacing in the observed
peak windows before filling the requested candidate budget. This prevents a
coarse-bin false positive from consuming a returned slot when a later-ranked
exact hit is available. Exact verification does not repair false negatives
outside the coarse-bin union; the result remains bounded and reports scan,
reject, verified, backfill and truncation diagnostics. Use `exhaustive_exact`
for qualification when practical. The policy version and quotas used are
recorded in query provenance and analysis identity.

The v0.1 fitter shortlist policy is separate from the score: when a ranked
candidate set exceeds the fitter budget, 70% of slots remain reserved for
global leaders and the rest are filled in round-robin order from candidates
that match different members of the ten strongest observed peaks. It does not
increase the fitter budget or rank candidates as probabilities. Reports retain
the selected reference IDs and per-peak assignments so the bounded selection
can be audited. The 70/30 split is provisional and should be changed only from
measured shortlist-recall/runtime evidence, not to force a known sample label.

For XRDML files, the importer preserves the declared anode, Kα1/Kα2
wavelengths, and Kα2/Kα1 intensity ratio. `auto_from_source` uses those
components when the selected anode agrees with the file metadata. Candidate
matching and mixture profiles model both wavelengths while counting each
crystallographic reflection once as independent reference evidence. Text
formats without source spectrum metadata retain single-effective-wavelength
behavior unless the operator explicitly selects `doublets_resolved`. Reports
record the resolved components and their origin. This is a physically
motivated spectral-model correction, not a PG_1018 label-specific adjustment;
the PG_1018 rerun remains exploratory because this case was previously exposed.

## What is deliberately absent

There is no phase-fraction estimate, no universal confidence percentage, no automatic preferred-orientation correction, or automatic crystallite-size claim. POW_COD screening does not make phase claims publication-ready. Those claims require validation experiments and explicit uncertainty models.

### Cross-phase doublet evidence accounting (mixture-screening v0.10)

When an active phase has evidence for a reference reflection, the fitter marks
observed peaks within that reflection's predicted Kα component windows as
already explained. A later CIF cannot count a remaining partner lobe as a new
independent reflection merely because it selected a different observed peak
index. Inactive branch components (those below the configured relative-scale
threshold) do not reserve evidence windows; their old assignments are excluded
from the active evidence set. The phase profile may still contribute to
overlapping signal in the whole-pattern fit; support for adding another phase
must come from distinct reflection positions. The matching tolerance defines
these windows and is recorded with the analysis. The scaled branch reference is
used when optional d-spacing scaling is enabled. This conservative support
rule does not establish phase identity and can reduce recall when distinct
reflections overlap; regression tests cover inactive components and scaled,
resolved doublet partners.

The controlled PG_1018 replay kept the prior 20,000/100 lookup/fitter budgets,
the four-reflection gate, five-phase ceiling, and other settings, with
d-spacing scaling disabled. It remained ambiguous with no selected mixture.
The top ten contained the Cr2O3 formula family but not In2O3; no hypothesis
contained both source formula families. The source CIF crosswalk is unresolved
and the source refinement is marked `automated_db`. Do not call this a pass,
use it as an accuracy score, or start the 100-case loop from this result.

The v0.9 implementation was reviewed and found to let inactive branch phases
reserve windows. The correction is recorded as v0.10 and has direct unit
coverage for active/inactive scales and nonzero d-spacing scaling. The original
v0.9 PG_1018 report remains an immutable historical run; it is not represented
as an execution of v0.10.


## Remediation step 3 defaults (2026-09-30)

| Setting | Default | Meaning |
|---|---|---|
| `peak_detection` | `noise_aware` | Smoothed detection copy, noise-based prominence (`peak_min_snr` 6), width gate (`peak_min_width_deg` 0.03 plus 35% of the strongest peaks' width), prominence ranking. `legacy` keeps the old detector. |
| `background_window_deg` | 3.0 | Rolling 20th-percentile background window in degrees (noise-aware mode). |
| `profile_width_mode` / `profile_eta` | `estimated` / 0.5 | FWHM = a + b·tanθ fitted to detected peaks; pseudo-Voigt Lorentzian fraction. |
| `zero_shift_max_deg` | 0.10 | Per-branch bounded zero shift searched at seeding. |
| `displacement_search_max_deg` | 0.60 | Specimen displacement D·cosθ estimated before matching (0 disables). |
| `lattice_scale_tolerance` | 0.006 | Per-phase isotropic d-spacing scale searched by the matcher; retrieval windows widened by the same fraction. |
| `peak_tolerance_deg` | 0.10 | Narrowed from 0.20 once displacement, scale and width are modelled. |
| `allowed_elements` | none | Optional sample-context chemistry filter (see `scripts/precursor_sample_context.py`). |
| `complexity_penalty` / `ambiguity_margin` | 0.10 / 0.05 | Now **relative**: an extra phase must lower the objective by more than 10%; alternatives within 5% are ambiguous. Frozen protocols written with the old absolute values must be overridden. |

These are development defaults, not tuned or validated values.
