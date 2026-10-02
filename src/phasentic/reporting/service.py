from __future__ import annotations

from dataclasses import replace
import copy
import time
import hashlib
import inspect
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np

from phasentic.acquisition.calibration import (
    get_calibration_standard,
    validate_calibration_provenance,
)
from phasentic.domain.models import (
    AnalysisReport,
    AnalysisSettings,
    CandidateMatch,
    CalibrationStatus,
    InputSummary,
    KAlphaTreatment,
    Peak,
    QualityReport,
    ReferencePhase,
)
from phasentic.domain.formula import passes_element_filter
from phasentic.domain.radiation import Radiation, get_radiation, radiation_spectral_components
from phasentic.domain.validation import validate_settings
from phasentic.importers import import_pattern
from phasentic.preprocessing.pipeline import (
    detect_peaks,
    detect_peaks_noise_aware,
    estimate_background_deg,
    estimate_width_model,
    preprocess,
)
from phasentic.references.factory import open_reference_store
from phasentic.references.equivalence import (
    RuntimeEquivalenceSettings,
    resolve_on_demand_equivalences,
)
from phasentic.search.displacement import correct_angles, estimate_sample_displacement
from phasentic.search.matcher import (
    candidate_ranking_profile,
    candidate_retention_profile,
    match_references,
    select_fitter_shortlist,
)
from phasentic.search.mixtures import (
    MixtureComponentTrace,
    MixtureResidualTrace,
    MixtureResult,
    MixtureSettings,
    select_mixture_hypotheses,
)
from phasentic.search.qualx_search import (
    QUALX_SEARCH_VERSION,
    QualxSearchConfig,
    rerank_candidate_matches,
    search_candidates,
)

POWDER_TWO_THETA_RANGE_DEG = (0.0, 120.0)


ALGORITHM_VERSION = "research-alpha-0.9-noise-aware-peaks-displacement-element-filter"
QUALX_RANKING_INFLUENCE = 0.20


def _analysis_intensity_policy(store: object, radiation: Radiation) -> dict[str, object]:
    """Return the locked intensity contract for the selected radiation.

    Non-Cu intensity comparison is permanently outside the supported alpha
    contract.  Enforce that at the reporting boundary for every reference
    store, including demo and legacy stores that do not expose a policy method.
    """

    if radiation.key != "cu_ka":
        return {
            "mode": "position_only",
            "intensity_scoring": False,
            "intensity_comparison": "unsupported",
            "warning": "POWCOD_INTENSITY_UNSUPPORTED",
            "radiation": radiation.key,
        }
    provider = getattr(store, "intensity_policy", None)
    raw = provider(radiation) if callable(provider) else None
    policy = dict(raw) if isinstance(raw, dict) else {}
    policy.setdefault("mode", "native_calculated")
    policy.setdefault("intensity_scoring", True)
    policy.setdefault("intensity_comparison", "supported")
    policy.setdefault("warning", None)
    policy["radiation"] = radiation.key
    return policy


def _qualx_rank(
    peaks: tuple[Peak, ...],
    references: tuple[ReferencePhase, ...],
    matches: tuple[CandidateMatch, ...],
    radiation: Radiation,
    tolerance_deg: float,
    scan_range_deg: tuple[float, float],
) -> tuple[tuple[CandidateMatch, ...], dict[str, object]]:
    """Apply advisory strongest-line screening and return bounded provenance."""

    config = QualxSearchConfig(
        tolerance_deg=tolerance_deg,
        strongest_reference_line_count=3,
        prefilter_mode="any",
    )
    result = search_candidates(
        peaks,
        references,
        radiation,
        config=config,
        scan_range_deg=scan_range_deg,
    )
    ranked = rerank_candidate_matches(matches, result, influence_weight=QUALX_RANKING_INFLUENCE)
    top_assessments = tuple(result.ranked_candidates[:25])
    return ranked, {
        "algorithm_version": QUALX_SEARCH_VERSION,
        "settings": config.to_dict(radiation),
        "ranking_influence_weight": QUALX_RANKING_INFLUENCE,
        "diagnostics": result.diagnostics.to_dict(),
        "prefilter_semantics": "advisory_only; failed candidates are retained and may still be fitted",
        "top_candidates": [
            {
                "reference_id": item.reference_id,
                "passed_prefilter": item.passed_prefilter,
                "rejection_reason": item.rejection_reason,
                "strongest_reference_lines_matched": item.strongest_reference_lines_matched,
                "strongest_reference_lines_considered": item.strongest_reference_lines_considered,
                "figure_of_merit": item.figure_of_merit.to_dict(),
            }
            for item in top_assessments
        ],
    }


def _provider_accepts_keyword(provider: object, keyword: str) -> bool:
    if not callable(provider):
        return False
    try:
        parameters = inspect.signature(provider).parameters
    except (TypeError, ValueError):
        return False
    return keyword in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


def _references_by_id_first_wins(references: Iterable[ReferencePhase]) -> dict[str, ReferencePhase]:
    """Index references without changing the first record associated with an ID."""

    by_id: dict[str, ReferencePhase] = {}
    for reference in references:
        by_id.setdefault(reference.reference_id, reference)
    return by_id


def _query_reference_candidates(
    provider: object,
    peaks: Iterable,
    radiation: Radiation,
    tolerance_deg: float,
    *,
    max_candidates: int,
    retrieval_mode: str,
    allowed_elements: tuple[str, ...] | None = None,
    d_relative_tolerance: float = 0.0,
    oxidizing: bool = False,
) -> tuple[ReferencePhase, ...]:
    """Query an indexed store with a bounded pool when it supports it.

    Signature inspection keeps older third-party and test stores compatible
    without catching and masking a real ``TypeError`` raised inside a provider.
    The caller records whether the selected provider applied these bounds.
    """

    callable_provider = provider
    if not callable(callable_provider):
        return ()
    try:
        parameters = inspect.signature(callable_provider).parameters
    except (TypeError, ValueError):
        parameters = {}
    kwargs: dict[str, object] = {}
    if "max_candidates" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    ):
        kwargs["max_candidates"] = max_candidates
    if "retrieval_mode" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    ):
        kwargs["retrieval_mode"] = retrieval_mode
    if allowed_elements is not None and "allowed_elements" in parameters:
        kwargs["allowed_elements"] = allowed_elements
    if d_relative_tolerance > 0 and "d_relative_tolerance" in parameters:
        kwargs["d_relative_tolerance"] = d_relative_tolerance
    fetched = tuple(callable_provider(peaks, radiation, tolerance_deg, **kwargs))
    if allowed_elements is None:
        return fetched
    # Generic post-filter so every store honours the constraint, including
    # stores that cannot filter inside their own index.
    return _filter_by_elements(fetched, allowed_elements, oxidizing=oxidizing)


def _scaled_reference(reference: ReferencePhase, scale: float) -> ReferencePhase:
    """Apply the matcher's per-phase d-spacing scale (screening adjustment)."""

    if scale == 1.0:
        return reference
    return replace(
        reference,
        lines=tuple(replace(line, d_spacing_angstrom=line.d_spacing_angstrom * scale) for line in reference.lines),
    )


def _filter_by_elements(
    phases: Iterable[ReferencePhase], allowed_elements: tuple[str, ...], *, oxidizing: bool = False
) -> tuple[ReferencePhase, ...]:
    allowed = frozenset(allowed_elements)
    return tuple(phase for phase in phases if passes_element_filter(phase.formula, allowed, oxidizing=oxidizing))


def _fitter_group_count(references: Iterable[ReferencePhase]) -> int:
    """Count unique phase groups using the fitter's duplicate policy."""

    return len(
        {
            reference.equivalence_group_id
            or reference.duplicate_group_id
            or reference.reference_id
            for reference in references
        }
    )


def _resolve_radiation_spectrum(
    selected: Radiation,
    source_metadata: object,
    treatment: KAlphaTreatment,
) -> tuple[Radiation, dict[str, object]]:
    """Resolve a selected anode plus trustworthy source wavelength metadata."""

    if not isinstance(treatment, KAlphaTreatment):
        raise ValueError("K-alpha treatment is invalid")
    source = source_metadata if isinstance(source_metadata, dict) else {}
    source_anode = source.get("anode_material")
    selected_anode = selected.key.split("_", 1)[0].casefold()
    if isinstance(source_anode, str) and source_anode.strip():
        if source_anode.strip().casefold() != selected_anode:
            raise ValueError(
                f"XRDML anode '{source_anode.strip()}' does not match selected radiation '{selected.label}'"
            )

    use_source = treatment in {KAlphaTreatment.AUTO_FROM_SOURCE, KAlphaTreatment.DOUBLETS_RESOLVED}
    source_ka1 = source.get("ka1_angstrom")
    source_ka2 = source.get("ka2_angstrom")
    source_ratio = source.get("ka2_to_ka1_intensity_ratio")
    if use_source and source_ka1 is not None and source_ka2 is not None and source_ratio is not None:
        try:
            ka1, ka2, ratio = float(source_ka1), float(source_ka2), float(source_ratio)
        except (TypeError, ValueError) as exc:
            raise ValueError("XRDML source radiation metadata is invalid") from exc
        if (
            not np.isfinite(ka1)
            or not np.isfinite(ka2)
            or not np.isfinite(ratio)
            or ka1 <= 0.0
            or ka2 <= 0.0
            or not 0.0 <= ratio <= 1.0
        ):
            raise ValueError("XRDML source radiation metadata is outside supported bounds")
        resolved = Radiation(
            key=selected.key,
            label=selected.label,
            wavelength_angstrom=ka1,
            ka1_angstrom=ka1,
            ka2_angstrom=ka2,
            ka2_to_ka1_intensity_ratio=ratio,
        )
        origin = "xrdml_source_metadata"
    elif treatment is KAlphaTreatment.DOUBLETS_RESOLVED:
        ka1 = selected.ka1_angstrom or selected.wavelength_angstrom
        ka2 = selected.ka2_angstrom or selected.wavelength_angstrom
        resolved = Radiation(
            key=selected.key,
            label=selected.label,
            wavelength_angstrom=ka1,
            ka1_angstrom=ka1,
            ka2_angstrom=ka2,
            ka2_to_ka1_intensity_ratio=0.5 if ka1 != ka2 else 0.0,
        )
        origin = "selected_radiation_preset_assumption"
    else:
        resolved = selected
        origin = "single_effective_selected_preset"

    components = radiation_spectral_components(resolved)
    return resolved, {
        "treatment": "doublets_resolved" if len(components) > 1 else "single_effective",
        "origin": origin,
        "components": [
            {"wavelength_angstrom": wavelength, "relative_weight": weight}
            for wavelength, weight in components
        ],
        "source_anode_material": source_anode,
        "declared_intensity_ratio": source_ratio,
    }


class _StageTimer:
    """Wall-clock stage durations for provenance (diagnostic, not reproducible)."""

    def __init__(self) -> None:
        self._started = time.perf_counter()
        self._last = self._started
        self._stages: dict[str, float] = {}
        self._counters: dict[str, int] = {}

    def mark(self, stage: str) -> None:
        now = time.perf_counter()
        self._stages[stage] = self._stages.get(stage, 0.0) + (now - self._last)
        self._last = now

    def add(self, stage: str, seconds: float) -> None:
        self._stages[stage] = self._stages.get(stage, 0.0) + float(seconds)

    def count(self, name: str) -> None:
        self._counters[name] = self._counters.get(name, 0) + 1

    def receipt(self) -> dict[str, object]:
        return {
            "schema": "stage-timings-v1",
            "reproducible": False,
            "stage_seconds": {key: round(value, 4) for key, value in self._stages.items()},
            "counters": dict(self._counters),
            "elapsed_seconds_at_report": round(time.perf_counter() - self._started, 4),
        }


def analyze_file(
    path: str | Path,
    settings: AnalysisSettings | None = None,
    *,
    powcod_path: str | Path | None = None,
    powcod_cache_path: str | Path | None = None,
    powcod_equivalence_path: str | Path | None = None,
    reference_store: object | None = None,
    original_filename: str | None = None,
) -> AnalysisReport:
    resolved_settings = validate_settings(settings or AnalysisSettings())
    stage_timer = _StageTimer()
    input_path = Path(path)
    file_hash_before = _sha256(input_path)
    pattern = import_pattern(input_path, radiation=resolved_settings.radiation)
    file_hash = _sha256(input_path)
    if file_hash != file_hash_before:
        raise OSError("Input file changed while it was being analyzed")
    if original_filename:
        pattern = replace(pattern, source_name=Path(original_filename).name)
    radiation = get_radiation(resolved_settings.radiation)
    raw_angles = np.asarray(pattern.angles_deg, dtype=float)
    intensities = np.asarray(pattern.intensities, dtype=float)
    calibration = resolved_settings.calibration
    requested_calibration_status = (
        CalibrationStatus(calibration.status)
        if calibration is not None
        else CalibrationStatus.UNVERIFIED
    )
    calibration_status = requested_calibration_status
    if calibration is not None and requested_calibration_status is CalibrationStatus.PASSED:
        try:
            validate_calibration_provenance(calibration)
        except ValueError:
            calibration_status = CalibrationStatus.UNVERIFIED
    configured_treatment = (
        resolved_settings.instrument.k_alpha_treatment
        if resolved_settings.instrument is not None
        else KAlphaTreatment.AUTO_FROM_SOURCE
    )
    effective_radiation, radiation_spectrum = _resolve_radiation_spectrum(
        radiation,
        pattern.metadata.get("source_radiation"),
        configured_treatment,
    )
    angles = raw_angles.copy()
    if calibration is not None and calibration_status == CalibrationStatus.PASSED:
        angles = angles - calibration.zero_shift_deg
        effective_radiation = Radiation(
            key=radiation.key,
            label=radiation.label,
            wavelength_angstrom=effective_radiation.wavelength_angstrom * calibration.wavelength_scale,
            ka1_angstrom=(
                effective_radiation.ka1_angstrom * calibration.wavelength_scale
                if effective_radiation.ka1_angstrom is not None
                else None
            ),
            ka2_angstrom=(
                effective_radiation.ka2_angstrom * calibration.wavelength_scale
                if effective_radiation.ka2_angstrom is not None
                else None
            ),
            ka2_to_ka1_intensity_ratio=effective_radiation.ka2_to_ka1_intensity_ratio,
        )
        components = radiation_spectral_components(effective_radiation)
        radiation_spectrum = {
            **radiation_spectrum,
            "components": [
                {"wavelength_angstrom": wavelength, "relative_weight": weight}
                for wavelength, weight in components
            ],
            "calibration_wavelength_scale_applied": calibration.wavelength_scale,
        }
    trace_angles = raw_angles.copy()
    trace_intensities = intensities.copy()
    full_trace_angles = raw_angles.copy()
    full_trace_corrected_angles = angles.copy()
    full_trace_intensities = intensities.copy()
    range_warnings: list[str] = []
    configured_maximum_angle = resolved_settings.matching_two_theta_max_deg
    maximum_reference_angle = min(
        POWDER_TWO_THETA_RANGE_DEG[1],
        configured_maximum_angle if configured_maximum_angle is not None else POWDER_TWO_THETA_RANGE_DEG[1],
    )
    range_label = (
        "the configured primary matching 2theta range"
        if configured_maximum_angle is not None
        else "the indexed 2theta range"
    )
    if np.any((angles < POWDER_TWO_THETA_RANGE_DEG[0]) | (angles > maximum_reference_angle)):
        in_reference_range = (angles >= POWDER_TWO_THETA_RANGE_DEG[0]) & (angles <= maximum_reference_angle)
        if not np.any(in_reference_range):
            raise ValueError(
                f"No measured points remain inside {range_label} 0-{maximum_reference_angle:g} degrees"
            )
        angles = angles[in_reference_range]
        intensities = intensities[in_reference_range]
        trace_angles = trace_angles[in_reference_range]
        trace_intensities = trace_intensities[in_reference_range]
        range_warnings.append(
            f"Measured scan was cropped to {range_label} 0-{maximum_reference_angle:g} degrees; "
            "points outside the range were excluded from matching."
        )
    peak_detection_receipt: dict[str, object]
    if resolved_settings.peak_detection == "noise_aware":
        background = estimate_background_deg(
            angles, intensities, window_deg=resolved_settings.background_window_deg
        )
        processed = preprocess(angles, intensities, background=background)
        peaks, peak_detection_receipt = detect_peaks_noise_aware(
            processed.angles_deg,
            processed.raw_intensities,
            processed.background,
            smoothing_window_deg=resolved_settings.peak_smoothing_window_deg,
            min_snr=resolved_settings.peak_min_snr,
            min_width_deg=resolved_settings.peak_min_width_deg,
            min_relative_prominence=resolved_settings.peak_min_relative_prominence,
            max_peaks=resolved_settings.max_peaks,
        )
        noise = peak_detection_receipt.get("median_noise_sigma")
        if isinstance(noise, float) and noise > 0:
            processed = replace(
                processed,
                signal_to_noise=float(np.max(processed.corrected_intensities)) / noise,
            )
        peak_detection_receipt["background"] = {
            "model": "rolling 20th percentile + box smoothing",
            "window_deg": resolved_settings.background_window_deg,
        }
    else:
        processed = preprocess(angles, intensities, window=resolved_settings.background_window_points)
        peaks = detect_peaks(
            processed.angles_deg,
            processed.corrected_intensities,
            prominence_fraction=resolved_settings.min_prominence_fraction,
            max_peaks=resolved_settings.max_peaks,
        )
        peak_detection_receipt = {
            "algorithm_version": "legacy-prominence-fraction",
            "min_prominence_fraction": resolved_settings.min_prominence_fraction,
            "background_window_points": resolved_settings.background_window_points,
        }
    stage_timer.mark("import_and_peak_detection")
    owns_store = reference_store is None
    store = reference_store or open_reference_store(
        resolved_settings,
        powcod_path=powcod_path,
        powcod_cache_path=powcod_cache_path,
        powcod_equivalence_path=powcod_equivalence_path,
    )
    store_provenance = (
        store.provenance()
        if callable(getattr(store, "provenance", None))
        else {
            "reference_source": "demo",
            "reference_database": "COD-derived teaching subset; complete reference database not configured",
        }
    )
    mixture = None
    residual_candidates: dict[str, ReferencePhase] = {}
    candidate_source_phases: dict[str, ReferencePhase] = {}
    candidate_query_stats: dict[str, object] = {}
    residual_query_stats: list[dict[str, object]] = []
    qualx_search_receipt: dict[str, object] = {}
    equivalence_receipt: dict[str, object] = {
        "status": "not_run",
        "method_version": RuntimeEquivalenceSettings().method_version,
        "configuration_sha256": RuntimeEquivalenceSettings().configuration_sha256,
    }
    displacement_receipt: dict[str, object] = {"status": "disabled", "displacement_deg": 0.0}
    try:
        candidate_provider = getattr(store, "iter_candidates", None)
        lookup_budget_enforced = _provider_accepts_keyword(candidate_provider, "max_candidates")
        if resolved_settings.displacement_search_max_deg > 0 and len(peaks) >= 3:
            # Estimate specimen displacement before any tolerance-based matching;
            # a systematic shift larger than the tolerance otherwise rejects the
            # true phases outright.
            probe_peaks = tuple(sorted(peaks, key=lambda peak: -peak.prominence)[:12])
            probe_tolerance = max(resolved_settings.peak_tolerance_deg, resolved_settings.displacement_search_max_deg)
            probe_candidates = (
                _query_reference_candidates(
                    candidate_provider,
                    probe_peaks,
                    effective_radiation,
                    probe_tolerance,
                    max_candidates=3000,
                    retrieval_mode="bounded_coarse",
                    allowed_elements=resolved_settings.allowed_elements,
                    oxidizing=resolved_settings.oxidizing_synthesis,
                )
                if callable(candidate_provider)
                else (
                    _filter_by_elements(tuple(store), resolved_settings.allowed_elements, oxidizing=resolved_settings.oxidizing_synthesis)
                    if resolved_settings.allowed_elements
                    else tuple(store)
                )
            )
            displacement, displacement_receipt = estimate_sample_displacement(
                peaks,
                probe_candidates,
                effective_radiation,
                (float(np.min(angles)), float(np.max(angles))),
                max_displacement_deg=resolved_settings.displacement_search_max_deg,
                tolerance_deg=resolved_settings.displacement_tolerance_deg,
                scale_tolerance=resolved_settings.lattice_scale_tolerance,
            )
            if displacement:
                peaks = tuple(
                    replace(peak, position_deg=float(correct_angles(np.array([peak.position_deg]), displacement)[0]))
                    for peak in peaks
                )
                angles = correct_angles(angles, displacement)
                processed = replace(processed, angles_deg=correct_angles(processed.angles_deg, displacement))
        stage_timer.mark("store_open_and_displacement")
        retrieved_candidate_phases = tuple(
            _query_reference_candidates(
                candidate_provider,
                peaks,
                effective_radiation,
                resolved_settings.peak_tolerance_deg,
                max_candidates=resolved_settings.effective_candidate_lookup_budget,
                retrieval_mode=resolved_settings.candidate_retrieval_mode,
                allowed_elements=resolved_settings.allowed_elements,
                    oxidizing=resolved_settings.oxidizing_synthesis,
                d_relative_tolerance=resolved_settings.lattice_scale_tolerance,
            )
            if callable(candidate_provider)
            else (
                _filter_by_elements(tuple(store), resolved_settings.allowed_elements, oxidizing=resolved_settings.oxidizing_synthesis)
                if resolved_settings.allowed_elements
                else tuple(store)
            )
        )
        if not lookup_budget_enforced and len(retrieved_candidate_phases) > resolved_settings.effective_candidate_lookup_budget:
            range_warnings.append(
                "REFERENCE_LOOKUP_BUDGET_UNENFORCED: the selected reference provider does not accept a lookup limit; "
                "all returned candidates were ranked before the fitter pool was reduced."
            )
        candidate_phases = retrieved_candidate_phases
        stats_provider = getattr(store, "query_stats", None)
        if callable(stats_provider):
            raw_stats = stats_provider()
            if isinstance(raw_stats, dict):
                candidate_query_stats = dict(raw_stats)
                candidate_query_stats["lookup_budget"] = resolved_settings.effective_candidate_lookup_budget
                candidate_query_stats["lookup_budget_enforced"] = lookup_budget_enforced
                candidate_query_stats["fitter_candidate_budget"] = resolved_settings.candidate_pool
                if bool(candidate_query_stats.get("truncated")) and candidate_query_stats.get("retrieval_mode") == "exhaustive_exact":
                    range_warnings.append(
                        "POW_COD exhaustive exact retrieval scanned the full cached phase universe, "
                        "then truncated the downstream candidate pool; reported hypotheses are bounded "
                        "screening candidates, not an exhaustive result set."
                    )
                elif bool(candidate_query_stats.get("truncated")):
                    range_warnings.append(
                        "POW_COD candidate pool was truncated after coarse d-bin retrieval; "
                        "reported hypotheses are bounded screening candidates, not an exhaustive search."
                    )
        intensity_policy = _analysis_intensity_policy(store, effective_radiation)
        if intensity_policy.get("warning"):
            range_warnings.append(str(intensity_policy["warning"]))
        # Score the broad lookup result before reducing it to the more
        # expensive mixture-fitter pool. The returned matches are sorted by
        # score, so fitter seeds are selected by measured evidence rather than
        # by the reference store's coarse retrieval order.
        stage_timer.mark("candidate_lookup")
        ranked_candidates = match_references(
            peaks,
            candidate_phases,
            effective_radiation,
            tolerance_deg=resolved_settings.peak_tolerance_deg,
            limit=max(len(candidate_phases), resolved_settings.candidate_pool, resolved_settings.reference_limit),
            scan_range_deg=(float(np.min(angles)), float(np.max(angles))),
            use_intensity=bool(intensity_policy.get("intensity_scoring", True)),
            collapse_groups=False,
            d_scale_tolerance=resolved_settings.lattice_scale_tolerance,
        )
        ranked_candidates, qualx_search_receipt = _qualx_rank(
            peaks,
            candidate_phases,
            ranked_candidates,
            effective_radiation,
            resolved_settings.peak_tolerance_deg,
            (float(np.min(angles)), float(np.max(angles))),
        )
        exact_line_verified_count = sum(match.matched_peaks > 0 for match in ranked_candidates)
        ranked_with_evidence = tuple(match for match in ranked_candidates if match.matched_peaks > 0)
        if not ranked_with_evidence:
            ranked_with_evidence = ranked_candidates
        raw_candidates, fitter_shortlist_receipt = select_fitter_shortlist(
            ranked_with_evidence,
            peaks,
            limit=resolved_settings.candidate_pool,
        )
        candidate_by_id = _references_by_id_first_wins(retrieved_candidate_phases)
        candidate_phases = tuple(
            _scaled_reference(candidate_by_id[match.reference_id], match.d_spacing_scale)
            for match in raw_candidates
            if match.reference_id in candidate_by_id
        )
        candidate_source_phases.update({phase.reference_id: phase for phase in candidate_phases})
        stage_timer.mark("matching_and_qualx")
        resolved_equivalence = resolve_on_demand_equivalences(
            candidate_phases,
            raw_candidates,
            effective_radiation,
            settings=RuntimeEquivalenceSettings(line_tolerance_deg=resolved_settings.peak_tolerance_deg),
        )
        candidate_phases = resolved_equivalence.references
        candidates = resolved_equivalence.matches[: resolved_settings.reference_limit]
        equivalence_receipt = dict(resolved_equivalence.receipt)
        stage_timer.mark("equivalence")
        candidate_query_stats.update(
            {
                "lookup_budget": resolved_settings.effective_candidate_lookup_budget,
                "lookup_budget_enforced": lookup_budget_enforced,
                "lookup_returned_candidate_count": len(retrieved_candidate_phases),
                "exact_line_verified_count": exact_line_verified_count,
                "fitter_candidate_budget": resolved_settings.candidate_pool,
                "fitter_input_reference_count": len(raw_candidates),
                "fitter_candidate_count": _fitter_group_count(resolved_equivalence.references),
                "fitter_shortlist": fitter_shortlist_receipt,
                "residual_queries": residual_query_stats,
            }
        )
        width_model: tuple[float, float] | None = None
        width_receipt: dict[str, object] = {"status": "fixed", "profile_width_deg": resolved_settings.profile_width_deg}
        if resolved_settings.profile_width_mode == "estimated":
            components = radiation_spectral_components(effective_radiation)

            def _doublet_separation(two_theta: float) -> float:
                if len(components) < 2:
                    return 0.0
                theta = math.radians(two_theta) / 2.0
                ratio = components[1][0] / components[0][0] - 1.0
                return math.degrees(2.0 * math.tan(theta) * ratio)

            width_model, width_receipt = estimate_width_model(
                peaks, doublet_separation=_doublet_separation if len(components) > 1 else None
            )
            if width_model is None:
                width_receipt["fallback_profile_width_deg"] = resolved_settings.profile_width_deg
        candidate_query_stats["profile_width"] = width_receipt
        if resolved_settings.analysis_mode == "mixture":
            def _mixture_inputs(values: Iterable[ReferencePhase]) -> tuple[ReferencePhase, ...]:
                frozen = tuple(values)
                if bool(intensity_policy.get("intensity_scoring", True)):
                    return frozen
                return tuple(
                    replace(
                        reference,
                        lines=tuple(replace(line, relative_intensity=1.0) for line in reference.lines),
                    )
                    for reference in frozen
                )

            mixture_inputs = _mixture_inputs(candidate_phases)
            residual_candidate_provider = None
            if resolved_settings.residual_candidate_queries:
                if callable(candidate_provider):
                    # Different branches often leave exactly the same detected
                    # peaks unassigned. The query is a pure function of those
                    # peaks (store, settings and scan are fixed here), so its
                    # result is reused; the provenance entry is still appended
                    # once per request, exactly as for a fresh query.
                    residual_query_memo: dict[tuple, tuple[object, dict[str, object]]] = {}

                    def _query_residual_candidates(residual_peaks):
                        memo_key = tuple(
                            (peak.position_deg, peak.intensity, peak.prominence, peak.width_deg)
                            for peak in residual_peaks
                        )
                        cached = residual_query_memo.get(memo_key)
                        if cached is not None:
                            result, stats_entry = cached
                            stage_timer.count("residual_query_cache_hits")
                            residual_query_stats.append(copy.deepcopy(stats_entry))
                            return result
                        residual_started = time.perf_counter()
                        result = _query_residual_candidates_uncached(residual_peaks)
                        stage_timer.add("residual_queries_within_mixture", time.perf_counter() - residual_started)
                        residual_query_memo[memo_key] = (result, copy.deepcopy(residual_query_stats[-1]))
                        return result

                    def _query_residual_candidates_uncached(residual_peaks):
                        fetched = _query_reference_candidates(
                            candidate_provider,
                            residual_peaks,
                            effective_radiation,
                            resolved_settings.peak_tolerance_deg,
                            max_candidates=resolved_settings.effective_candidate_lookup_budget,
                            retrieval_mode=resolved_settings.candidate_retrieval_mode,
                            allowed_elements=resolved_settings.allowed_elements,
                    oxidizing=resolved_settings.oxidizing_synthesis,
                            d_relative_tolerance=resolved_settings.lattice_scale_tolerance,
                        )
                        ranked_residual_matches = match_references(
                            residual_peaks,
                            fetched,
                            effective_radiation,
                            tolerance_deg=resolved_settings.peak_tolerance_deg,
                            limit=max(len(fetched), resolved_settings.candidate_pool, resolved_settings.reference_limit),
                            scan_range_deg=(float(np.min(angles)), float(np.max(angles))),
                            use_intensity=bool(intensity_policy.get("intensity_scoring", True)),
                            collapse_groups=False,
                            d_scale_tolerance=resolved_settings.lattice_scale_tolerance,
                        )
                        ranked_residual_matches, residual_qualx_receipt = _qualx_rank(
                            residual_peaks,
                            tuple(fetched),
                            ranked_residual_matches,
                            effective_radiation,
                            resolved_settings.peak_tolerance_deg,
                            (float(np.min(angles)), float(np.max(angles))),
                        )
                        exact_residual_count = sum(
                            match.matched_peaks > 0 for match in ranked_residual_matches
                        )
                        residual_ranked_with_evidence = tuple(
                            match for match in ranked_residual_matches if match.matched_peaks > 0
                        )
                        if not residual_ranked_with_evidence:
                            residual_ranked_with_evidence = ranked_residual_matches
                        residual_matches, residual_shortlist_receipt = select_fitter_shortlist(
                            residual_ranked_with_evidence,
                            residual_peaks,
                            limit=resolved_settings.candidate_pool,
                        )
                        fetched_by_id = _references_by_id_first_wins(fetched)
                        fetched_shortlist = tuple(
                            _scaled_reference(fetched_by_id[match.reference_id], match.d_spacing_scale)
                            for match in residual_matches
                            if match.reference_id in fetched_by_id
                        )
                        candidate_source_phases.update(
                            {phase.reference_id: phase for phase in fetched_shortlist}
                        )
                        resolved = resolve_on_demand_equivalences(
                            fetched_shortlist,
                            residual_matches,
                            effective_radiation,
                            settings=RuntimeEquivalenceSettings(line_tolerance_deg=resolved_settings.peak_tolerance_deg),
                        )
                        raw_stats = stats_provider() if callable(stats_provider) else {}
                        residual_query_stats.append(
                            {
                                "lookup_budget": resolved_settings.effective_candidate_lookup_budget,
                                "lookup_budget_enforced": lookup_budget_enforced,
                                "lookup_returned_candidate_count": len(fetched),
                                "exact_line_verified_count": exact_residual_count,
                                "fitter_candidate_budget": resolved_settings.candidate_pool,
                                "fitter_input_reference_count": len(fetched_shortlist),
                                "fitter_candidate_count": _fitter_group_count(resolved.references),
                                "fitter_shortlist": residual_shortlist_receipt,
                                "qualx_search": {
                                    "algorithm_version": residual_qualx_receipt["algorithm_version"],
                                    "diagnostics": residual_qualx_receipt["diagnostics"],
                                    "ranking_influence_weight": residual_qualx_receipt[
                                        "ranking_influence_weight"
                                    ],
                                },
                                "store_query_stats": dict(raw_stats) if isinstance(raw_stats, dict) else {},
                            }
                        )
                        residual_candidates.update({reference.reference_id: reference for reference in resolved.references})
                        return _mixture_inputs(resolved.references)

                    residual_candidate_provider = _query_residual_candidates
                else:
                    # Stores without an indexed query API still participate
                    # deterministically by returning their immutable universe.
                    def _query_residual_universe(residual_peaks):
                        fetched = (
                            _filter_by_elements(tuple(store), resolved_settings.allowed_elements, oxidizing=resolved_settings.oxidizing_synthesis)
                            if resolved_settings.allowed_elements
                            else tuple(store)
                        )
                        ranked_residual_matches = match_references(
                            residual_peaks,
                            fetched,
                            effective_radiation,
                            tolerance_deg=resolved_settings.peak_tolerance_deg,
                            limit=max(len(fetched), resolved_settings.candidate_pool, resolved_settings.reference_limit),
                            scan_range_deg=(float(np.min(angles)), float(np.max(angles))),
                            use_intensity=bool(intensity_policy.get("intensity_scoring", True)),
                            collapse_groups=False,
                            d_scale_tolerance=resolved_settings.lattice_scale_tolerance,
                        )
                        exact_residual_count = sum(
                            match.matched_peaks > 0 for match in ranked_residual_matches
                        )
                        residual_ranked_with_evidence = tuple(
                            match for match in ranked_residual_matches if match.matched_peaks > 0
                        )
                        if not residual_ranked_with_evidence:
                            residual_ranked_with_evidence = ranked_residual_matches
                        residual_matches, residual_shortlist_receipt = select_fitter_shortlist(
                            residual_ranked_with_evidence,
                            residual_peaks,
                            limit=resolved_settings.candidate_pool,
                        )
                        fetched_by_id = _references_by_id_first_wins(fetched)
                        fetched_shortlist = tuple(
                            _scaled_reference(fetched_by_id[match.reference_id], match.d_spacing_scale)
                            for match in residual_matches
                            if match.reference_id in fetched_by_id
                        )
                        candidate_source_phases.update(
                            {phase.reference_id: phase for phase in fetched_shortlist}
                        )
                        resolved = resolve_on_demand_equivalences(
                            fetched_shortlist,
                            residual_matches,
                            effective_radiation,
                            settings=RuntimeEquivalenceSettings(line_tolerance_deg=resolved_settings.peak_tolerance_deg),
                        )
                        raw_stats = stats_provider() if callable(stats_provider) else {}
                        residual_query_stats.append(
                            {
                                "lookup_budget": resolved_settings.effective_candidate_lookup_budget,
                                "lookup_budget_enforced": False,
                                "lookup_returned_candidate_count": len(fetched),
                                "exact_line_verified_count": exact_residual_count,
                                "fitter_candidate_budget": resolved_settings.candidate_pool,
                                "fitter_input_reference_count": len(fetched_shortlist),
                                "fitter_candidate_count": _fitter_group_count(resolved.references),
                                "fitter_shortlist": residual_shortlist_receipt,
                                "store_query_stats": dict(raw_stats) if isinstance(raw_stats, dict) else {},
                            }
                        )
                        residual_candidates.update({reference.reference_id: reference for reference in resolved.references})
                        return _mixture_inputs(resolved.references)

                    residual_candidate_provider = _query_residual_universe
            mixture = select_mixture_hypotheses(
                processed.angles_deg,
                processed.raw_intensities,
                peaks,
                mixture_inputs,
                effective_radiation,
                tolerance_deg=resolved_settings.peak_tolerance_deg,
                settings=MixtureSettings(
                    max_phases=resolved_settings.max_phases,
                    candidate_pool=resolved_settings.candidate_pool,
                    retained_branches=resolved_settings.retained_branches,
                    min_independent_evidence=resolved_settings.min_independent_evidence,
                    min_objective_improvement=resolved_settings.min_objective_improvement,
                    complexity_penalty=resolved_settings.complexity_penalty,
                    ambiguity_margin=resolved_settings.ambiguity_margin,
                    abstain_when_ambiguous=resolved_settings.abstain_when_ambiguous,
                    missing_intensity_max=resolved_settings.missing_intensity_max,
                    noise_sigma=(
                        float(peak_detection_receipt["median_noise_sigma"])
                        if isinstance(peak_detection_receipt.get("median_noise_sigma"), float)
                        and peak_detection_receipt["median_noise_sigma"] > 0
                        else None
                    ),
                    inactive_scale_relative_tolerance=resolved_settings.inactive_scale_relative_tolerance,
                    profile_width_deg=resolved_settings.profile_width_deg,
                    d_spacing_scale_tolerance=resolved_settings.d_spacing_scale_tolerance,
                    max_fit_attempts=resolved_settings.max_fit_attempts,
                    swap_fit_attempt_budget=resolved_settings.swap_fit_attempt_budget,
                    profile_width_model=width_model,
                    profile_eta=resolved_settings.profile_eta,
                    zero_shift_max_deg=resolved_settings.zero_shift_max_deg,
                    zero_shift_step_deg=resolved_settings.zero_shift_step_deg,
                ),
                scan_range_deg=(float(np.min(angles)), float(np.max(angles))),
                background_intensities=processed.background,
                weight_provenance="trapezoidal-grid from acquired angle spacing",
                residual_candidate_provider=residual_candidate_provider,
            )
            if residual_candidates:
                by_id = {reference.reference_id: reference for reference in candidate_phases}
                by_id.update(residual_candidates)
                candidate_phases = tuple(by_id.values())
        stage_timer.mark("mixture_search")
    finally:
        close = getattr(store, "close", None)
        if owns_store and callable(close):
            close()
    quality = _quality_report(
        pattern.point_count,
        processed.signal_to_noise,
        processed.baseline_fraction,
        peaks,
        calibration_status=calibration_status,
        calibration_rmse_deg=calibration.rmse_deg if calibration is not None else None,
        extra_warnings=range_warnings,
    )
    candidates = _align_candidate_status(candidates, calibration_status, quality.warnings)
    decision = _decision(candidates, quality.warnings, calibration_status)
    if mixture is not None:
        mixture = _bound_mixture_result(mixture)
        if calibration_status is not CalibrationStatus.PASSED or any("Low estimated" in warning for warning in quality.warnings):
            mixture = replace(
                mixture,
                hypotheses=tuple(
                    replace(hypothesis, status="tentative" if hypothesis.status == "supported" else hypothesis.status)
                    for hypothesis in mixture.hypotheses
                ),
            )
    calibration_standard = None
    if calibration is not None:
        try:
            standard = get_calibration_standard(calibration.standard_id)
            calibration_standard = {
                "standard_id": standard.standard_id,
                "name": standard.name,
                "status": standard.status,
                "material_formula": standard.material_formula,
                "source_reference": standard.source_reference,
                "source_url": standard.source_url,
                "source_note": standard.source_note,
                "certificate_id": standard.certificate_id,
                "manifest_sha256": standard.manifest_sha256,
                "license_note": standard.license_note,
                "line_derivation": standard.line_derivation,
                "lattice_parameter_angstrom": standard.lattice_parameter_angstrom,
                "lattice_parameter_temperature_c": standard.lattice_parameter_temperature_c,
                "expanded_uncertainty_k": standard.expanded_uncertainty_k,
            }
        except ValueError:
            calibration_standard = {"standard_id": calibration.standard_id}
    store_provenance = dict(store_provenance)
    store_provenance["powcod_equivalence_resolution"] = equivalence_receipt
    store_provenance["equivalence_method_version"] = equivalence_receipt.get("method_version")
    store_provenance["equivalence_configuration_sha256"] = equivalence_receipt.get("configuration_sha256")
    store_provenance["candidate_ranking"] = candidate_ranking_profile(
        use_intensity=bool(intensity_policy.get("intensity_scoring", True))
    )
    store_provenance["candidate_retention"] = candidate_retention_profile()
    store_provenance["qualx_candidate_search"] = qualx_search_receipt
    analysis_id = _analysis_id(file_hash, resolved_settings, store_provenance)
    provenance_phases = tuple(candidate_source_phases.values()) or candidate_phases
    cod_entry_keys = sorted(
        {
            (
                phase.reference_id,
                phase.cod_entry_id,
                phase.cod_block_id,
                phase.cod_entry_url,
            )
            for phase in provenance_phases
            if phase.cod_entry_id is not None
        },
        key=lambda item: (item[1], item[2] or "", item[0]),
    )
    cod_entries: list[dict[str, object]] = []
    for reference_id, entry_id, block_id, source_url in cod_entry_keys:
        entry: dict[str, object] = {
            "reference_id": reference_id,
            "entry_id": entry_id,
            "block_id": block_id,
            "source_url": source_url,
        }
        source_phase = next(
            (
                phase
                for phase in provenance_phases
                if phase.reference_id == reference_id
                and phase.cod_entry_id == entry_id
                and phase.cod_block_id == block_id
            ),
            None,
        )
        if source_phase is not None and source_phase.source_path is not None:
            entry["source_path"] = source_phase.source_path
        if source_phase is not None and source_phase.source_cif_sha256 is not None:
            entry["cif_sha256"] = source_phase.source_cif_sha256
        if source_phase is not None and source_phase.equivalence_group_id is not None:
            entry["equivalence_group_id"] = source_phase.equivalence_group_id
            entry["parent_family_group_id"] = source_phase.parent_family_group_id
            entry["equivalence_kind"] = source_phase.equivalence_kind
            entry["equivalence_confidence"] = source_phase.equivalence_confidence
        if source_phase is not None:
            group = next(
                (
                    item for item in (equivalence_receipt.get("groups", []) if isinstance(equivalence_receipt, dict) else [])
                    if isinstance(item, dict)
                    and source_phase.reference_id in item.get("member_reference_ids", [])
                ),
                None,
            )
            if group is not None and len(group.get("member_reference_ids", [])) > 1:
                entry["equivalence_member_ids"] = list(group.get("member_reference_ids", []))
                entry["equivalence_name_status"] = group.get("name_status")
        cod_entries.append(entry)
    store_provenance.update(
        {
            "cod_entry_ids": sorted(
                {phase.cod_entry_id for phase in provenance_phases if phase.cod_entry_id is not None}
            ),
            "cod_block_ids": sorted(
                {phase.cod_block_id for phase in provenance_phases if phase.cod_block_id is not None}
            ),
            "cod_source_urls": sorted(
                {phase.cod_entry_url for phase in provenance_phases if phase.cod_entry_url is not None}
            ),
            "cod_entries": cod_entries,
            "reference_query": {
                "radiation": effective_radiation.key,
                "radiation_spectrum": radiation_spectrum,
                "tolerance_deg": resolved_settings.peak_tolerance_deg,
                "observed_peak_count": len(peaks),
                "candidate_count": len(candidate_phases),
                "candidate_query_stats": candidate_query_stats,
                "intensity_policy": intensity_policy,
            },
        }
    )
    report = AnalysisReport(
        schema_version="0.1",
        analysis_id=analysis_id,
        decision=decision,
        input=InputSummary(
            file_name=pattern.source_name,
            file_extension=Path(pattern.source_name).suffix.lower(),
            point_count=pattern.point_count,
            angle_min_deg=min(pattern.angles_deg),
            angle_max_deg=max(pattern.angles_deg),
            sha256=file_hash,
        ),
        radiation_key=radiation.key,
        radiation_label=radiation.label,
        angle_unit=pattern.angle_unit.value,
        peaks=peaks,
        candidates=candidates,
        quality=quality,
        mixture=mixture,
        provenance={
            "algorithm_version": ALGORITHM_VERSION,
            **store_provenance,
            "input_source": {
                "format": pattern.source_format,
                "metadata": dict(pattern.metadata),
            },
            "measurement_trace": _trace_payload(trace_angles, trace_intensities, angles, processed.corrected_intensities),
            "full_measurement_trace": _trace_payload(
                full_trace_angles,
                full_trace_intensities,
                full_trace_corrected_angles,
                full_trace_intensities,
            ),
            "peak_detection": peak_detection_receipt,
            "timings": stage_timer.receipt(),
            "sample_displacement": displacement_receipt,
            "evaluation_window": {
                "upper_two_theta_deg": configured_maximum_angle,
                "basis": "configured_primary_matching_window" if configured_maximum_angle is not None else "indexed_reference_range",
            },
            "settings": {
                "radiation": radiation.key,
                "k_alpha_treatment": radiation_spectrum["treatment"],
                "angle_unit": pattern.angle_unit.value,
                "reference_source": resolved_settings.reference_source,
                "peak_tolerance_deg": resolved_settings.peak_tolerance_deg,
                "min_prominence_fraction": resolved_settings.min_prominence_fraction,
                "max_peaks": resolved_settings.max_peaks,
                "background_window_points": resolved_settings.background_window_points,
                "peak_detection": resolved_settings.peak_detection,
                "background_window_deg": resolved_settings.background_window_deg,
                "peak_min_snr": resolved_settings.peak_min_snr,
                "peak_min_width_deg": resolved_settings.peak_min_width_deg,
                "peak_smoothing_window_deg": resolved_settings.peak_smoothing_window_deg,
                "peak_min_relative_prominence": resolved_settings.peak_min_relative_prominence,
                "reference_limit": resolved_settings.reference_limit,
                "allowed_elements": list(resolved_settings.allowed_elements) if resolved_settings.allowed_elements else None,
                "oxidizing_synthesis": resolved_settings.oxidizing_synthesis,
                "missing_intensity_max": resolved_settings.missing_intensity_max,
                "matching_two_theta_max_deg": resolved_settings.matching_two_theta_max_deg,
                "analysis_mode": resolved_settings.analysis_mode,
                "analysis_variant": resolved_settings.analysis_variant,
                "residual_candidate_queries": resolved_settings.residual_candidate_queries,
                "max_phases": resolved_settings.max_phases,
                "candidate_pool": resolved_settings.candidate_pool,
                "candidate_lookup_budget": resolved_settings.effective_candidate_lookup_budget,
                "candidate_retrieval_mode": resolved_settings.candidate_retrieval_mode,
                "retained_branches": resolved_settings.retained_branches,
                "min_independent_evidence": resolved_settings.min_independent_evidence,
                "min_objective_improvement": resolved_settings.min_objective_improvement,
                "complexity_penalty": resolved_settings.complexity_penalty,
                "ambiguity_margin": resolved_settings.ambiguity_margin,
                "abstain_when_ambiguous": resolved_settings.abstain_when_ambiguous,
                "inactive_scale_relative_tolerance": resolved_settings.inactive_scale_relative_tolerance,
                "profile_width_deg": resolved_settings.profile_width_deg,
                "profile_width_mode": resolved_settings.profile_width_mode,
                "profile_eta": resolved_settings.profile_eta,
                "zero_shift_max_deg": resolved_settings.zero_shift_max_deg,
                "zero_shift_step_deg": resolved_settings.zero_shift_step_deg,
                "displacement_search_max_deg": resolved_settings.displacement_search_max_deg,
                "displacement_tolerance_deg": resolved_settings.displacement_tolerance_deg,
                "lattice_scale_tolerance": resolved_settings.lattice_scale_tolerance,
                "d_spacing_scale_tolerance": resolved_settings.d_spacing_scale_tolerance,
                "max_fit_attempts": resolved_settings.max_fit_attempts,
                "swap_fit_attempt_budget": resolved_settings.swap_fit_attempt_budget,
                "equivalence_method_version": equivalence_receipt.get("method_version"),
                "equivalence_configuration_sha256": equivalence_receipt.get("configuration_sha256"),
                "instrument": (
                    resolved_settings.instrument.to_dict()
                    if resolved_settings.instrument is not None
                    else None
                ),
                "calibration": calibration.to_dict() if calibration is not None else None,
            },
            "coordinate_correction": {
                "raw_angle_min_deg": float(np.min(raw_angles)),
                "raw_angle_max_deg": float(np.max(raw_angles)),
                "zero_shift_applied_deg": (
                    calibration.zero_shift_deg
                    if calibration is not None and calibration_status == CalibrationStatus.PASSED
                    else 0.0
                ),
                "wavelength_scale_applied": (
                    calibration.wavelength_scale
                    if calibration is not None and calibration_status == CalibrationStatus.PASSED
                    else 1.0
                ),
                "calibration_applied": calibration_status == CalibrationStatus.PASSED,
                "sample_displacement_deg": displacement_receipt.get("displacement_deg", 0.0),
                "sample_displacement_model": "delta_2theta = D * cos(theta)",
            },
            "calibration_standard": calibration_standard,
            "limitations": [
                "This report ranks hypotheses and does not assert universal phase certainty.",
                "No quantitative phase fraction or full-pattern Rietveld refinement is performed.",
                "Binary vendor RAW variants require the optional GSAS-II adapter.",
                "Line-position calibration is required before a supported decision is reported.",
            ],
        },
    )
    return report


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _analysis_id(
    file_hash: str,
    settings: AnalysisSettings,
    reference_provenance: dict[str, object] | None = None,
) -> str:
    serialized = json.dumps(
        {
            "sha256": file_hash,
            "radiation": settings.radiation,
            "angle_unit": settings.angle_unit.value,
            "reference_source": settings.reference_source,
            "tolerance": settings.peak_tolerance_deg,
            "prominence": settings.min_prominence_fraction,
            "max_peaks": settings.max_peaks,
            "background_window_points": settings.background_window_points,
            "peak_detection": settings.peak_detection,
            "background_window_deg": settings.background_window_deg,
            "peak_min_snr": settings.peak_min_snr,
            "peak_min_width_deg": settings.peak_min_width_deg,
            "peak_smoothing_window_deg": settings.peak_smoothing_window_deg,
            "peak_min_relative_prominence": settings.peak_min_relative_prominence,
            "reference_limit": settings.reference_limit,
            "allowed_elements": list(settings.allowed_elements) if settings.allowed_elements else None,
            "oxidizing_synthesis": settings.oxidizing_synthesis,
            "missing_intensity_max": settings.missing_intensity_max,
            "analysis_mode": settings.analysis_mode,
            "analysis_variant": settings.analysis_variant,
            "residual_candidate_queries": settings.residual_candidate_queries,
            "max_phases": settings.max_phases,
            "candidate_pool": settings.candidate_pool,
            "candidate_lookup_budget": settings.effective_candidate_lookup_budget,
            "candidate_retrieval_mode": settings.candidate_retrieval_mode,
            "retained_branches": settings.retained_branches,
            "min_independent_evidence": settings.min_independent_evidence,
            "min_objective_improvement": settings.min_objective_improvement,
            "complexity_penalty": settings.complexity_penalty,
            "ambiguity_margin": settings.ambiguity_margin,
            "abstain_when_ambiguous": settings.abstain_when_ambiguous,
            "inactive_scale_relative_tolerance": settings.inactive_scale_relative_tolerance,
            "profile_width_deg": settings.profile_width_deg,
            "profile_width_mode": settings.profile_width_mode,
            "profile_eta": settings.profile_eta,
            "zero_shift_max_deg": settings.zero_shift_max_deg,
            "zero_shift_step_deg": settings.zero_shift_step_deg,
            "displacement_search_max_deg": settings.displacement_search_max_deg,
            "displacement_tolerance_deg": settings.displacement_tolerance_deg,
            "lattice_scale_tolerance": settings.lattice_scale_tolerance,
            "d_spacing_scale_tolerance": settings.d_spacing_scale_tolerance,
            "max_fit_attempts": settings.max_fit_attempts,
            "swap_fit_attempt_budget": settings.swap_fit_attempt_budget,
            "matching_two_theta_max_deg": settings.matching_two_theta_max_deg,
            "calibration": settings.calibration.to_dict() if settings.calibration is not None else None,
            "instrument": settings.instrument.to_dict() if settings.instrument is not None else None,
            "algorithm_version": ALGORITHM_VERSION,
            "reference_identity": {
                key: value
                for key, value in (reference_provenance or {}).items()
                if key in {
                    "reference_source",
                    "reference_database_hash",
                    "powcod_release",
                    "powcod_database_sha256",
                    "powcod_cache_sha256",
                    "powcod_schema_version",
                    "powcod_adapter_version",
                    "powcod_index_kind",
                    "powcod_d_bin_width_angstrom",
                    "powcod_max_index_d_angstrom",
                    "powcod_reflection_encoding",
                    "powcod_retrieval_policy_version",
                    "powcod_equivalence_content_sha256",
                    "powcod_equivalence_method_version",
                    "snapshot_id",
                    "snapshot_manifest_sha256",
                    "canonical_content_sha256",
                    "index_schema_version",
                    "index_configuration_sha256",
                    "index_canonical_content_sha256",
                    "index_config_hash",
                    "radiation_configuration_sha256",
                    "powder_configuration_sha256",
                    "equivalence_method_version",
                    "equivalence_configuration_sha256",
                    "candidate_ranking",
                    "candidate_retention",
                }
            },
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()[:16]


def _trace_payload(
    raw_angles: np.ndarray,
    raw_intensities: np.ndarray,
    corrected_angles: np.ndarray,
    corrected_intensities: np.ndarray,
    *,
    limit: int = 2000,
) -> dict[str, list[float]]:
    """Return a bounded trace for the UI without replacing the immutable input."""

    count = len(raw_angles)
    indices = np.linspace(0, count - 1, min(count, limit), dtype=int) if count else np.array([], dtype=int)
    return {
        "raw_angles_deg": [float(raw_angles[index]) for index in indices],
        "raw_intensities": [float(raw_intensities[index]) for index in indices],
        "corrected_angles_deg": [float(corrected_angles[index]) for index in indices],
        "corrected_intensities": [float(corrected_intensities[index]) for index in indices],
    }


def _align_candidate_status(
    candidates: tuple,
    calibration_status: CalibrationStatus,
    warnings: tuple[str, ...],
) -> tuple:
    """Keep per-candidate support labels consistent with report gates."""

    support_allowed = calibration_status is CalibrationStatus.PASSED and not any(
        "Low estimated" in warning for warning in warnings
    )
    if support_allowed:
        return candidates
    return tuple(
        replace(candidate, status="tentative") if candidate.status == "supported" else candidate
        for candidate in candidates
    )


def _bound_mixture_result(result: MixtureResult, limit: int = 2000) -> MixtureResult:
    trace = result.residual_trace
    count = len(trace.angles_deg)
    if count <= limit:
        return result
    indices = np.linspace(0, count - 1, limit, dtype=int)
    bounded = MixtureResidualTrace(
        tuple(trace.angles_deg[index] for index in indices),
        tuple(trace.observed_intensities[index] for index in indices),
        tuple(trace.calculated_intensities[index] for index in indices),
        tuple(trace.residual_intensities[index] for index in indices),
        truncated=True,
        component_traces=tuple(
            MixtureComponentTrace(
                component.reference_id,
                tuple(component.calculated_intensities[index] for index in indices),
            )
            for component in trace.component_traces
        ),
        background_intensities=(
            tuple(trace.background_intensities[index] for index in indices)
            if len(trace.background_intensities) == count
            else ()
        ),
        fit_target_intensities=(
            tuple(trace.fit_target_intensities[index] for index in indices)
            if len(trace.fit_target_intensities) == count
            else ()
        ),
        weights=(
            tuple(trace.weights[index] for index in indices)
            if len(trace.weights) == count
            else ()
        ),
    )
    return replace(result, residual_trace=bounded)


def _quality_report(
    point_count: int,
    signal_to_noise: float,
    baseline_fraction: float,
    peaks: tuple,
    *,
    calibration_status: CalibrationStatus,
    calibration_rmse_deg: float | None,
    extra_warnings: tuple[str, ...] | list[str] = (),
) -> QualityReport:
    warnings: list[str] = list(extra_warnings)
    if point_count < 100:
        warnings.append("Sparse scan: peak positions may be undersampled.")
    if signal_to_noise < 3.0:
        warnings.append("Low estimated signal-to-noise ratio; candidate scores should be treated cautiously.")
    if baseline_fraction > 0.75:
        warnings.append("Background dominates the measured signal.")
    if not peaks:
        warnings.append("No peaks met the prominence threshold.")
    if calibration_status == CalibrationStatus.UNVERIFIED:
        warnings.append(
            "Instrument line-position calibration is unverified; a supported-looking match is not publication-ready."
        )
    elif calibration_status == CalibrationStatus.INSUFFICIENT_DATA:
        warnings.append("Calibration did not have enough standard lines to validate the coordinate.")
    elif calibration_status == CalibrationStatus.FAILED:
        warnings.append("Instrument line-position calibration failed its provisional quality limits.")
    return QualityReport(
        signal_to_noise=float(signal_to_noise),
        baseline_fraction=float(baseline_fraction),
        warnings=tuple(warnings),
        checks={
            "monotonic_angles": "pass",
            "finite_values": "pass",
            "peak_detection": "pass" if peaks else "review",
            "background_subtraction": "pass",
            "line_position_calibration": calibration_status.value,
        },
        calibration_status=calibration_status.value,
        calibration_rmse_deg=calibration_rmse_deg,
    )


def _decision(
    candidates: tuple,
    warnings: tuple[str, ...],
    calibration_status: CalibrationStatus,
) -> str:
    if not candidates or candidates[0].matched_peaks < 2:
        return "unresolved"
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    if second and abs(top.score - second.score) <= 0.05 and top.score >= 0.50:
        return "ambiguous"
    if (
        top.score >= 0.75
        and calibration_status == CalibrationStatus.PASSED
        and not any("Low estimated" in warning for warning in warnings)
    ):
        return "supported"
    if top.score >= 0.50:
        return "tentative"
    return "unresolved"
