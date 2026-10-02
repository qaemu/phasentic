"""Deterministic, bounded multi-phase screening on a measured powder trace.

This module deliberately stops at a screening fit. Component scales describe
the fit's arbitrary reference-profile amplitudes; they are not phase fractions
and must never be presented as composition percentages.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Callable, Iterable

import numpy as np

from phasentic.domain.formula import charge_balanced, compositions_compatible, normalize_space_group_symbol
from phasentic.domain.models import Peak, ReferenceLine, ReferencePhase
from phasentic.domain.radiation import (
    Radiation,
    radiation_spectral_components,
    two_theta_from_wavelength,
)


MIXTURE_ALGORITHM_VERSION = "mixture-screening-0.17-balanced-entry-preference"
SHARED_PEAK_CONTRIBUTION_RATIO = 0.5
SAME_MATERIAL_PREFERENCE_MARGIN = 0.15
SYMMETRY_PREFERENCE_REFLECTION_RATIO = 0.8
SUPPORT_OBJECTIVE_THRESHOLD = 0.10
RESIDUAL_CANDIDATE_PEAK_SOURCE = "unassigned_detected_peaks_from_active_branch_components"
PROFILE_D_SPACING_SCALE_GRID_POINTS = 31


@dataclass(frozen=True)
class MixtureSettings:
    max_phases: int = 3
    candidate_pool: int = 100
    retained_branches: int = 3
    min_independent_evidence: int = 2
    min_objective_improvement: float = 0.02
    complexity_penalty: float = 0.02
    ambiguity_margin: float = 0.01
    abstain_when_ambiguous: bool = True
    inactive_scale_relative_tolerance: float = 1e-6
    profile_width_deg: float = 0.20
    d_spacing_scale_tolerance: float = 0.0
    max_fit_attempts: int = 300
    swap_fit_attempt_budget: int = 25
    # Optional angle-dependent width, FWHM(2theta) = a + b * tan(theta).
    # ``None`` keeps the fixed ``profile_width_deg``.
    profile_width_model: tuple[float, float] | None = None
    # Pseudo-Voigt Lorentzian fraction (0 = Gaussian).
    profile_eta: float = 0.0
    # Bounded per-branch zero shift searched when a phase set is seeded.
    zero_shift_max_deg: float = 0.0
    zero_shift_step_deg: float = 0.02
    # Reject a candidate phase when more than this fraction of its predicted
    # intensity above VISIBLE_LINE_SNR * noise_sigma is absent from the scan
    # (1.0 disables). ``noise_sigma`` is the scan's measured noise level.
    missing_intensity_max: float = 1.0
    noise_sigma: float | None = None

    def validate(self) -> "MixtureSettings":
        if isinstance(self.missing_intensity_max, bool) or not isinstance(self.missing_intensity_max, (int, float)) or not 0.0 <= float(self.missing_intensity_max) <= 1.0:
            raise ValueError("missing_intensity_max must be between 0 and 1")
        if self.noise_sigma is not None and (not isinstance(self.noise_sigma, (int, float)) or not math.isfinite(float(self.noise_sigma)) or self.noise_sigma <= 0):
            raise ValueError("noise_sigma must be positive when given")
        if not isinstance(self.max_phases, int) or isinstance(self.max_phases, bool) or not 1 <= self.max_phases <= 10:
            raise ValueError("max_phases must be between 1 and 10")
        if not isinstance(self.candidate_pool, int) or isinstance(self.candidate_pool, bool) or not 1 <= self.candidate_pool <= 2000:
            raise ValueError("candidate_pool must be between 1 and 2000")
        if not isinstance(self.retained_branches, int) or isinstance(self.retained_branches, bool) or not 1 <= self.retained_branches <= 10:
            raise ValueError("retained_branches must be between 1 and 10")
        if not isinstance(self.min_independent_evidence, int) or isinstance(self.min_independent_evidence, bool) or not 1 <= self.min_independent_evidence <= 10:
            raise ValueError("min_independent_evidence must be between 1 and 10")
        if isinstance(self.min_objective_improvement, bool) or not isinstance(self.min_objective_improvement, (int, float)) or not math.isfinite(float(self.min_objective_improvement)) or not 0.0 < self.min_objective_improvement <= 1.0:
            raise ValueError("min_objective_improvement must be in (0, 1]")
        if isinstance(self.complexity_penalty, bool) or not isinstance(self.complexity_penalty, (int, float)) or not math.isfinite(float(self.complexity_penalty)) or not 0.0 <= self.complexity_penalty <= 1.0:
            raise ValueError("complexity_penalty must be between 0 and 1")
        if isinstance(self.ambiguity_margin, bool) or not isinstance(self.ambiguity_margin, (int, float)) or not math.isfinite(float(self.ambiguity_margin)) or not 0.0 <= self.ambiguity_margin <= 1.0:
            raise ValueError("ambiguity_margin must be between 0 and 1")
        if isinstance(self.inactive_scale_relative_tolerance, bool) or not isinstance(self.inactive_scale_relative_tolerance, (int, float)) or not math.isfinite(float(self.inactive_scale_relative_tolerance)) or not 0.0 < self.inactive_scale_relative_tolerance <= 0.1:
            raise ValueError("inactive_scale_relative_tolerance must be in (0, 0.1]")
        if isinstance(self.profile_width_deg, bool) or not isinstance(self.profile_width_deg, (int, float)) or not math.isfinite(float(self.profile_width_deg)) or not 0.01 <= self.profile_width_deg <= 2.0:
            raise ValueError("profile_width_deg must be between 0.01 and 2.0 degrees")
        if (
            isinstance(self.d_spacing_scale_tolerance, bool)
            or not isinstance(self.d_spacing_scale_tolerance, (int, float))
            or not math.isfinite(float(self.d_spacing_scale_tolerance))
            or not 0.0 <= self.d_spacing_scale_tolerance <= 0.03
        ):
            raise ValueError("d_spacing_scale_tolerance must be between 0 and 0.03")
        if not isinstance(self.max_fit_attempts, int) or isinstance(self.max_fit_attempts, bool) or not 1 <= self.max_fit_attempts <= 10000:
            raise ValueError("max_fit_attempts must be between 1 and 10000")
        if (
            not isinstance(self.swap_fit_attempt_budget, int)
            or isinstance(self.swap_fit_attempt_budget, bool)
            or not 0 <= self.swap_fit_attempt_budget <= 1000
        ):
            raise ValueError("swap_fit_attempt_budget must be between 0 and 1000")
        if self.profile_width_model is not None:
            model = self.profile_width_model
            if (
                not isinstance(model, tuple)
                or len(model) != 2
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in model)
                or float(model[0]) < 0.0
                or float(model[1]) < 0.0
                or float(model[0]) + float(model[1]) <= 0.0
            ):
                raise ValueError("profile_width_model must be a non-negative (a, b) pair")
        if isinstance(self.profile_eta, bool) or not isinstance(self.profile_eta, (int, float)) or not 0.0 <= float(self.profile_eta) <= 1.0:
            raise ValueError("profile_eta must be between 0 and 1")
        if isinstance(self.zero_shift_max_deg, bool) or not isinstance(self.zero_shift_max_deg, (int, float)) or not 0.0 <= float(self.zero_shift_max_deg) <= 0.5:
            raise ValueError("zero_shift_max_deg must be between 0 and 0.5")
        if isinstance(self.zero_shift_step_deg, bool) or not isinstance(self.zero_shift_step_deg, (int, float)) or not 0.001 <= float(self.zero_shift_step_deg) <= 0.2:
            raise ValueError("zero_shift_step_deg must be between 0.001 and 0.2")
        return self

    def to_dict(self) -> dict[str, int | float]:
        return {
            "max_phases": self.max_phases,
            "candidate_pool": self.candidate_pool,
            "retained_branches": self.retained_branches,
            "min_independent_evidence": self.min_independent_evidence,
            "min_objective_improvement": self.min_objective_improvement,
            "complexity_penalty": self.complexity_penalty,
            "ambiguity_margin": self.ambiguity_margin,
            "abstain_when_ambiguous": self.abstain_when_ambiguous,
            "missing_intensity_max": self.missing_intensity_max,
            "inactive_scale_relative_tolerance": self.inactive_scale_relative_tolerance,
            "profile_width_deg": self.profile_width_deg,
            "d_spacing_scale_tolerance": self.d_spacing_scale_tolerance,
            "max_fit_attempts": self.max_fit_attempts,
            "swap_fit_attempt_budget": self.swap_fit_attempt_budget,
            "profile_width_model": list(self.profile_width_model) if self.profile_width_model is not None else None,
            "profile_eta": self.profile_eta,
            "zero_shift_max_deg": self.zero_shift_max_deg,
            "zero_shift_step_deg": self.zero_shift_step_deg,
        }


@dataclass(frozen=True)
class MixtureComponent:
    reference_id: str
    name: str
    formula: str
    screening_scale: float
    duplicate_group_id: str | None
    matched_peak_indices: tuple[int, ...]
    independent_evidence_peak_indices: tuple[int, ...]
    evidence_groups: tuple[str, ...]
    missing_expected_lines: tuple[str, ...]
    profile_d_spacing_scale: float = 1.0
    equivalence_group_id: str | None = None
    parent_family_group_id: str | None = None
    space_group: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_id": self.reference_id,
            "name": self.name,
            "formula": self.formula,
            "space_group": self.space_group,
            "screening_scale": self.screening_scale,
            "scale_semantics": "arbitrary nonnegative profile amplitude; not a phase fraction",
            "duplicate_group_id": self.duplicate_group_id,
            "equivalence_group_id": self.equivalence_group_id,
            "parent_family_group_id": self.parent_family_group_id,
            "matched_peak_indices": list(self.matched_peak_indices),
            "independent_evidence_peak_indices": list(self.independent_evidence_peak_indices),
            "evidence_groups": list(self.evidence_groups),
            "missing_expected_lines": list(self.missing_expected_lines),
            "profile_d_spacing_scale": self.profile_d_spacing_scale,
            "profile_d_spacing_scale_semantics": (
                "bounded d-spacing adjustment for screening only; not a refined CIF cell"
            ),
        }


@dataclass(frozen=True)
class MixtureComponentTrace:
    reference_id: str
    calculated_intensities: tuple[float, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_id": self.reference_id,
            "calculated_intensities": list(self.calculated_intensities),
        }


@dataclass(frozen=True)
class MixtureResidualTrace:
    angles_deg: tuple[float, ...]
    observed_intensities: tuple[float, ...]
    calculated_intensities: tuple[float, ...]
    residual_intensities: tuple[float, ...]
    truncated: bool = False
    component_traces: tuple[MixtureComponentTrace, ...] = ()
    background_intensities: tuple[float, ...] = ()
    fit_target_intensities: tuple[float, ...] = ()
    weights: tuple[float, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "angles_deg": list(self.angles_deg),
            "observed_intensities": list(self.observed_intensities),
            "calculated_intensities": list(self.calculated_intensities),
            "residual_intensities": list(self.residual_intensities),
            "truncated": self.truncated,
            "component_traces": [trace.to_dict() for trace in self.component_traces],
            "background_intensities": list(self.background_intensities),
            "fit_target_intensities": list(self.fit_target_intensities),
            "weights": list(self.weights),
        }


@dataclass(frozen=True)
class MixtureHypothesis:
    hypothesis_id: str
    components: tuple[MixtureComponent, ...]
    objective: float
    objective_improvement: float
    unexplained_peak_positions: tuple[float, ...]
    missing_expected_lines: tuple[str, ...]
    status: str
    stopping_reason: str
    fit_attempts: int
    selection_score: float
    selection_penalty: float
    active_component_count: int
    zero_shift_deg: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "zero_shift_deg": self.zero_shift_deg,
            "components": [component.to_dict() for component in self.components],
            "objective": self.objective,
            "objective_improvement": self.objective_improvement,
            "unexplained_peak_positions": list(self.unexplained_peak_positions),
            "missing_expected_lines": list(self.missing_expected_lines),
            "status": self.status,
            "stopping_reason": self.stopping_reason,
            "fit_attempts": self.fit_attempts,
            "selection_score": self.selection_score,
            "selection_penalty": self.selection_penalty,
            "active_component_count": self.active_component_count,
        }


@dataclass(frozen=True)
class MixtureResult:
    algorithm_version: str
    hypotheses: tuple[MixtureHypothesis, ...]
    selected_hypothesis_id: str | None
    residual_trace: MixtureResidualTrace
    query: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "algorithm_version": self.algorithm_version,
            "selected_hypothesis_id": self.selected_hypothesis_id,
            "hypotheses": [hypothesis.to_dict() for hypothesis in self.hypotheses],
            "residual_trace": self.residual_trace.to_dict(),
            "query": dict(self.query),
        }


def profile_fwhm(center_deg: float, width_deg: float, width_model: tuple[float, float] | None) -> float:
    """FWHM at a 2theta position: fixed, or a + b * tan(theta)."""

    if width_model is None:
        return float(width_deg)
    a, b = float(width_model[0]), float(width_model[1])
    return float(min(2.0, max(0.01, a + b * math.tan(math.radians(center_deg) / 2.0))))


def render_phase_profile(
    reference: ReferencePhase,
    angles_deg: np.ndarray,
    radiation: Radiation,
    *,
    width_deg: float,
    d_spacing_scale: float = 1.0,
    width_model: tuple[float, float] | None = None,
    eta: float = 0.0,
) -> np.ndarray:
    """Render a unit-area ideal line profile on the acquired angle grid.

    Each reflection is an area-normalized pseudo-Voigt (``eta`` = Lorentzian
    fraction; 0 is a pure Gaussian) whose FWHM is fixed or follows
    ``width_model``. Relative line intensities are integrated intensities.
    Lines are evaluated only inside a window around their centre. The phase
    profile is normalized by its trapezoidal integral, so the fitted scale is
    an arbitrary amplitude, never a phase fraction.
    """

    width = float(width_deg)
    if not math.isfinite(width) or width <= 0:
        raise ValueError("width_deg must be positive and finite")
    d_scale = float(d_spacing_scale)
    if not math.isfinite(d_scale) or not 0.5 <= d_scale <= 1.5:
        raise ValueError("d_spacing_scale must be finite and between 0.5 and 1.5")
    mixing = float(eta)
    if not math.isfinite(mixing) or not 0.0 <= mixing <= 1.0:
        raise ValueError("eta must be between 0 and 1")
    angles = np.asarray(angles_deg, dtype=float)
    if angles.ndim != 1 or angles.size < 3 or not np.all(np.isfinite(angles)):
        raise ValueError("angles_deg must be a finite one-dimensional grid")
    if np.any(np.diff(angles) <= 0):
        raise ValueError("angles_deg must be strictly increasing")
    profile = np.zeros(angles.shape, dtype=float)
    spectral_components = radiation_spectral_components(radiation)
    reach = 6.0 if mixing == 0.0 else 30.0
    four_ln2 = 4.0 * math.log(2.0)
    first, last = float(angles[0]), float(angles[-1])
    # Per-line centres and widths are computed with the same scalar code as
    # before; the window evaluation is vectorized and accumulated with
    # ``np.add.at``, which applies additions in index order, so every grid
    # point receives its line contributions in the original line order.
    centers: list[float] = []
    fwhms: list[float] = []
    weights: list[float] = []
    for line in reference.lines:
        intensity = float(line.relative_intensity)
        if not math.isfinite(intensity) or intensity <= 0:
            continue
        for wavelength, component_weight in spectral_components:
            try:
                center = two_theta_from_wavelength(line.d_spacing_angstrom * d_scale, wavelength)
            except ValueError:
                continue
            fwhm = profile_fwhm(center, width, width_model)
            if center < first - reach * fwhm or center > last + reach * fwhm:
                continue
            centers.append(center)
            fwhms.append(fwhm)
            weights.append(intensity * component_weight / fwhm)
    if centers:
        center_array = np.asarray(centers, dtype=float)
        fwhm_array = np.asarray(fwhms, dtype=float)
        lower = np.searchsorted(angles, center_array - reach * fwhm_array, side="left")
        upper = np.searchsorted(angles, center_array + reach * fwhm_array, side="right")
        lengths = np.maximum(upper - lower, 0)
        total = int(lengths.sum())
        if total:
            line_ids = np.repeat(np.arange(center_array.size), lengths)
            starts = np.cumsum(lengths) - lengths
            grid_index = lower[line_ids] + (np.arange(total) - starts[line_ids])
            offset = (angles[grid_index] - center_array[line_ids]) / fwhm_array[line_ids]
            shape = (1.0 - mixing) * np.exp(-four_ln2 * offset * offset)
            if mixing:
                shape = shape + mixing / (1.0 + 4.0 * offset * offset)
            # Divide by FWHM so the line area, not its height, follows intensity.
            np.add.at(profile, grid_index, np.asarray(weights, dtype=float)[line_ids] * shape)
    try:
        trapezoid = np.trapezoid
    except AttributeError:  # NumPy < 2.0
        trapezoid = np.trapz
    integral = float(trapezoid(profile, angles))
    if not math.isfinite(integral) or integral <= 0:
        return profile
    return profile / integral


@dataclass(frozen=True)
class _MixtureBranch:
    """One immutable beam-search branch and its fitted evidence."""

    references: tuple[ReferencePhase, ...]
    matched_peak_indices: frozenset[int]
    evidence: tuple[tuple[str, tuple[_ReflectionEvidence, ...]], ...]
    scales: np.ndarray
    profile_d_spacing_scales: tuple[float, ...]
    calculated: np.ndarray
    objective: float
    stopping_reason: str
    zero_shift_deg: float = 0.0


@dataclass(frozen=True)
class _ReflectionEvidence:
    """Observed components belonging to one crystallographic reflection."""

    line_index: int
    peak_indices: tuple[int, ...]
    label: str


def _validate_scan_range(value: tuple[float, float] | None) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("scan_range_deg must be an increasing pair")
    try:
        lower, upper = (float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError("scan_range_deg must be an increasing pair") from exc
    if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
        raise ValueError("scan_range_deg must be an increasing pair")
    return lower, upper


def select_mixture_hypotheses(
    angles_deg: np.ndarray,
    observed_intensities: np.ndarray,
    peaks: Iterable[Peak],
    references: Iterable[ReferencePhase],
    radiation: Radiation,
    *,
    tolerance_deg: float,
    settings: MixtureSettings | None = None,
    scan_range_deg: tuple[float, float] | None = None,
    background_intensities: np.ndarray | None = None,
    weights: np.ndarray | None = None,
    weight_provenance: str | None = None,
    residual_candidate_provider: Callable[[tuple[Peak, ...]], Iterable[ReferencePhase]] | None = None,
) -> MixtureResult:
    """Select bounded nonnegative phase-set hypotheses by residual improvement.

    ``observed_intensities`` is the immutable raw trace.  A supplied fixed
    background is subtracted only for fitting; the target is intentionally
    allowed to be signed so background overestimation cannot be hidden by a
    second clipping operation.  The default weights are positive trapezoidal
    grid weights and are recorded in the result query.
    """

    config = (settings or MixtureSettings()).validate()
    angles = np.asarray(angles_deg, dtype=float)
    observed = np.asarray(observed_intensities, dtype=float)
    if angles.ndim != 1 or observed.ndim != 1 or angles.size != observed.size or angles.size < 3:
        raise ValueError("mixture inputs must be equal-length one-dimensional arrays")
    if not np.all(np.isfinite(angles)) or not np.all(np.isfinite(observed)) or np.any(observed < 0):
        raise ValueError("mixture inputs must be finite and non-negative")
    if np.any(np.diff(angles) <= 0):
        raise ValueError("mixture angles must be strictly increasing")
    if not math.isfinite(tolerance_deg) or tolerance_deg <= 0:
        raise ValueError("tolerance_deg must be positive")
    resolved_scan_range = _validate_scan_range(scan_range_deg)
    peak_values = tuple(peaks)
    original_shape = observed.shape
    background_values: np.ndarray | None = None
    if background_intensities is not None:
        background_values = np.asarray(background_intensities, dtype=float)
        if background_values.shape != original_shape:
            raise ValueError("background_intensities must be finite, non-negative, and match the trace")
    weight_values: np.ndarray | None = None
    if weights is not None:
        weight_values = np.asarray(weights, dtype=float)
        if weight_values.shape != original_shape:
            raise ValueError("weights must be finite, positive, and match the angle grid")
    if resolved_scan_range is not None:
        lower, upper = resolved_scan_range
        mask = (angles >= lower) & (angles <= upper)
        if int(np.count_nonzero(mask)) < 3:
            raise ValueError("scan_range_deg must contain at least three acquired points")
        angles = angles[mask].copy()
        observed = observed[mask].copy()
        if background_values is not None:
            background_values = background_values[mask].copy()
        if weight_values is not None:
            weight_values = weight_values[mask].copy()
        peak_values = tuple(
            peak for peak in peak_values if lower <= float(peak.position_deg) <= upper
        )
    else:
        angles = angles.copy()
        observed = observed.copy()
    if background_intensities is None:
        background = np.zeros_like(observed)
        background_model = "none"
    else:
        background = background_values if background_values is not None else np.asarray(background_intensities, dtype=float)
        if background.shape != observed.shape or not np.all(np.isfinite(background)) or np.any(background < 0):
            raise ValueError("background_intensities must be finite, non-negative, and match the trace")
        background_model = "fixed-preprocessing-background"
    target = observed - background
    grid_weights, weighting = _resolve_weights(angles, weight_values)
    shift_targets = _shifted_targets(angles, target, config)
    if weight_provenance is not None and (not isinstance(weight_provenance, str) or not weight_provenance.strip()):
        raise ValueError("weight_provenance must be a non-empty string when supplied")
    resolved_weight_provenance = weight_provenance or weighting
    source_pool = _unique_references(references, limit=config.candidate_pool)
    empty_trace = _trace(
        angles,
        observed,
        background,
        np.zeros_like(observed),
        target,
        grid_weights,
    )
    if not source_pool:
        return MixtureResult(
            MIXTURE_ALGORITHM_VERSION,
            (),
            None,
            empty_trace,
            _query_metadata(
                candidate_pool_size=0,
                fit_attempts=0,
                config=config,
                tolerance_deg=tolerance_deg,
                scan_range_deg=resolved_scan_range,
                weighting=weighting,
                weight_provenance=resolved_weight_provenance,
                background_model=background_model,
                residual_query_count=0,
                stopping_reason="no_seed_passed_evidence",
            ),
        )

    profile_references: dict[str, ReferencePhase] = {}
    profile_scales: dict[str, float] = {}
    profiles: dict[str, np.ndarray] = {}
    evidence: dict[str, tuple[_ReflectionEvidence, ...]] = {}
    for reference in source_pool:
        profile_scale, profile = _fit_reference_profile_scale(
            reference,
            angles,
            target,
            grid_weights,
            radiation,
            width_deg=config.profile_width_deg,
                width_model=config.profile_width_model,
                eta=config.profile_eta,
            tolerance=config.d_spacing_scale_tolerance,
        )
        adjusted_reference = _scale_reference_d_spacings(reference, profile_scale)
        profile_references[reference.reference_id] = adjusted_reference
        profile_scales[reference.reference_id] = profile_scale
        profiles[reference.reference_id] = profile
        evidence[reference.reference_id] = _evidence(
            adjusted_reference, peak_values, radiation, tolerance_deg
        )
    pool = tuple(profile_references[reference.reference_id] for reference in source_pool)
    attempts = 0
    residual_query_count = 0
    effective_swap_budget = _effective_swap_budget(config)
    addition_attempt_limit = config.max_fit_attempts - effective_swap_budget
    swap_fit_attempts = 0
    swap_diagnostics: list[dict[str, object]] = []
    dynamic_pool: dict[str, ReferencePhase] = {item.reference_id: item for item in pool}
    root = _MixtureBranch(
        references=(),
        matched_peak_indices=frozenset(),
        evidence=(),
        scales=np.zeros(0, dtype=float),
        profile_d_spacing_scales=(),
        calculated=np.zeros_like(target),
        objective=_objective(target, np.zeros_like(target), grid_weights),
        stopping_reason="no_seed_passed_evidence",
    )
    branches: list[_MixtureBranch] = [root]
    terminal: list[_MixtureBranch] = []
    all_branches: list[_MixtureBranch] = []

    fitted_branch_ids: set[str] = set()
    while branches and attempts < addition_attempt_limit:
        expanded: list[_MixtureBranch] = []
        branch_queues: list[tuple[_MixtureBranch, list[ReferencePhase], frozenset[int]]] = []
        for branch in branches:
            branch_candidates: dict[str, ReferencePhase] = {}
            if residual_candidate_provider is not None and branch.references:
                residual_peaks = _unassigned_detected_peaks(peak_values, branch, config)
                if residual_peaks:
                    residual_query_count += 1
                    for candidate_index, candidate in enumerate(residual_candidate_provider(residual_peaks)):
                        if candidate_index >= config.candidate_pool:
                            break
                        if not isinstance(candidate, ReferencePhase):
                            raise ValueError("residual candidate provider returned a non-reference value")
                        # Query only detected peaks not already assigned to an
                        # active phase. This prevents profile-width/background
                        # residuals at explained peaks from dominating the
                        # secondary-phase candidate search.
                        if candidate.reference_id not in profile_references:
                            candidate_d_scale, candidate_profile = _fit_reference_profile_scale(
                                candidate,
                                angles,
                                target,
                                grid_weights,
                                radiation,
                                width_deg=config.profile_width_deg,
                width_model=config.profile_width_model,
                eta=config.profile_eta,
                                tolerance=config.d_spacing_scale_tolerance,
                            )
                            adjusted_candidate = _scale_reference_d_spacings(candidate, candidate_d_scale)
                            profile_references[candidate.reference_id] = adjusted_candidate
                            profile_scales[candidate.reference_id] = candidate_d_scale
                            profiles[candidate.reference_id] = candidate_profile
                            evidence[candidate.reference_id] = _evidence(
                                adjusted_candidate, peak_values, radiation, tolerance_deg
                            )
                        adjusted_candidate = profile_references[candidate.reference_id]
                        branch_candidates.setdefault(candidate.reference_id, adjusted_candidate)
                        if candidate.reference_id not in dynamic_pool and len(dynamic_pool) < 2 * config.candidate_pool:
                            dynamic_pool[candidate.reference_id] = adjusted_candidate
                        if len(branch_candidates) >= 2 * config.candidate_pool:
                            break
            # Append prior global and residual candidates after this branch's
            # newly retrieved residual shortlist. Preserve insertion order so a
            # tight fit-attempt budget tests current residual evidence first.
            for reference_id, reference in dynamic_pool.items():
                branch_candidates.setdefault(reference_id, reference)
                if len(branch_candidates) >= 2 * config.candidate_pool:
                    break
            # The caller supplies candidates in deterministic evidence-rank order.
            # Keep that order so a tight fit-attempt budget cannot silently
            # replace the best seeds with lexicographically earlier IDs.
            explained_peak_indices = _branch_explained_peak_indices(
                branch,
                peak_values,
                radiation,
                tolerance_deg,
                config,
            )
            branch_queues.append((branch, list(branch_candidates.values()), explained_peak_indices))
        # Share the level's attempt budget fairly: every retained branch gets
        # one fit attempt per round (round-robin) instead of the first branch
        # consuming the whole budget. A reference set already fitted from
        # another parent (A+B versus B+A) is skipped before it costs an attempt.
        cursors = [0 for _ in branch_queues]
        # Split the remaining budget evenly over the remaining depth so a wide
        # seed level cannot starve the search for third and later phases.
        # The seed level may use up to half the budget (the major phase must be
        # among the seeds); unused attempts roll over to deeper levels.
        depth = len(branches[0].references) if branches else 0
        remaining_budget = addition_attempt_limit - attempts
        if depth == 0:
            level_share = max(1, (remaining_budget + 1) // 2)
        else:
            level_share = max(1, remaining_budget // max(1, config.max_phases - depth))
        level_limit = attempts + level_share
        progressed = True
        while progressed and attempts < level_limit:
            progressed = False
            for slot, (branch, queue, explained_peak_indices) in enumerate(branch_queues):
                if attempts >= level_limit:
                    break
                while cursors[slot] < len(queue):
                    candidate_reference = queue[cursors[slot]]
                    cursors[slot] += 1
                    outcome = _try_branch_addition(
                        branch,
                        candidate_reference,
                        explained_peak_indices,
                        profile_references,
                        profile_scales,
                        profiles,
                        evidence,
                        fitted_branch_ids,
                        peak_values,
                        angles,
                        target,
                        grid_weights,
                        radiation,
                        tolerance_deg,
                        config,
                        shift_targets,
                    )
                    if outcome is None:
                        continue
                    attempts += 1
                    progressed = True
                    if outcome is not _REJECTED:
                        expanded.append(outcome)
                    break
        all_branches.extend(expanded)
        if not expanded:
            terminal.extend(branches)
            break
        expanded.sort(key=lambda item: (item.objective, _branch_id(item), len(item.references)))
        branches = expanded[: config.retained_branches]
        terminal.extend(item for item in branches if len(item.references) >= config.max_phases)
        branches = [item for item in branches if len(item.references) < config.max_phases]
        if not branches:
            break

    swap_branches, attempts, swap_fit_attempts, swap_diagnostics = _swap_phase_branches(
        (*all_branches, *terminal),
        tuple(dynamic_pool.values()),
        evidence,
        profiles,
        profile_scales,
        peak_values,
        target,
        grid_weights,
        radiation,
        tolerance_deg,
        config,
        attempts=attempts,
        swap_budget=effective_swap_budget,
        shift_targets=shift_targets,
    )
    all_branches.extend(swap_branches)
    terminal.extend(swap_branches)
    if attempts >= config.max_fit_attempts:
        terminal.extend(branches)
        terminal = [
            _replace_branch_reason(item, "fit_attempt_budget_exhausted")
            for item in terminal
        ]
    if not terminal:
        terminal = branches
    terminal = [
        _replace_branch_reason(item, "residual_search_converged")
        if item.stopping_reason == "residual_search_pending"
        else item
        for item in terminal
        if item.references
    ]
    if not terminal:
        return MixtureResult(
            MIXTURE_ALGORITHM_VERSION,
            (),
            None,
            empty_trace,
            _query_metadata(
                candidate_pool_size=len(dynamic_pool),
                fit_attempts=attempts,
                config=config,
                tolerance_deg=tolerance_deg,
                scan_range_deg=resolved_scan_range,
                weighting=weighting,
                weight_provenance=resolved_weight_provenance,
                background_model=background_model,
                residual_query_count=residual_query_count,
                stopping_reason="no_seed_passed_evidence",
                swap_fit_attempts=swap_fit_attempts,
                swap_diagnostics=swap_diagnostics,
            ),
        )

    # Keep parent hypotheses as valid alternatives.  A lower residual from an
    # over-complete branch must not erase a simpler explanation before the
    # complexity-aware selection step can evaluate it.
    budget_exhausted = attempts >= config.max_fit_attempts
    unique_terminal: dict[str, _MixtureBranch] = {}
    for branch in (*all_branches, *terminal):
        if not branch.references:
            continue
        if branch.stopping_reason == "residual_search_pending":
            # A branch that was still expandable when the search stopped is
            # labelled by why the search stopped, not left as "pending".
            branch = _replace_branch_reason(
                branch,
                "fit_attempt_budget_exhausted" if budget_exhausted else "residual_search_converged",
            )
        identifier = _branch_id(branch)
        previous = unique_terminal.get(identifier)
        if previous is None or branch.objective < previous.objective:
            unique_terminal[identifier] = branch
    ordered_terminal = sorted(
        unique_terminal.values(),
        key=lambda item: (item.objective, _branch_id(item)),
    )
    hypotheses = tuple(
        _hypothesis(
            branch,
            peak_values,
            evidence,
            radiation,
            tolerance_deg,
            config,
            attempts,
            scan_range=(float(angles[0]), float(angles[-1])),
            angles=angles,
            profiles=profiles,
        )
        for branch in ordered_terminal
    )
    ranked = tuple(
        sorted(
            (
                item
                for item in zip(hypotheses, ordered_terminal, strict=True)
                if item[0].active_component_count > 0
            ),
            key=lambda item: (item[0].selection_score, item[0].hypothesis_id),
        )
    )
    if not ranked:
        return MixtureResult(
            MIXTURE_ALGORITHM_VERSION,
            (),
            None,
            empty_trace,
            _query_metadata(
                candidate_pool_size=len(dynamic_pool),
                fit_attempts=attempts,
                config=config,
                tolerance_deg=tolerance_deg,
                scan_range_deg=resolved_scan_range,
                weighting=weighting,
                weight_provenance=resolved_weight_provenance,
                background_model=background_model,
                residual_query_count=residual_query_count,
                stopping_reason="no_active_components",
                swap_fit_attempts=swap_fit_attempts,
                swap_diagnostics=swap_diagnostics,
            ),
        )
    ranked_hypotheses = [item[0] for item in ranked[: config.retained_branches]]
    ranked_branches = [item[1] for item in ranked[: config.retained_branches]]
    selected_hypothesis_id: str | None = ranked_hypotheses[0].hypothesis_id
    stopping_reason = ranked_hypotheses[0].stopping_reason
    if len(ranked_hypotheses) > 1:
        # Among alternatives that describe the same materials and fit within
        # the ambiguity margin, prefer the most symmetric description (fewest
        # distinct reflections): a lower-symmetry setting of the same structure
        # can fit marginally better only by having more free lines.
        leader = ranked_hypotheses[0]
        best_selection_score = leader.selection_score
        peers = [
            index
            for index, item in enumerate(ranked_hypotheses)
            # Same-material alternatives use a looser window than competing
            # explanations: they differ only in database entry or setting.
            if _relative_margin(leader.selection_score, item.selection_score) <= max(config.ambiguity_margin, SAME_MATERIAL_PREFERENCE_MARGIN)
            and (
                index == 0
                or (
                    (_same_compositions(leader, item) or not _formulas_balanced(leader))
                    and _chemically_equivalent(leader, item, profile_references, radiation, tolerance_deg)
                )
            )
        ]
        if len(peers) > 1:
            def reflection_count(item: MixtureHypothesis) -> int:
                total = 0
                for component in item.components:
                    reference = profile_references.get(component.reference_id)
                    if reference is not None:
                        total += sum(
                            1
                            for angle, _intensity in _merged_reflections(reference, radiation)
                            if float(angles[0]) <= angle <= float(angles[-1])
                        )
                return total

            leader_count = reflection_count(leader)
            preferred = min(peers, key=lambda index: (reflection_count(ranked_hypotheses[index]), index))
            # Only a clearly more symmetric description (at least 20% fewer
            # distinct reflections) displaces the best fit; small differences
            # come from database intensity cut-offs, not symmetry.
            if reflection_count(ranked_hypotheses[preferred]) > SYMMETRY_PREFERENCE_REFLECTION_RATIO * leader_count:
                preferred = 0
            if preferred == 0 and not _formulas_balanced(leader):
                # An entry stored under a formula that cannot be charge
                # balanced (calcite as "C Ca O") yields to an equivalent entry
                # of the same material whose formula can.
                preferred = next((index for index in peers if _formulas_balanced(ranked_hypotheses[index])), 0)
            if preferred != 0:
                ranked_hypotheses.insert(0, ranked_hypotheses.pop(preferred))
                ranked_branches.insert(0, ranked_branches.pop(preferred))
                selected_hypothesis_id = ranked_hypotheses[0].hypothesis_id
                stopping_reason = ranked_hypotheses[0].stopping_reason
        first = ranked_hypotheses[0]
        # Alternatives that describe the same materials with other POW_COD
        # entries (same compositions and space groups) are not a competing
        # explanation; compare against the first chemically different one.
        competitor_index = next(
            (
                index
                for index, item in enumerate(ranked_hypotheses[1:], start=1)
                if not _chemically_equivalent(first, item, profile_references, radiation, tolerance_deg)
            ),
            None,
        )
        second = ranked_hypotheses[competitor_index] if competitor_index is not None else None
        if second is not None:
            # Measure the competitor against the best score found, not against a
            # same-material description promoted for symmetry.
            score_margin = _relative_margin(best_selection_score, second.selection_score)
            objective_gain = second.objective - first.objective
            selection_is_ambiguous = (
                first.active_component_count <= second.active_component_count
                or objective_gain < config.min_objective_improvement
            )
            if score_margin <= config.ambiguity_margin and selection_is_ambiguous:
                if config.abstain_when_ambiguous:
                    selected_hypothesis_id = None
                    stopping_reason = "ambiguous_selection"
                else:
                    stopping_reason = "ambiguous_best_reported"
                ranked_hypotheses[0] = replace(first, status="ambiguous")
                ranked_hypotheses[competitor_index] = replace(second, status="ambiguous")
    ordered_terminal = ranked_branches
    hypotheses = tuple(ranked_hypotheses)
    selected = ordered_terminal[0]
    selected_active_indices = _active_component_indices(selected, config)
    trace = _trace(
        angles,
        observed,
        background,
        selected.calculated,
        shift_targets.get(selected.zero_shift_deg, target),
        grid_weights,
        component_traces=tuple(
            MixtureComponentTrace(
                reference.reference_id,
                tuple(float(value) for value in profiles[reference.reference_id] * selected.scales[index]),
            )
            for index in selected_active_indices
            for reference in (selected.references[index],)
        ),
    )
    return MixtureResult(
        MIXTURE_ALGORITHM_VERSION,
        hypotheses,
        selected_hypothesis_id,
        trace,
        _query_metadata(
            candidate_pool_size=len(dynamic_pool),
            fit_attempts=attempts,
            config=config,
            tolerance_deg=tolerance_deg,
            scan_range_deg=resolved_scan_range,
            weighting=weighting,
            weight_provenance=resolved_weight_provenance,
            background_model=background_model,
            residual_query_count=residual_query_count,
            stopping_reason=stopping_reason,
            retained_branches=len(hypotheses),
            selection_margin=(
                hypotheses[1].selection_score - hypotheses[0].selection_score
                if len(hypotheses) > 1
                else None
            ),
            swap_fit_attempts=swap_fit_attempts,
            swap_diagnostics=swap_diagnostics,
        ),
    )



_REJECTED = object()


def _try_branch_addition(
    branch: "_MixtureBranch",
    candidate_reference: ReferencePhase,
    explained_peak_indices: frozenset[int],
    profile_references: dict[str, ReferencePhase],
    profile_scales: dict[str, float],
    profiles: dict[str, np.ndarray],
    evidence: dict[str, tuple["_ReflectionEvidence", ...]],
    fitted_branch_ids: set[str],
    peak_values: tuple[Peak, ...],
    angles: np.ndarray,
    target: np.ndarray,
    grid_weights: np.ndarray,
    radiation: Radiation,
    tolerance_deg: float,
    config: MixtureSettings,
    shift_targets: dict[float, np.ndarray] | None = None,
):
    """Evaluate one candidate addition to a branch.

    Returns ``None`` when the candidate is ineligible (no fit attempt is
    spent), ``_REJECTED`` when a fit was spent but did not improve the branch,
    or the new branch.
    """

    reference = profile_references.get(candidate_reference.reference_id, candidate_reference)
    group = _reference_group(reference)
    if group in {_reference_group(item) for item in branch.references}:
        return None
    # Another database entry of a material already in the branch is not a
    # second phase (same composition and space group, or the same strong
    # reflections).
    if any(_same_material(reference, item, radiation, tolerance_deg) for item in branch.references):
        return None
    if reference.reference_id not in profiles:
        profile_d_scale, profile = _fit_reference_profile_scale(
            reference,
            angles,
            target,
            grid_weights,
            radiation,
            width_deg=config.profile_width_deg,
                width_model=config.profile_width_model,
                eta=config.profile_eta,
            tolerance=config.d_spacing_scale_tolerance,
        )
        reference = _scale_reference_d_spacings(reference, profile_d_scale)
        profile_references[reference.reference_id] = reference
        profile_scales[reference.reference_id] = profile_d_scale
        profiles[reference.reference_id] = profile
        evidence[reference.reference_id] = _evidence(reference, peak_values, radiation, tolerance_deg)
    available_reflections = tuple(
        _ReflectionEvidence(
            line_index=reflection.line_index,
            peak_indices=tuple(index for index in reflection.peak_indices if index not in explained_peak_indices),
            label=reflection.label,
        )
        for reflection in evidence[reference.reference_id]
        if any(index not in explained_peak_indices for index in reflection.peak_indices)
    )
    if len(available_reflections) < config.min_independent_evidence:
        return None
    proposed = branch.references + (reference,)
    proposed_id = _branch_id_from_references(proposed)
    if proposed_id in fitted_branch_ids:
        return None
    fitted_branch_ids.add(proposed_id)
    matched = tuple(
        index
        for reflection in available_reflections
        for index in reflection.peak_indices
        if index not in explained_peak_indices
    )
    matrix = np.column_stack([profiles[item.reference_id] for item in proposed])
    targets = shift_targets or {0.0: target}
    if branch.references:
        # A branch keeps the zero shift chosen when it was seeded.
        zero_shift = branch.zero_shift_deg
        scales, calculated, objective = _fit(matrix, targets[zero_shift], grid_weights)
    else:
        # Seed: choose the instrument zero shift that best fits this phase.
        best: tuple[float, float, np.ndarray, np.ndarray] | None = None
        for shift in sorted(targets, key=lambda value: (abs(value), value)):
            trial_scales, trial_calculated, trial_objective = _fit(matrix, targets[shift], grid_weights)
            if best is None or trial_objective < best[0] - 1e-12:
                best = (trial_objective, shift, trial_scales, trial_calculated)
        objective, zero_shift, scales, calculated = best
    improvement = (branch.objective - objective) / max(branch.objective, 1e-12)
    if branch.references and improvement < config.min_objective_improvement:
        return _REJECTED
    if config.missing_intensity_max < 1.0 and config.noise_sigma:
        contribution = matrix[:, -1] * float(scales[-1])
        if _missing_visible_fraction(
            reference, contribution, targets[zero_shift], angles, radiation, tolerance_deg, float(config.noise_sigma)
        ) > config.missing_intensity_max:
            return _REJECTED
    return _MixtureBranch(
        references=proposed,
        matched_peak_indices=frozenset(branch.matched_peak_indices | set(matched)),
        evidence=branch.evidence + ((reference.reference_id, available_reflections),),
        scales=scales,
        profile_d_spacing_scales=branch.profile_d_spacing_scales + (profile_scales[reference.reference_id],),
        calculated=calculated,
        objective=objective,
        stopping_reason=(
            "phase_limit_reached" if len(proposed) >= config.max_phases else "residual_search_pending"
        ),
        zero_shift_deg=zero_shift,
    )



VISIBLE_LINE_SNR = 5.0
ABSENT_OBSERVED_RATIO = 0.3


def _missing_visible_fraction(
    reference: ReferencePhase,
    contribution: np.ndarray,
    target: np.ndarray,
    angles: np.ndarray,
    radiation: Radiation,
    tolerance_deg: float,
    noise_sigma: float,
) -> float:
    """Fraction of a phase's clearly visible predicted intensity that the scan lacks.

    A line is visible when the fitted contribution peaks above
    VISIBLE_LINE_SNR * noise within the tolerance window; it is absent when
    the observed (background-subtracted) signal there stays below
    ABSENT_OBSERVED_RATIO of that prediction. Other phases' intensity at the
    same place counts as present, so overlaps never cause a rejection.
    """

    wavelength = radiation_spectral_components(radiation)[0][0]
    visible = absent = 0.0
    for line in reference.lines:
        try:
            center = two_theta_from_wavelength(line.d_spacing_angstrom, wavelength)
        except ValueError:
            continue
        lower = int(np.searchsorted(angles, center - tolerance_deg, side="left"))
        upper = int(np.searchsorted(angles, center + tolerance_deg, side="right"))
        if upper <= lower:
            continue
        predicted = float(np.max(contribution[lower:upper]))
        if predicted < VISIBLE_LINE_SNR * noise_sigma:
            continue
        visible += predicted
        if float(np.max(target[lower:upper])) < ABSENT_OBSERVED_RATIO * predicted:
            absent += predicted
    return absent / visible if visible > 0 else 0.0


def _shifted_targets(angles: np.ndarray, target: np.ndarray, config: MixtureSettings) -> dict[float, np.ndarray]:
    """Fit targets for a bounded grid of instrument zero shifts.

    A zero error ``s`` means measured angle = true angle + s, so the target in
    the reference frame is ``observed(angle + s)``. Shifting the one target is
    cheaper than re-rendering every phase profile and applies the same shift
    to every phase, as a real zero error does.
    """

    targets = {0.0: target}
    limit = float(config.zero_shift_max_deg)
    step = float(config.zero_shift_step_deg)
    if limit <= 0.0:
        return targets
    count = int(math.floor(limit / step + 1e-9))
    for index in range(1, count + 1):
        for sign in (-1.0, 1.0):
            shift = round(sign * index * step, 6)
            targets[shift] = np.interp(angles + shift, angles, target)
    return targets



def _chemically_equivalent(
    first: MixtureHypothesis,
    second: MixtureHypothesis,
    references: dict[str, ReferencePhase] | None = None,
    radiation: Radiation | None = None,
    tolerance_deg: float = 0.1,
) -> bool:
    """One-to-one pairing of components that describe the same material.

    Two components are the same material when they share an equivalence group,
    have compatible composition and space group, or have indistinguishable
    strong reflections (POW_COD sometimes stores the same structure under an
    incomplete formula). Indistinguishable alternatives are reported but do
    not make the selection ambiguous.
    """

    if len(first.components) != len(second.components):
        return False
    remaining = list(second.components)
    for component in first.components:
        group = _group_key(component)
        match = next(
            (
                other
                for other in remaining
                if _group_key(other) == group
                or _patterns_indistinguishable(component, other, references, radiation, tolerance_deg)
                or (
                    compositions_compatible(component.formula, other.formula, ignore_hydrogen=True)
                    and normalize_space_group_symbol(component.space_group) is not None
                    and normalize_space_group_symbol(component.space_group)
                    == normalize_space_group_symbol(other.space_group)
                )
            ),
            None,
        )
        if match is None:
            return False
        remaining.remove(match)
    return True


def _same_material(
    first: ReferencePhase, second: ReferencePhase, radiation: Radiation, tolerance_deg: float
) -> bool:
    symbol = normalize_space_group_symbol(first.space_group)
    if (
        symbol is not None
        and symbol == normalize_space_group_symbol(second.space_group)
        and compositions_compatible(first.formula, second.formula, ignore_hydrogen=True)
    ):
        return True
    a = _strong_line_angles(first, radiation)
    b = _strong_line_angles(second, radiation)
    if len(a) < 3 or len(b) < 3:
        return False
    a_in_b = sum(any(abs(x - y) <= tolerance_deg for y in b) for x in a) / len(a)
    b_in_a = sum(any(abs(x - y) <= tolerance_deg for y in a) for x in b) / len(b)
    return min(a_in_b, b_in_a) >= 0.8


def _merged_reflections(reference: ReferencePhase, radiation: Radiation, merge_deg: float = 0.02) -> list[tuple[float, float]]:
    """(angle, intensity) with coincident reflections merged.

    A low-symmetry setting of a structure lists symmetry-split reflections at
    the same angle separately; merging them makes pattern comparison and
    symmetry counting independent of the setting.
    """

    points: list[tuple[float, float]] = []
    for line in reference.lines:
        try:
            points.append((two_theta_from_wavelength(line.d_spacing_angstrom, radiation.wavelength_angstrom), max(line.relative_intensity, 0.0)))
        except ValueError:
            continue
    points.sort()
    merged: list[list[float]] = []
    for angle, intensity in points:
        if merged and angle - merged[-1][0] <= merge_deg:
            total = merged[-1][1] + intensity
            if total > 0:
                merged[-1][0] = (merged[-1][0] * merged[-1][1] + angle * intensity) / total
            merged[-1][1] = total
        else:
            merged.append([angle, intensity])
    return [(angle, intensity) for angle, intensity in merged]


def _strong_line_angles(reference: ReferencePhase, radiation: Radiation, count: int = 10) -> list[float]:
    merged = _merged_reflections(reference, radiation)
    return [angle for angle, _intensity in sorted(merged, key=lambda item: -item[1])[:count]]


def _patterns_indistinguishable(
    left: MixtureComponent,
    right: MixtureComponent,
    references: dict[str, ReferencePhase] | None,
    radiation: Radiation | None,
    tolerance_deg: float,
    *,
    minimum_fraction: float = 0.8,
) -> bool:
    if references is None or radiation is None:
        return False
    first = references.get(left.reference_id)
    second = references.get(right.reference_id)
    if first is None or second is None:
        return False
    a = _strong_line_angles(first, radiation)
    b = _strong_line_angles(second, radiation)
    if len(a) < 3 or len(b) < 3:
        return False
    a_in_b = sum(any(abs(x - y) <= tolerance_deg for y in b) for x in a) / len(a)
    b_in_a = sum(any(abs(x - y) <= tolerance_deg for y in a) for x in b) / len(b)
    return min(a_in_b, b_in_a) >= minimum_fraction


def _relative_margin(best: float, other: float) -> float:
    """Relative selection-score gap; ambiguity is judged on this ratio."""

    return (other - best) / max(abs(best), 1e-9)


def _formulas_balanced(hypothesis: MixtureHypothesis) -> bool:
    return all(charge_balanced(component.formula) for component in hypothesis.components)


def _same_compositions(first: MixtureHypothesis, second: MixtureHypothesis) -> bool:
    """One-to-one pairing of components with compatible compositions."""

    if len(first.components) != len(second.components):
        return False
    remaining = list(second.components)
    for component in first.components:
        match = next((other for other in remaining if compositions_compatible(component.formula, other.formula, ignore_hydrogen=True)), None)
        if match is None:
            return False
        remaining.remove(match)
    return True


def _group_key(component: MixtureComponent) -> str:
    return component.equivalence_group_id or component.duplicate_group_id or component.reference_id

def _fit(matrix: np.ndarray, target: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        calculated = np.zeros_like(target)
        return np.zeros(0, dtype=float), calculated, _objective(target, calculated, weights)
    try:
        from scipy.optimize import nnls

        square_root_weights = np.sqrt(weights)
        scales, _ = nnls(matrix * square_root_weights[:, None], target * square_root_weights)
    except Exception as exc:
        raise RuntimeError("MIXTURE_NNLS_UNAVAILABLE: nonnegative fit failed") from exc
    calculated = matrix @ scales
    return scales, calculated, _objective(target, calculated, weights)


def _scale_reference_d_spacings(reference: ReferencePhase, scale: float) -> ReferencePhase:
    if scale == 1.0:
        return reference
    return replace(
        reference,
        lines=tuple(
            ReferenceLine(line.d_spacing_angstrom * scale, line.relative_intensity, line.hkl)
            for line in reference.lines
        ),
    )


def _fit_reference_profile_scale(
    reference: ReferencePhase,
    angles: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    radiation: Radiation,
    *,
    width_deg: float,
    tolerance: float,
    width_model: tuple[float, float] | None = None,
    eta: float = 0.0,
) -> tuple[float, np.ndarray]:
    """Choose a bounded isotropic d-spacing scale for screening-profile fit."""

    shape = {"width_deg": width_deg, "width_model": width_model, "eta": eta}
    if tolerance <= 0.0:
        return 1.0, render_phase_profile(reference, angles, radiation, **shape)
    scales = np.linspace(
        1.0 - tolerance,
        1.0 + tolerance,
        PROFILE_D_SPACING_SCALE_GRID_POINTS,
    )
    best_scale = 1.0
    best_profile = render_phase_profile(reference, angles, radiation, **shape)
    _, _, best_objective = _fit(best_profile[:, None], target, weights)
    for scale in scales:
        candidate_scale = float(scale)
        profile = render_phase_profile(
            reference,
            angles,
            radiation,
            d_spacing_scale=candidate_scale,
            **shape,
        )
        _, _, objective = _fit(profile[:, None], target, weights)
        if objective < best_objective - 1e-12 or (
            abs(objective - best_objective) <= 1e-12
            and abs(candidate_scale - 1.0) < abs(best_scale - 1.0)
        ):
            best_scale = candidate_scale
            best_profile = profile
            best_objective = objective
    return best_scale, best_profile


def _objective(target: np.ndarray, calculated: np.ndarray, weights: np.ndarray) -> float:
    residual = target - calculated
    denominator = max(float(np.sum(weights * target * target)), 1e-12)
    return max(0.0, float(np.sum(weights * residual * residual) / denominator))


def _resolve_weights(angles: np.ndarray, supplied: np.ndarray | None) -> tuple[np.ndarray, str]:
    if supplied is not None:
        values = np.asarray(supplied, dtype=float)
        if values.shape != angles.shape or not np.all(np.isfinite(values)) or np.any(values <= 0):
            raise ValueError("weights must be finite, positive, and match the angle grid")
        return values.copy(), "caller-supplied"
    spacing = np.diff(angles)
    values = np.empty_like(angles)
    values[0] = spacing[0] / 2.0
    values[-1] = spacing[-1] / 2.0
    if values.size > 2:
        values[1:-1] = (angles[2:] - angles[:-2]) / 2.0
    # Unit mean keeps objective magnitudes stable without changing the NNLS
    # solution or the relative importance of non-uniform scan intervals.
    values /= max(float(np.mean(values)), 1e-12)
    return values, "trapezoidal-grid"


def _unique_references(references: Iterable[ReferencePhase], *, limit: int) -> tuple[ReferencePhase, ...]:
    unique: dict[str, ReferencePhase] = {}
    for reference in references:
        group = _reference_group(reference)
        if group not in unique:
            unique[group] = reference
    return tuple(unique.values())[:limit]


def _branch_id(branch: _MixtureBranch) -> str:
    return "+".join(sorted(reference.reference_id for reference in branch.references))


def _reference_group(reference: ReferencePhase) -> str:
    """Return the strict identity used to prevent duplicate phase selection."""

    return reference.equivalence_group_id or reference.duplicate_group_id or reference.reference_id


def _replace_branch_reason(branch: _MixtureBranch, reason: str) -> _MixtureBranch:
    return _MixtureBranch(
        references=branch.references,
        matched_peak_indices=branch.matched_peak_indices,
        evidence=branch.evidence,
        scales=branch.scales,
        profile_d_spacing_scales=branch.profile_d_spacing_scales,
        calculated=branch.calculated,
        objective=branch.objective,
        stopping_reason=reason,
        zero_shift_deg=branch.zero_shift_deg,
    )


def _trace(
    angles: np.ndarray,
    observed: np.ndarray,
    background: np.ndarray,
    calculated: np.ndarray,
    target: np.ndarray,
    weights: np.ndarray,
    *,
    component_traces: tuple[MixtureComponentTrace, ...] = (),
) -> MixtureResidualTrace:
    return MixtureResidualTrace(
        angles_deg=tuple(float(value) for value in angles),
        observed_intensities=tuple(float(value) for value in observed),
        calculated_intensities=tuple(float(value) for value in calculated),
        residual_intensities=tuple(float(value) for value in target - calculated),
        component_traces=component_traces,
        background_intensities=tuple(float(value) for value in background),
        fit_target_intensities=tuple(float(value) for value in target),
        weights=tuple(float(value) for value in weights),
    )


def _query_metadata(
    *,
    candidate_pool_size: int,
    fit_attempts: int,
    config: MixtureSettings,
    tolerance_deg: float,
    scan_range_deg: tuple[float, float] | None,
    weighting: str,
    weight_provenance: str,
    background_model: str,
    residual_query_count: int,
    stopping_reason: str,
    retained_branches: int = 0,
    selection_margin: float | None = None,
    swap_fit_attempts: int = 0,
    swap_diagnostics: Iterable[dict[str, object]] = (),
) -> dict[str, object]:
    return {
        "candidate_pool_size": candidate_pool_size,
        "retained_branches": retained_branches,
        "fit_attempts": fit_attempts,
        "max_phases": config.max_phases,
        "candidate_pool_limit": config.candidate_pool,
        "minimum_independent_evidence": config.min_independent_evidence,
        "minimum_objective_improvement": config.min_objective_improvement,
        "complexity_penalty": config.complexity_penalty,
        "complexity_penalty_semantics": "relative: selection = objective * (1 + penalty) ** (phases - 1)",
        "ambiguity_margin": config.ambiguity_margin,
        "abstain_when_ambiguous": config.abstain_when_ambiguous,
        "ambiguity_margin_semantics": "relative selection-score gap",
        "inactive_scale_relative_tolerance": config.inactive_scale_relative_tolerance,
        "scan_range_deg": list(scan_range_deg) if scan_range_deg is not None else None,
        "max_fit_attempts": config.max_fit_attempts,
        "swap_fit_attempt_budget": config.swap_fit_attempt_budget,
        "effective_swap_fit_attempt_budget": _effective_swap_budget(config),
        "swap_fit_attempts": swap_fit_attempts,
        "swap_proposals": [dict(item) for item in swap_diagnostics],
        "phase_search_moves": ["seed", "add", "preserve_smaller_parent", "single_component_swap"],
        "profile_width_deg": config.profile_width_deg,
        "d_spacing_scale_tolerance": config.d_spacing_scale_tolerance,
        "profile_d_spacing_scale_mode": (
            "bounded-single-reference-full-pattern-fit" if config.d_spacing_scale_tolerance else "disabled"
        ),
        "profile_d_spacing_scale_grid_points": (
            PROFILE_D_SPACING_SCALE_GRID_POINTS if config.d_spacing_scale_tolerance else 1
        ),
        "profile_model": "area-normalized-pseudo-voigt" if config.profile_eta else "area-normalized-gaussian",
        "profile_eta": config.profile_eta,
        "profile_width_model": list(config.profile_width_model) if config.profile_width_model is not None else None,
        "zero_shift_max_deg": config.zero_shift_max_deg,
        "zero_shift_step_deg": config.zero_shift_step_deg,
        "fit_model": "nonnegative-least-squares-on-signed-background-corrected-grid",
        "background_model": background_model,
        "fit_target": "raw-minus-fixed-background",
        "weighting": weighting,
        "weight_provenance": weight_provenance,
        "residual_candidate_requeries": residual_query_count,
        "residual_candidate_peak_source": RESIDUAL_CANDIDATE_PEAK_SOURCE,
        "quantitative_phase_fractions": False,
        "tolerance_deg": tolerance_deg,
        "stopping_reason": stopping_reason,
        "selection_margin": selection_margin,
        "support_objective_threshold": SUPPORT_OBJECTIVE_THRESHOLD,
        "support_policy": (
            f"objective<{SUPPORT_OBJECTIVE_THRESHOLD:g} and at least "
            f"{config.min_independent_evidence} distinct reference reflections; "
            "resolved spectral components count once, and observed peaks inside "
            "an earlier phase's matched-reflection windows are not independent evidence"
        ),
        "independent_evidence_unit": "distinct_reference_line_across_spectral_components",
    }


def _effective_swap_budget(config: MixtureSettings) -> int:
    # Preserve the full search budget for candidate addition on short runs.
    # A swap reserve becomes available only when the configured total budget
    # can actually spare one fifth of its attempts.
    return min(config.swap_fit_attempt_budget, config.max_fit_attempts // 5)


def _hypothesis(
    branch: _MixtureBranch,
    peaks: tuple[Peak, ...],
    evidence: dict[str, tuple[_ReflectionEvidence, ...]],
    radiation: Radiation,
    tolerance_deg: float,
    config: MixtureSettings,
    attempts: int,
    *,
    scan_range: tuple[float, float],
    angles: np.ndarray | None = None,
    profiles: dict[str, np.ndarray] | None = None,
) -> MixtureHypothesis:
    active_indices = _active_component_indices(branch, config)
    if angles is not None and profiles is not None:
        branch_evidence = _dominant_peak_evidence(branch, active_indices, evidence, peaks, angles, profiles)
    else:
        branch_evidence = dict(branch.evidence)
    components = tuple(
        _component(
            branch.references[index],
            float(branch.scales[index]),
            float(branch.profile_d_spacing_scales[index]),
            evidence[branch.references[index].reference_id],
            branch_evidence.get(branch.references[index].reference_id, ()),
            peaks,
            radiation,
            tolerance_deg,
            scan_range=scan_range,
        )
        for index in active_indices
    )
    missing = tuple(sorted({line for component in components for line in component.missing_expected_lines}))
    active_matched_peak_indices = {
        peak_index
        for component in components
        for peak_index in component.matched_peak_indices
    }
    groups = {
        (branch.references[index].reference_id, reflection.line_index)
        for index in active_indices
        for reflection in branch_evidence.get(branch.references[index].reference_id, ())
    }
    status = (
        "supported"
        if branch.objective < SUPPORT_OBJECTIVE_THRESHOLD
        and len(groups) >= config.min_independent_evidence
        else "tentative"
    )
    # Relative complexity penalty: each extra phase must lower the objective by
    # more than ``complexity_penalty`` (fraction) to be preferred. An absolute
    # penalty overwhelmed genuine minor phases once fits became good.
    selection_score = branch.objective * (1.0 + config.complexity_penalty) ** max(len(components) - 1, 0)
    selection_penalty = selection_score - branch.objective
    return MixtureHypothesis(
        hypothesis_id=_branch_id(branch),
        components=components,
        objective=branch.objective,
        objective_improvement=max(0.0, 1.0 - branch.objective),
        unexplained_peak_positions=tuple(
            float(peaks[index].position_deg)
            for index in range(len(peaks))
            if index not in active_matched_peak_indices
        ),
        missing_expected_lines=missing,
        status=status,
        stopping_reason=branch.stopping_reason,
        fit_attempts=attempts,
        selection_score=selection_score,
        selection_penalty=selection_penalty,
        active_component_count=len(components),
        zero_shift_deg=branch.zero_shift_deg,
    )



def _dominant_peak_evidence(
    branch: _MixtureBranch,
    active_indices: tuple[int, ...],
    evidence: dict[str, tuple[_ReflectionEvidence, ...]],
    peaks: tuple[Peak, ...],
    angles: np.ndarray,
    profiles: dict[str, np.ndarray],
) -> dict[str, tuple[_ReflectionEvidence, ...]]:
    """Credit each observed peak to the phase that dominates it in the fit.

    Search-time evidence depends on the order in which phases were added. For
    the reported hypothesis, a matched peak is independent evidence only for
    the active component whose fitted profile contributes most at that peak,
    and only when no other component contributes at least
    ``SHARED_PEAK_CONTRIBUTION_RATIO`` of that amount. The result does not
    depend on insertion order.
    """

    grid = np.asarray(angles, dtype=float)
    contributions: dict[str, np.ndarray] = {}
    for index in active_indices:
        reference = branch.references[index]
        profile = profiles.get(reference.reference_id)
        if profile is None:
            continue
        contributions[reference.reference_id] = profile * float(branch.scales[index])
    owner: dict[int, str | None] = {}
    for peak_index, peak in enumerate(peaks):
        grid_index = int(np.clip(np.searchsorted(grid, float(peak.position_deg)), 0, grid.size - 1))
        values = sorted(
            ((float(curve[grid_index]), reference_id) for reference_id, curve in contributions.items()),
            key=lambda item: (-item[0], item[1]),
        )
        if not values or values[0][0] <= 0.0:
            owner[peak_index] = None
        elif len(values) > 1 and values[1][0] >= SHARED_PEAK_CONTRIBUTION_RATIO * values[0][0]:
            owner[peak_index] = None
        else:
            owner[peak_index] = values[0][1]
    credited: dict[str, tuple[_ReflectionEvidence, ...]] = {}
    for reference_id in contributions:
        reflections = []
        for reflection in evidence.get(reference_id, ()):
            owned = tuple(index for index in reflection.peak_indices if owner.get(index) == reference_id)
            if owned:
                reflections.append(
                    _ReflectionEvidence(line_index=reflection.line_index, peak_indices=owned, label=reflection.label)
                )
        credited[reference_id] = tuple(reflections)
    return credited

def _active_component_indices(branch: _MixtureBranch, config: MixtureSettings) -> tuple[int, ...]:
    if not branch.references or branch.scales.size == 0:
        return ()
    finite_scales = np.asarray(branch.scales, dtype=float)
    finite_scales = np.where(np.isfinite(finite_scales), finite_scales, 0.0)
    maximum = float(np.max(finite_scales)) if finite_scales.size else 0.0
    if maximum <= 0.0:
        return ()
    threshold = maximum * config.inactive_scale_relative_tolerance
    return tuple(index for index, scale in enumerate(finite_scales) if scale > threshold)


def _swap_phase_branches(
    source_branches: Iterable[_MixtureBranch],
    candidates: tuple[ReferencePhase, ...],
    evidence: dict[str, tuple[_ReflectionEvidence, ...]],
    profiles: dict[str, np.ndarray],
    profile_scales: dict[str, float],
    peaks: tuple[Peak, ...],
    target: np.ndarray,
    weights: np.ndarray,
    radiation: Radiation,
    tolerance_deg: float,
    config: MixtureSettings,
    *,
    attempts: int,
    swap_budget: int,
    shift_targets: dict[float, np.ndarray] | None = None,
) -> tuple[list[_MixtureBranch], int, int, list[dict[str, object]]]:
    """Try a bounded one-for-one replacement around the best retained sets."""

    if swap_budget <= 0:
        return [], attempts, 0, []
    unique_branches: dict[str, _MixtureBranch] = {}
    for branch in source_branches:
        identifier = _branch_id(branch)
        if branch.references and identifier not in unique_branches:
            unique_branches[identifier] = branch
    known_ids = set(unique_branches)
    leaders = sorted(unique_branches.values(), key=lambda item: (item.objective, _branch_id(item)))[:
        max(config.retained_branches * 3, config.retained_branches)
    ]
    accepted: list[_MixtureBranch] = []
    receipts: list[dict[str, object]] = []
    swap_attempts = 0
    base_target = target
    for branch in leaders:
        target = (shift_targets or {}).get(branch.zero_shift_deg, base_target)
        original_groups = {_reference_group(item) for item in branch.references}
        drop_order = sorted(
            range(len(branch.references)),
            key=lambda index: (
                float(branch.scales[index]) if index < branch.scales.size else 0.0,
                branch.references[index].reference_id,
            ),
        )
        for drop_index in drop_order:
            dropped = branch.references[drop_index]
            remaining = tuple(item for index, item in enumerate(branch.references) if index != drop_index)
            remaining_evidence = tuple(
                pair for pair in branch.evidence if pair[0] != dropped.reference_id
            )
            remaining_d_scales = tuple(
                value for index, value in enumerate(branch.profile_d_spacing_scales) if index != drop_index
            )
            if remaining:
                try:
                    remaining_matrix = np.column_stack([profiles[item.reference_id] for item in remaining])
                except KeyError:
                    continue
                remaining_scales, remaining_calculated, remaining_objective = _fit(
                    remaining_matrix, target, weights
                )
            else:
                remaining_scales = np.zeros(0, dtype=float)
                remaining_calculated = np.zeros_like(target)
                remaining_objective = _objective(target, remaining_calculated, weights)
            remaining_matched = frozenset(
                index
                for _reference_id, reflections in remaining_evidence
                for reflection in reflections
                for index in reflection.peak_indices
            )
            remaining_branch = _MixtureBranch(
                references=remaining,
                matched_peak_indices=remaining_matched,
                evidence=remaining_evidence,
                scales=remaining_scales,
                profile_d_spacing_scales=remaining_d_scales,
                calculated=remaining_calculated,
                objective=remaining_objective,
                stopping_reason="phase_swap_baseline",
                zero_shift_deg=branch.zero_shift_deg,
            )
            explained = _branch_explained_peak_indices(
                remaining_branch,
                peaks,
                radiation,
                tolerance_deg,
                config,
            )
            for candidate in candidates:
                if attempts >= config.max_fit_attempts or swap_attempts >= swap_budget:
                    return accepted, attempts, swap_attempts, receipts
                candidate_group = _reference_group(candidate)
                if candidate_group in original_groups or candidate.reference_id in {item.reference_id for item in remaining}:
                    continue
                if any(_same_material(candidate, item, radiation, tolerance_deg) for item in remaining):
                    continue
                if candidate.reference_id not in profiles or candidate.reference_id not in evidence:
                    continue
                available = tuple(
                    _ReflectionEvidence(
                        line_index=reflection.line_index,
                        peak_indices=tuple(index for index in reflection.peak_indices if index not in explained),
                        label=reflection.label,
                    )
                    for reflection in evidence[candidate.reference_id]
                    if any(index not in explained for index in reflection.peak_indices)
                )
                if len(available) < config.min_independent_evidence:
                    continue
                proposed = remaining + (candidate,)
                try:
                    matrix = np.column_stack([profiles[item.reference_id] for item in proposed])
                except KeyError:
                    continue
                attempts += 1
                swap_attempts += 1
                scales, calculated, objective = _fit(matrix, target, weights)
                improvement = (branch.objective - objective) / max(branch.objective, 1e-12)
                active_threshold = (
                    float(np.max(scales)) * config.inactive_scale_relative_tolerance
                    if scales.size
                    else 0.0
                )
                candidate_active = bool(scales.size and scales[-1] > active_threshold)
                accepted_swap = (
                    candidate_active
                    and improvement >= config.min_objective_improvement
                    and _branch_id_from_references(proposed) not in known_ids
                )
                receipts.append(
                    {
                        "from_hypothesis_id": _branch_id(branch),
                        "dropped_reference_id": dropped.reference_id,
                        "added_reference_id": candidate.reference_id,
                        "objective_before": branch.objective,
                        "objective_after": objective,
                        "relative_improvement": improvement,
                        "candidate_scale": float(scales[-1]) if scales.size else 0.0,
                        "status": "accepted" if accepted_swap else "rejected",
                        "rejection_reason": (
                            None
                            if accepted_swap
                            else "inactive_or_non_improving_replacement"
                            if candidate_active is False or improvement < config.min_objective_improvement
                            else "duplicate_phase_set"
                        ),
                    }
                )
                if not accepted_swap:
                    continue
                known_id = _branch_id_from_references(proposed)
                known_ids.add(known_id)
                matched = frozenset(
                    index
                    for _reference_id, reflections in (*remaining_evidence, (candidate.reference_id, available))
                    for reflection in reflections
                    for index in reflection.peak_indices
                )
                accepted.append(
                    _MixtureBranch(
                        references=proposed,
                        matched_peak_indices=matched,
                        evidence=remaining_evidence + ((candidate.reference_id, available),),
                        scales=scales,
                        profile_d_spacing_scales=remaining_d_scales + (profile_scales[candidate.reference_id],),
                        calculated=calculated,
                        objective=objective,
                        stopping_reason="phase_swap_recovered",
                        zero_shift_deg=branch.zero_shift_deg,
                    )
                )
    return accepted, attempts, swap_attempts, receipts


def _branch_id_from_references(references: Iterable[ReferencePhase]) -> str:
    return "+".join(sorted(reference.reference_id for reference in references))


def _unassigned_detected_peaks(
    peaks: tuple[Peak, ...],
    branch: _MixtureBranch,
    config: MixtureSettings,
) -> tuple[Peak, ...]:
    """Return detected peaks not yet assigned to an active phase in a branch."""

    active_indices = _active_component_indices(branch, config)
    active_reference_ids = {branch.references[index].reference_id for index in active_indices}
    assigned_indices = {
        peak_index
        for reference_id, reflections in branch.evidence
        if reference_id in active_reference_ids
        for reflection in reflections
        for peak_index in reflection.peak_indices
    }
    return tuple(
        peak
        for index, peak in sorted(
            enumerate(peaks),
            key=lambda item: (-max(float(item[1].intensity), 0.0), float(item[1].position_deg), item[0]),
        )
        if index not in assigned_indices
    )


def _branch_explained_peak_indices(
    branch: _MixtureBranch,
    peaks: tuple[Peak, ...],
    radiation: Radiation,
    tolerance_deg: float,
    config: MixtureSettings,
) -> frozenset[int]:
    """Identify peaks already inside a branch's assigned reflection envelopes.

    A resolved Kα doublet can produce two observed lobes for one parent
    reflection. Small CIF or profile shifts may lead one phase to claim only
    one lobe while another phase claims the partner. Treat any detected peak
    within an assigned reflection's spectral-component tolerance window as
    explained, even when the first phase did not select that peak as its
    nearest match. This keeps a partner lobe from becoming independent
    evidence for an additional phase.
    """

    active_indices = _active_component_indices(branch, config)
    active_reference_ids = {
        branch.references[index].reference_id
        for index in active_indices
        if index < len(branch.references)
    }
    explained: set[int] = set()
    references = {reference.reference_id: reference for reference in branch.references}
    spectral_components = radiation_spectral_components(radiation)
    for reference_id, reflections in branch.evidence:
        if reference_id not in active_reference_ids:
            continue
        reference = references.get(reference_id)
        if reference is None:
            continue
        for reflection in reflections:
            # Seed with only the retained evidence from active components.
            # An inactive component's old assignments must not suppress a
            # later phase during residual expansion.
            explained.update(reflection.peak_indices)
            if not 0 <= reflection.line_index < len(reference.lines):
                continue
            line = reference.lines[reflection.line_index]
            for wavelength, _component_weight in spectral_components:
                try:
                    expected = two_theta_from_wavelength(line.d_spacing_angstrom, wavelength)
                except ValueError:
                    continue
                explained.update(
                    index
                    for index, peak in enumerate(peaks)
                    if abs(float(peak.position_deg) - expected) <= tolerance_deg
                )
    return frozenset(explained)


def _evidence(
    reference: ReferencePhase,
    peaks: tuple[Peak, ...],
    radiation: Radiation,
    tolerance_deg: float,
) -> tuple[_ReflectionEvidence, ...]:
    used: set[int] = set()
    reflections: list[_ReflectionEvidence] = []
    spectral_components = radiation_spectral_components(radiation)
    for line_index, line in sorted(enumerate(reference.lines), key=lambda item: item[1].relative_intensity, reverse=True):
        line_peak_indices: list[int] = []
        for wavelength, _component_weight in spectral_components:
            try:
                expected = two_theta_from_wavelength(line.d_spacing_angstrom, wavelength)
            except ValueError:
                continue
            options = [(abs(peak.position_deg - expected), index) for index, peak in enumerate(peaks) if index not in used and abs(peak.position_deg - expected) <= tolerance_deg]
            if options:
                _, index = min(options)
                used.add(index)
                line_peak_indices.append(index)
        if line_peak_indices:
            reflections.append(
                _ReflectionEvidence(
                    line_index=line_index,
                    peak_indices=tuple(line_peak_indices),
                    label=line.hkl or f"line-{line_index + 1}",
                )
            )
    return tuple(reflections)


def _component(
    reference: ReferencePhase,
    scale: float,
    profile_d_spacing_scale: float,
    evidence: tuple[_ReflectionEvidence, ...],
    independent_evidence: tuple[_ReflectionEvidence, ...],
    peaks: tuple[Peak, ...],
    radiation: Radiation,
    tolerance_deg: float,
    *,
    scan_range: tuple[float, float],
) -> MixtureComponent:
    matched_indices = tuple(
        dict.fromkeys(
            peak_index
            for reflection in evidence
            for peak_index in reflection.peak_indices
        )
    )
    independent_indices = tuple(
        dict.fromkeys(
            peak_index
            for reflection in independent_evidence
            for peak_index in reflection.peak_indices
        )
    )
    labels = tuple(dict.fromkeys(reflection.label for reflection in independent_evidence))
    missing: list[str] = []
    spectral_components = radiation_spectral_components(radiation)
    for index, line in enumerate(reference.lines):
        expected_positions: list[float] = []
        for wavelength, _component_weight in spectral_components:
            try:
                expected = two_theta_from_wavelength(line.d_spacing_angstrom, wavelength)
            except ValueError:
                continue
            if scan_range[0] <= expected <= scan_range[1]:
                expected_positions.append(expected)
        if not expected_positions:
            continue
        if not any(
            abs(peaks[peak_index].position_deg - expected) <= tolerance_deg
            for peak_index in matched_indices
            for expected in expected_positions
        ):
            missing.append(line.hkl or f"line-{index + 1}")
    return MixtureComponent(
        reference_id=reference.reference_id,
        name=reference.name,
        formula=reference.formula,
        screening_scale=max(0.0, scale),
        duplicate_group_id=reference.duplicate_group_id,
        equivalence_group_id=reference.equivalence_group_id,
        parent_family_group_id=reference.parent_family_group_id,
        matched_peak_indices=tuple(matched_indices),
        independent_evidence_peak_indices=independent_indices,
        evidence_groups=labels,
        missing_expected_lines=tuple(missing),
        profile_d_spacing_scale=profile_d_spacing_scale,
        space_group=reference.space_group,
    )


__all__ = [
    "MIXTURE_ALGORITHM_VERSION",
    "MixtureComponent",
    "MixtureComponentTrace",
    "MixtureHypothesis",
    "MixtureResidualTrace",
    "MixtureResult",
    "MixtureSettings",
    "render_phase_profile",
    "select_mixture_hypotheses",
]
