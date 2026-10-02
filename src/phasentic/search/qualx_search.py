"""Deterministic, auditable peak-list candidate screening.

This module implements a QUALX-inspired search stage, not a phase probability
model and not a full-pattern refinement. Inputs are calibrated 2θ peak
positions and reference d-spacings. Observed peaks and reference records are
treated as immutable evidence; only the returned assessments are new values.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, replace
import math
from types import MappingProxyType
from typing import Iterable, Literal, Mapping

from phasentic.domain.identity_cache import IdentityLRU
from phasentic.domain.models import CandidateMatch, Peak, ReferencePhase
from phasentic.domain.radiation import (
    Radiation,
    get_radiation,
    radiation_spectral_components,
    two_theta_from_wavelength,
)


QUALX_SEARCH_VERSION = "qualx-inspired-peak-list-search-0.1"
SCORE_SEMANTICS = "deterministic ranking score; not a probability or certainty"
PrefilterMode = Literal["all", "any"]


@dataclass(frozen=True)
class FigureOfMeritWeights:
    """Nonnegative relative weights for transparent FoM components.

    Defaults are deliberately equal and provisional. They are ranking
    parameters, not scientifically calibrated probabilities.
    """

    position_agreement: float = 0.25
    matched_observed_intensity: float = 0.25
    observed_coverage: float = 0.25
    database_coverage: float = 0.25

    def __post_init__(self) -> None:
        values = (
            self.position_agreement,
            self.matched_observed_intensity,
            self.observed_coverage,
            self.database_coverage,
        )
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0.0
            for value in values
        ):
            raise ValueError("Figure-of-merit weights must be finite and nonnegative")
        if math.fsum(values) <= 0.0:
            raise ValueError("At least one figure-of-merit weight must be positive")


@dataclass(frozen=True)
class QualxSearchConfig:
    """Reproducible peak-list screening and strongest-line prefilter policy."""

    tolerance_deg: float = 0.20
    strongest_reference_line_count: int = 3
    prefilter_mode: PrefilterMode = "any"
    weights: FigureOfMeritWeights = FigureOfMeritWeights()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.tolerance_deg, (int, float))
            or isinstance(self.tolerance_deg, bool)
            or not math.isfinite(self.tolerance_deg)
            or self.tolerance_deg <= 0.0
        ):
            raise ValueError("tolerance_deg must be positive and finite")
        if (
            not isinstance(self.strongest_reference_line_count, int)
            or isinstance(self.strongest_reference_line_count, bool)
            or self.strongest_reference_line_count < 1
        ):
            raise ValueError("strongest_reference_line_count must be a positive integer")
        if self.prefilter_mode not in ("all", "any"):
            raise ValueError("prefilter_mode must be 'all' or 'any'")
        if not isinstance(self.weights, FigureOfMeritWeights):
            raise ValueError("weights must be FigureOfMeritWeights")

    def to_dict(self, radiation: Radiation | str | None = None) -> dict[str, object]:
        """Return settings and the intensity-support decision for provenance."""

        selected = get_radiation(radiation) if radiation is not None else None
        intensity_comparison = (
            "not_evaluated"
            if selected is None
            else "supported"
            if selected.key == "cu_ka"
            else "unsupported"
        )
        return {
            "algorithm_version": QUALX_SEARCH_VERSION,
            "angle_coordinate": "calibrated 2theta degrees",
            "tolerance_deg": self.tolerance_deg,
            "strongest_reference_line_count": self.strongest_reference_line_count,
            "prefilter_mode": self.prefilter_mode,
            "weights": {
                "position_agreement": self.weights.position_agreement,
                "matched_observed_intensity": self.weights.matched_observed_intensity,
                "observed_coverage": self.weights.observed_coverage,
                "database_coverage": self.weights.database_coverage,
            },
            "intensity_comparison": intensity_comparison,
            "score_semantics": SCORE_SEMANTICS,
        }


@dataclass(frozen=True)
class ReflectionMatch:
    """One observed maximum associated with one reference reflection."""

    reference_line_index: int
    observed_peak_index: int
    spectral_component_index: int
    observed_two_theta_deg: float
    expected_two_theta_deg: float
    position_error_deg: float


@dataclass(frozen=True)
class FigureOfMerit:
    """FoM components and the normalized weights used to combine them."""

    score: float
    position_agreement: float
    matched_observed_intensity: float | None
    observed_coverage: float
    database_coverage: float
    active_weights: Mapping[str, float]
    matched_observed_peaks: int
    observed_peaks: int
    matched_reference_lines: int
    expected_reference_lines: int
    score_semantics: str = SCORE_SEMANTICS

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_weights", MappingProxyType(dict(self.active_weights)))

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "position_agreement": self.position_agreement,
            "matched_observed_intensity": self.matched_observed_intensity,
            "observed_coverage": self.observed_coverage,
            "database_coverage": self.database_coverage,
            "active_weights": dict(self.active_weights),
            "matched_observed_peaks": self.matched_observed_peaks,
            "observed_peaks": self.observed_peaks,
            "matched_reference_lines": self.matched_reference_lines,
            "expected_reference_lines": self.expected_reference_lines,
            "score_semantics": self.score_semantics,
        }


@dataclass(frozen=True)
class QualxCandidateAssessment:
    """Evidence and screening outcome for one unique reference structure."""

    reference_id: str
    name: str
    formula: str
    passed_prefilter: bool
    strongest_reference_lines_matched: int
    strongest_reference_lines_considered: int
    rejection_reason: str | None
    figure_of_merit: FigureOfMerit
    line_matches: tuple[ReflectionMatch, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_id": self.reference_id,
            "name": self.name,
            "formula": self.formula,
            "passed_prefilter": self.passed_prefilter,
            "strongest_reference_lines_matched": self.strongest_reference_lines_matched,
            "strongest_reference_lines_considered": self.strongest_reference_lines_considered,
            "rejection_reason": self.rejection_reason,
            "figure_of_merit": self.figure_of_merit.to_dict(),
            "line_matches": [
                {
                    "reference_line_index": match.reference_line_index,
                    "observed_peak_index": match.observed_peak_index,
                    "spectral_component_index": match.spectral_component_index,
                    "observed_two_theta_deg": match.observed_two_theta_deg,
                    "expected_two_theta_deg": match.expected_two_theta_deg,
                    "position_error_deg": match.position_error_deg,
                }
                for match in self.line_matches
            ],
        }


@dataclass(frozen=True)
class QualxSearchDiagnostics:
    """Counts that explain which candidates were accepted or rejected."""

    candidate_count: int
    unique_candidate_count: int
    duplicate_reference_ids_skipped: int
    accepted_count: int
    rejected_count: int
    rejected_no_observed_peaks: int
    rejected_no_reference_lines_in_scan: int
    rejected_strongest_reference_prefilter: int
    scan_range_source: str
    scan_range_deg: tuple[float, float] | None
    strongest_reference_line_count: int
    prefilter_mode: PrefilterMode

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_count": self.candidate_count,
            "unique_candidate_count": self.unique_candidate_count,
            "duplicate_reference_ids_skipped": self.duplicate_reference_ids_skipped,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "rejected_no_observed_peaks": self.rejected_no_observed_peaks,
            "rejected_no_reference_lines_in_scan": self.rejected_no_reference_lines_in_scan,
            "rejected_strongest_reference_prefilter": self.rejected_strongest_reference_prefilter,
            "scan_range_source": self.scan_range_source,
            "scan_range_deg": list(self.scan_range_deg) if self.scan_range_deg is not None else None,
            "strongest_reference_line_count": self.strongest_reference_line_count,
            "prefilter_mode": self.prefilter_mode,
        }


@dataclass(frozen=True)
class QualxSearchResult:
    """All unique assessments in deterministic rank order."""

    ranked_candidates: tuple[QualxCandidateAssessment, ...]
    diagnostics: QualxSearchDiagnostics
    algorithm_version: str = QUALX_SEARCH_VERSION


    def to_dict(self) -> dict[str, object]:
        return {
            "algorithm_version": self.algorithm_version,
            "diagnostics": self.diagnostics.to_dict(),
            "ranked_candidates": [candidate.to_dict() for candidate in self.ranked_candidates],
        }


def rerank_candidate_matches(
    matches: Iterable[CandidateMatch],
    result: QualxSearchResult,
    *,
    influence_weight: float = 0.20,
) -> tuple[CandidateMatch, ...]:
    """Blend the native score with the QUALX-inspired FoM without filtering.

    The strongest-reference prefilter is deliberately advisory: a failed
    candidate remains in the output and can still enter a later shortlist.
    The blend is an uncalibrated, versioned ranking aid, not a phase
    probability. A zero influence weight preserves input order and scores.
    """

    if (
        isinstance(influence_weight, bool)
        or not isinstance(influence_weight, (int, float))
        or not math.isfinite(float(influence_weight))
        or not 0.0 <= float(influence_weight) <= 1.0
    ):
        raise ValueError("influence_weight must be finite and between 0 and 1")
    ordered_matches = tuple(matches)
    weight = float(influence_weight)
    if weight == 0.0:
        return ordered_matches
    assessments = {item.reference_id: item for item in result.ranked_candidates}
    blended: list[CandidateMatch] = []
    for match in ordered_matches:
        assessment = assessments.get(match.reference_id)
        if assessment is None:
            blended.append(match)
            continue
        score = (1.0 - weight) * float(match.score) + weight * assessment.figure_of_merit.score
        blended.append(replace(match, score=max(0.0, min(1.0, score))))
    return tuple(sorted(blended, key=lambda item: (-item.score, item.reference_id)))


@dataclass(frozen=True)
class _ObservedPeak:
    original_index: int
    peak: Peak


@dataclass(frozen=True)
class _ExpectedComponent:
    reference_line_index: int
    spectral_component_index: int
    expected_two_theta_deg: float


@dataclass(frozen=True)
class _ExpectedLine:
    reference_line_index: int
    relative_intensity: float
    components: tuple[_ExpectedComponent, ...]


def search_candidates(
    peaks: Iterable[Peak],
    references: Iterable[ReferencePhase],
    radiation: Radiation | str,
    *,
    config: QualxSearchConfig = QualxSearchConfig(),
    scan_range_deg: tuple[float, float] | None = None,
) -> QualxSearchResult:
    """Score and prefilter references from calibrated 2θ peak-list evidence.

    When ``scan_range_deg`` is omitted, the measured range is approximated by
    the observed peak extent plus the configured match tolerance. Supplying
    the actual scan limits is preferable because a peak list alone cannot
    reveal where measured-but-peak-free intervals occurred.

    Candidate records with duplicate reference IDs are evaluated once; the
    first record is retained. Candidate scores are deterministic rankings,
    never probabilities or certainty estimates. Non-Cu radiation disables
    intensity comparison and renormalizes the other configured weights.
    """

    selected_radiation = get_radiation(radiation)
    observed_input = tuple(peaks)
    references_input = tuple(references)
    _validate_peaks(observed_input)
    resolved_range, range_source = _resolve_scan_range(observed_input, scan_range_deg, config.tolerance_deg)
    ordered_peaks = tuple(
        sorted(
            (_ObservedPeak(index, peak) for index, peak in enumerate(observed_input)),
            key=lambda item: (item.peak.position_deg, -item.peak.intensity, item.original_index),
        )
    )
    if resolved_range is not None:
        ordered_peaks = tuple(
            item
            for item in ordered_peaks
            if resolved_range[0] <= item.peak.position_deg <= resolved_range[1]
        )

    unique_references: list[ReferencePhase] = []
    seen_ids: set[str] = set()
    duplicate_ids = 0
    for reference in references_input:
        if reference.reference_id in seen_ids:
            duplicate_ids += 1
            continue
        seen_ids.add(reference.reference_id)
        _validate_reference(reference)
        unique_references.append(reference)

    assessments: list[QualxCandidateAssessment] = []
    no_observed_count = 0
    no_reference_lines_count = 0
    prefilter_rejected_count = 0
    for reference in unique_references:
        expected_lines = _expected_lines(reference, selected_radiation, resolved_range)
        matches = _associate_lines(
            ordered_peaks,
            expected_lines,
            config.tolerance_deg,
        )
        fom = _figure_of_merit(
            ordered_peaks,
            expected_lines,
            matches,
            selected_radiation,
            config.weights,
            config.tolerance_deg,
        )
        strongest_lines = _strongest_lines(expected_lines, config.strongest_reference_line_count)
        matched_line_ids = {match.reference_line_index for match in matches}
        strongest_matched = sum(line.reference_line_index in matched_line_ids for line in strongest_lines)
        strongest_considered = len(strongest_lines)

        if not ordered_peaks:
            rejection_reason = "no_observed_peaks"
            no_observed_count += 1
            passed = False
        elif not expected_lines:
            rejection_reason = "no_reference_lines_in_scan"
            no_reference_lines_count += 1
            passed = False
        else:
            passed = _passes_prefilter(strongest_matched, strongest_considered, config.prefilter_mode)
            rejection_reason = None if passed else "strongest_reference_prefilter_failed"
            if not passed:
                prefilter_rejected_count += 1
        assessments.append(
            QualxCandidateAssessment(
                reference_id=reference.reference_id,
                name=reference.name,
                formula=reference.formula,
                passed_prefilter=passed,
                strongest_reference_lines_matched=strongest_matched,
                strongest_reference_lines_considered=strongest_considered,
                rejection_reason=rejection_reason,
                figure_of_merit=fom,
                line_matches=matches,
            )
        )

    ranked = tuple(
        sorted(
            assessments,
            key=lambda item: (
                not item.passed_prefilter,
                -item.figure_of_merit.score,
                item.reference_id,
            ),
        )
    )
    accepted_count = sum(candidate.passed_prefilter for candidate in ranked)
    diagnostics = QualxSearchDiagnostics(
        candidate_count=len(references_input),
        unique_candidate_count=len(unique_references),
        duplicate_reference_ids_skipped=duplicate_ids,
        accepted_count=accepted_count,
        rejected_count=len(unique_references) - accepted_count,
        rejected_no_observed_peaks=no_observed_count,
        rejected_no_reference_lines_in_scan=no_reference_lines_count,
        rejected_strongest_reference_prefilter=prefilter_rejected_count,
        scan_range_source=range_source,
        scan_range_deg=resolved_range,
        strongest_reference_line_count=config.strongest_reference_line_count,
        prefilter_mode=config.prefilter_mode,
    )
    return QualxSearchResult(ranked_candidates=ranked, diagnostics=diagnostics)


def _validate_peaks(peaks: tuple[Peak, ...]) -> None:
    for peak in peaks:
        if not all(math.isfinite(value) for value in (peak.position_deg, peak.intensity)):
            raise ValueError("Each peak must have finite position and intensity values")
        if not 0.0 < peak.position_deg < 180.0:
            raise ValueError("Each peak position must be calibrated 2θ between 0 and 180 degrees")


def _validate_reference(reference: ReferencePhase) -> None:
    if not isinstance(reference.reference_id, str) or not reference.reference_id.strip():
        raise ValueError("Each reference must have a non-empty reference_id")
    for line in reference.lines:
        if not math.isfinite(line.d_spacing_angstrom) or line.d_spacing_angstrom <= 0.0:
            raise ValueError(f"Reference {reference.reference_id} contains an invalid d spacing")
        if not math.isfinite(line.relative_intensity) or line.relative_intensity < 0.0:
            raise ValueError(f"Reference {reference.reference_id} contains an invalid relative intensity")


def _resolve_scan_range(
    peaks: tuple[Peak, ...],
    scan_range_deg: tuple[float, float] | None,
    tolerance_deg: float,
) -> tuple[tuple[float, float] | None, str]:
    if scan_range_deg is not None:
        if (
            not isinstance(scan_range_deg, tuple)
            or len(scan_range_deg) != 2
            or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in scan_range_deg)
        ):
            raise ValueError("scan_range_deg must be a two-value tuple")
        lower, upper = (float(value) for value in scan_range_deg)
        if not math.isfinite(lower) or not math.isfinite(upper) or not 0.0 <= lower < upper <= 180.0:
            raise ValueError("scan_range_deg must satisfy 0 <= lower < upper <= 180")
        return (lower, upper), "provided"
    if not peaks:
        return None, "unavailable_no_observed_peaks"
    lower = max(0.0, min(peak.position_deg for peak in peaks) - tolerance_deg)
    upper = min(180.0, max(peak.position_deg for peak in peaks) + tolerance_deg)
    if lower >= upper:
        raise ValueError("Observed peaks do not define a valid scan range")
    return (lower, upper), "observed_peak_extent_plus_tolerance"


_EXPECTED_LINES_CACHE = IdentityLRU(8000)


def _expected_lines(
    reference: ReferencePhase,
    radiation: Radiation,
    scan_range_deg: tuple[float, float] | None,
) -> tuple[_ExpectedLine, ...]:
    spectral_components = radiation_spectral_components(radiation)
    return _EXPECTED_LINES_CACHE.get_or_compute(
        reference,
        (spectral_components, scan_range_deg),
        lambda: _expected_lines_uncached(reference, spectral_components, scan_range_deg),
    )


def _expected_lines_uncached(
    reference: ReferencePhase,
    spectral_components: tuple[tuple[float, float], ...],
    scan_range_deg: tuple[float, float] | None,
) -> tuple[_ExpectedLine, ...]:
    result: list[_ExpectedLine] = []
    for line_index, line in enumerate(reference.lines):
        components: list[_ExpectedComponent] = []
        for component_index, (wavelength, _component_weight) in enumerate(spectral_components):
            try:
                angle = two_theta_from_wavelength(line.d_spacing_angstrom, wavelength)
            except ValueError:
                continue
            if scan_range_deg is not None and not scan_range_deg[0] <= angle <= scan_range_deg[1]:
                continue
            components.append(
                _ExpectedComponent(line_index, component_index, angle)
            )
        if components:
            result.append(_ExpectedLine(line_index, line.relative_intensity, tuple(components)))
    return tuple(result)


def _associate_lines(
    peaks: tuple[_ObservedPeak, ...],
    expected_lines: tuple[_ExpectedLine, ...],
    tolerance_deg: float,
) -> tuple[ReflectionMatch, ...]:
    """Associate reflections and measured peaks without reusing a peak.

    Reflections are considered by descending reference intensity, then source
    row order. Within each reflection, spectral components are considered in
    source order and choose the closest still-unassigned observed peak. The
    deterministic greedy rule matches the existing Phasentic matcher policy;
    it is a search association, not a whole-pattern optimum.
    """

    positions = tuple(item.peak.position_deg for item in peaks)
    available = set(range(len(peaks)))
    matches: list[ReflectionMatch] = []
    ordered_lines = sorted(
        expected_lines,
        key=lambda item: (-item.relative_intensity, item.reference_line_index),
    )
    for line in ordered_lines:
        for component in line.components:
            start = bisect_left(positions, component.expected_two_theta_deg - tolerance_deg)
            end = bisect_right(positions, component.expected_two_theta_deg + tolerance_deg)
            possible = tuple(index for index in range(start, end) if index in available)
            if not possible:
                continue
            chosen = min(
                possible,
                key=lambda index: (
                    abs(peaks[index].peak.position_deg - component.expected_two_theta_deg),
                    peaks[index].peak.position_deg,
                    peaks[index].original_index,
                ),
            )
            available.remove(chosen)
            observed = peaks[chosen]
            error = abs(observed.peak.position_deg - component.expected_two_theta_deg)
            matches.append(
                ReflectionMatch(
                    reference_line_index=line.reference_line_index,
                    observed_peak_index=observed.original_index,
                    spectral_component_index=component.spectral_component_index,
                    observed_two_theta_deg=observed.peak.position_deg,
                    expected_two_theta_deg=component.expected_two_theta_deg,
                    position_error_deg=error,
                )
            )
    return tuple(
        sorted(
            matches,
            key=lambda item: (
                item.reference_line_index,
                item.spectral_component_index,
                item.observed_peak_index,
            ),
        )
    )


def _strongest_lines(
    expected_lines: tuple[_ExpectedLine, ...],
    count: int,
) -> tuple[_ExpectedLine, ...]:
    return tuple(
        sorted(
            expected_lines,
            key=lambda line: (-line.relative_intensity, line.reference_line_index),
        )[:count]
    )


def _passes_prefilter(matched: int, considered: int, mode: PrefilterMode) -> bool:
    if considered == 0:
        return False
    if mode == "all":
        return matched == considered
    return matched >= 1


def _figure_of_merit(
    peaks: tuple[_ObservedPeak, ...],
    expected_lines: tuple[_ExpectedLine, ...],
    matches: tuple[ReflectionMatch, ...],
    radiation: Radiation,
    weights: FigureOfMeritWeights,
    tolerance_deg: float,
) -> FigureOfMerit:
    matched_peak_indices = {match.observed_peak_index for match in matches}
    matched_line_indices = {match.reference_line_index for match in matches}
    observed_by_original_index = {item.original_index: item.peak for item in peaks}
    position_by_line: dict[int, list[float]] = {}
    for match in matches:
        position_by_line.setdefault(match.reference_line_index, []).append(
            math.exp(-0.5 * (match.position_error_deg / tolerance_deg) ** 2)
        )
    position_agreement = (
        math.fsum(math.fsum(values) / len(values) for values in position_by_line.values())
        / len(position_by_line)
        if position_by_line
        else 0.0
    )
    matched_intensity: float | None
    if radiation.key == "cu_ka":
        total_intensity = math.fsum(max(0.0, float(item.peak.intensity)) for item in peaks)
        matched_intensity = (
            math.fsum(
                max(0.0, float(observed_by_original_index[index].intensity))
                for index in matched_peak_indices
            )
            / total_intensity
            if total_intensity > 0.0
            else 0.0
        )
    else:
        matched_intensity = None

    observed_coverage = len(matched_peak_indices) / len(peaks) if peaks else 0.0
    database_coverage = (
        len(matched_line_indices) / len(expected_lines) if expected_lines else 0.0
    )
    declared = {
        "position_agreement": weights.position_agreement,
        "observed_coverage": weights.observed_coverage,
        "database_coverage": weights.database_coverage,
    }
    if matched_intensity is not None:
        declared["matched_observed_intensity"] = weights.matched_observed_intensity
    active_total = math.fsum(declared.values())
    if active_total <= 0.0:
        raise ValueError("Configured weights provide no supported FoM component for this radiation")
    active_weights = {name: value / active_total for name, value in declared.items() if value > 0.0}
    components = {
        "position_agreement": position_agreement,
        "observed_coverage": observed_coverage,
        "database_coverage": database_coverage,
    }
    if matched_intensity is not None:
        components["matched_observed_intensity"] = matched_intensity
    score = math.fsum(active_weights[name] * components[name] for name in active_weights)
    return FigureOfMerit(
        score=max(0.0, min(1.0, score)),
        position_agreement=position_agreement,
        matched_observed_intensity=matched_intensity,
        observed_coverage=observed_coverage,
        database_coverage=database_coverage,
        active_weights=active_weights,
        matched_observed_peaks=len(matched_peak_indices),
        observed_peaks=len(peaks),
        matched_reference_lines=len(matched_line_indices),
        expected_reference_lines=len(expected_lines),
    )


__all__ = [
    "FigureOfMerit",
    "FigureOfMeritWeights",
    "PrefilterMode",
    "QualxCandidateAssessment",
    "QualxSearchConfig",
    "QualxSearchDiagnostics",
    "QualxSearchResult",
    "ReflectionMatch",
    "search_candidates",
]
