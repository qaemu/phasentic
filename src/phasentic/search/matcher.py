from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Protocol

import numpy as np

from phasentic.domain.identity_cache import IdentityLRU
from phasentic.domain.models import CandidateMatch, Peak, ReferenceLine, ReferencePhase
from phasentic.domain.radiation import (
    Radiation,
    radiation_spectral_components,
    two_theta_from_wavelength,
)

CANDIDATE_RANKING_VERSION = "major-peak-ranking-0.8-reference-evidence"
STRONGEST_OBSERVED_PEAK_COUNT = 10
STRONGEST_REFERENCE_REFLECTION_COUNT = 10
FITTER_SHORTLIST_VERSION = "strong-peak-diverse-shortlist-0.1"
FITTER_SHORTLIST_GLOBAL_SHARE = 0.70

_CU_RANKING_WEIGHTS = {
    "peak_position_agreement": 0.25,
    "strongest_observed_peak_intensity_weighted_coverage": 0.35,
    "relative_intensity_agreement": 0.10,
    "strong_reference_reflection_coverage": 0.30,
}
_POSITION_ONLY_RANKING_WEIGHTS = {
    "peak_position_agreement": 0.60,
    "strongest_observed_peak_hit_fraction": 0.30,
    "unweighted_reference_line_coverage": 0.10,
}


def candidate_ranking_profile(*, use_intensity: bool = True) -> dict[str, object]:
    """Return the immutable-by-convention ranking profile for report provenance."""

    weights = _CU_RANKING_WEIGHTS if use_intensity else _POSITION_ONLY_RANKING_WEIGHTS
    return {
        "algorithm_version": CANDIDATE_RANKING_VERSION,
        "strongest_observed_peak_count": STRONGEST_OBSERVED_PEAK_COUNT,
        "strongest_reference_reflection_count": STRONGEST_REFERENCE_REFLECTION_COUNT,
        "strongest_observed_peak_metric": (
            "observed_intensity_weighted_coverage" if use_intensity else "unweighted_hit_fraction"
        ),
        "relative_intensity_scope": "matched_top_ten_observed_peaks" if use_intensity else "unsupported",
        "intensity_comparison": "supported" if use_intensity else "unsupported",
        "weights": dict(weights),
        "score_semantics": "deterministic candidate ranking; not a probability or certainty",
    }


def candidate_retention_profile() -> dict[str, object]:
    """Describe the bounded shortlist rule included in analysis identity."""

    return {
        "algorithm_version": FITTER_SHORTLIST_VERSION,
        "global_rank_share": FITTER_SHORTLIST_GLOBAL_SHARE,
        "strongest_observed_peak_count": STRONGEST_OBSERVED_PEAK_COUNT,
        "selection": "global-rank-quota then round-robin strongest-peak support",
        "score_semantics": "deterministic retention policy; not a probability or certainty",
    }


class ReferenceStore(Protocol):
    def __iter__(self) -> Iterable[ReferencePhase]: ...

    def iter_candidates(
        self,
        peaks: Iterable[Peak],
        radiation: Radiation,
        tolerance_deg: float,
    ) -> Iterable[ReferencePhase]: ...


@dataclass(frozen=True)
class _LineMatch:
    expected_deg: float
    observed: Peak
    observed_index: int
    reference_line_index: int
    position_error: float
    intensity_score: float


def _nearest_matches(
    peaks: tuple[Peak, ...],
    reference: ReferencePhase,
    radiation: Radiation,
    tolerance_deg: float,
    *,
    use_intensity: bool,
) -> tuple[_LineMatch, ...]:
    ordered_peaks = tuple(sorted(peaks, key=lambda peak: peak.position_deg))
    spectral_components = radiation_spectral_components(radiation)
    predicted_max = max(
        (
            line.relative_intensity * component_weight
            for line in reference.lines
            for _wavelength, component_weight in spectral_components
        ),
        default=1.0,
    )
    # All line/peak distances are computed in one numpy pass (bit-identical
    # float64 subtraction and abs). The greedy assignment itself is unchanged:
    # lines in the same order, each taking the closest still-available peak
    # within tolerance, ties to the lowest peak index.
    observed_max = max(max((peak.intensity for peak in peaks), default=1.0), 1e-12)
    matches: list[_LineMatch] = []
    if not ordered_peaks:
        return ()
    indexed_lines = tuple(enumerate(reference.lines))
    ordered_lines = (
        sorted(indexed_lines, key=lambda item: (-item[1].relative_intensity, item[0]))
        if use_intensity
        else sorted(indexed_lines, key=lambda item: (item[1].d_spacing_angstrom, item[0]))
    )
    rows: list[tuple[int, ReferenceLine, float, float]] = []
    for line_index, line in ordered_lines:
        for wavelength, component_weight in spectral_components:
            try:
                expected = two_theta_from_wavelength(line.d_spacing_angstrom, wavelength)
            except ValueError:
                continue
            rows.append((line_index, line, component_weight, expected))
    if not rows:
        return ()
    positions = np.fromiter((peak.position_deg for peak in ordered_peaks), dtype=np.float64, count=len(ordered_peaks))
    expected_values = np.fromiter((row[3] for row in rows), dtype=np.float64, count=len(rows))
    distances = np.abs(positions[None, :] - expected_values[:, None])
    within = distances <= tolerance_deg
    candidate_rows = np.flatnonzero(within.any(axis=1))
    available = [True] * len(ordered_peaks)
    for row_number in candidate_rows.tolist():
        line_index, line, component_weight, expected = rows[row_number]
        row_distances = distances[row_number]
        index = -1
        error = 0.0
        for candidate in np.flatnonzero(within[row_number]).tolist():
            if not available[candidate]:
                continue
            distance = float(row_distances[candidate])
            if index < 0 or distance < error:
                index = candidate
                error = distance
        if index < 0:
            continue
        observed = ordered_peaks[index]
        available[index] = False
        if use_intensity:
            observed_norm = observed.intensity / observed_max
            expected_norm = (line.relative_intensity * component_weight) / max(predicted_max, 1e-12)
            intensity_score = max(
                0.0,
                1.0
                - abs(math.log(max(observed_norm, 1e-6) / max(expected_norm, 1e-6)))
                / math.log(20.0),
            )
        else:
            intensity_score = 0.0
        matches.append(_LineMatch(expected, observed, index, line_index, error, intensity_score))
    return tuple(matches)


def _strongest_observed_peak_indices(peaks: tuple[Peak, ...]) -> frozenset[int]:
    """Return position-ordered indices for the strongest measured peaks."""

    if not peaks:
        return frozenset()
    ordered_peaks = tuple(sorted(peaks, key=lambda peak: peak.position_deg))
    strongest = tuple(
        sorted(
            enumerate(ordered_peaks),
            key=lambda item: (-max(float(item[1].intensity), 0.0), item[1].position_deg, item[0]),
        )[:STRONGEST_OBSERVED_PEAK_COUNT]
    )
    return frozenset(index for index, _peak in strongest)


def _strong_observed_peak_hit_fraction(
    peaks: tuple[Peak, ...], matches: tuple[_LineMatch, ...]
) -> float:
    """Count how many of the ten strongest observed peaks this phase matches."""

    strongest_indices = _strongest_observed_peak_indices(peaks)
    if not strongest_indices:
        return 0.0
    matched_indices = {match.observed_index for match in matches}
    return sum(index in matched_indices for index in strongest_indices) / len(strongest_indices)


def _strong_observed_peak_intensity_weighted_coverage(
    peaks: tuple[Peak, ...], matches: tuple[_LineMatch, ...]
) -> float:
    """Weight covered top-ten observed peaks by their measured peak heights."""

    strongest_indices = _strongest_observed_peak_indices(peaks)
    if not strongest_indices:
        return 0.0
    strongest_weights = {
        index: max(float(peak.intensity), 0.0)
        for index, peak in enumerate(tuple(sorted(peaks, key=lambda peak: peak.position_deg)))
        if index in strongest_indices
    }
    total_weight = math.fsum(strongest_weights.values())
    if total_weight <= 0.0:
        return _strong_observed_peak_hit_fraction(peaks, matches)
    matched_indices = {match.observed_index for match in matches}
    covered_weight = math.fsum(
        weight for index, weight in strongest_weights.items() if index in matched_indices
    )
    return covered_weight / total_weight


def _top_observed_intensity_agreement(
    peaks: tuple[Peak, ...], matches: tuple[_LineMatch, ...]
) -> float:
    """Compare relative intensities only for matches among the strongest observations."""

    strongest_indices = _strongest_observed_peak_indices(peaks)
    scores = tuple(match.intensity_score for match in matches if match.observed_index in strongest_indices)
    return sum(scores) / len(scores) if scores else 0.0


def _strong_reference_reflection_coverage(
    expected_lines: tuple[ReferenceLine, ...], matches: tuple[_LineMatch, ...]
) -> float:
    """Measure matched intensity weight among the strongest reference lines in range."""

    if not expected_lines:
        return 0.0
    strongest = tuple(
        sorted(
            enumerate(expected_lines),
            key=lambda item: (-max(float(item[1].relative_intensity), 0.0), item[0]),
        )[:STRONGEST_REFERENCE_REFLECTION_COUNT]
    )
    if not strongest:
        return 0.0
    matched_indices = {match.reference_line_index for match in matches}
    weights = tuple(max(float(line.relative_intensity), 0.0) for _, line in strongest)
    total_weight = math.fsum(weights)
    if total_weight <= 0.0:
        return sum(index in matched_indices for index, _ in strongest) / len(strongest)
    matched_weight = math.fsum(
        weight for (index, _line), weight in zip(strongest, weights, strict=True) if index in matched_indices
    )
    return matched_weight / total_weight


LATTICE_SCALE_GRID_POINTS = 25


def best_d_spacing_scale(
    lines: tuple[ReferenceLine, ...],
    peaks: tuple[Peak, ...],
    radiation: Radiation,
    tolerance_deg: float,
    scale_tolerance: float,
    *,
    strongest_lines: int = 12,
) -> float:
    """Isotropic d-spacing scale that best aligns strong lines with peaks.

    Scores each scale on a grid by intensity-weighted coverage of the
    reference's strongest lines and of the observed peaks (both within
    ``tolerance_deg``). Ties prefer the scale closest to 1.
    """

    if scale_tolerance <= 0.0 or not lines or not peaks:
        return 1.0
    strong = sorted(lines, key=lambda line: -line.relative_intensity)[:strongest_lines]
    d_values = np.array([line.d_spacing_angstrom for line in strong], dtype=float)
    line_weights = np.array([max(line.relative_intensity, 0.0) for line in strong], dtype=float)
    if line_weights.sum() <= 0:
        return 1.0
    line_weights /= line_weights.sum()
    observed = np.array([peak.position_deg for peak in peaks], dtype=float)
    observed_weights = np.array([max(peak.intensity, 0.0) for peak in peaks], dtype=float)
    observed_weights = observed_weights / max(float(observed_weights.sum()), 1e-12)
    scales = np.linspace(1.0 - scale_tolerance, 1.0 + scale_tolerance, LATTICE_SCALE_GRID_POINTS)
    wavelengths = [wavelength for wavelength, _weight in radiation_spectral_components(radiation)]
    best_score = -1.0
    best_scale = 1.0
    for wavelength in wavelengths[:1]:
        argument = wavelength / (2.0 * d_values[None, :] * scales[:, None])
        valid = argument < 1.0
        predicted = np.where(valid, np.degrees(2.0 * np.arcsin(np.clip(argument, 0.0, 1.0))), np.nan)
        distance = np.abs(observed[None, :, None] - predicted[:, None, :])
        hits = np.nan_to_num(distance, nan=np.inf) <= tolerance_deg
        score = (hits.any(axis=1) * line_weights[None, :]).sum(axis=1) + (
            hits.any(axis=2) * observed_weights[None, :]
        ).sum(axis=1)
        order = np.lexsort((np.abs(scales - 1.0), -score))
        if float(score[order[0]]) > best_score:
            best_score = float(score[order[0]])
            best_scale = float(scales[order[0]])
    return best_scale


def _status(score: float, matched: int) -> str:
    if matched < 2 or score < 0.35:
        return "unresolved"
    if score >= 0.75:
        return "supported"
    return "tentative"


def select_fitter_shortlist(
    ranked_matches: Iterable[CandidateMatch],
    peaks: Iterable[Peak],
    *,
    limit: int,
) -> tuple[tuple[CandidateMatch, ...], dict[str, object]]:
    """Keep global leaders and reserve bounded slots for strong-peak evidence.

    The first 70% of a truncated fitter budget follows the global candidate
    ranking. The remaining slots are filled round-robin from candidates that
    match distinct members of the ten strongest observed peaks. This prevents
    the global score alone from removing all candidates that explain a major
    measured peak, without increasing the number of expensive fitter inputs.
    Final ordering stays in global rank order so downstream runs remain stable.
    """

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")
    ranked = tuple(ranked_matches)
    observed = tuple(sorted(peaks, key=lambda peak: peak.position_deg))
    # Candidate IDs should be unique, but keeping the first ranked instance
    # makes this helper deterministic for third-party ReferenceStore inputs.
    unique_ranked: list[CandidateMatch] = []
    seen_ids: set[str] = set()
    for match in ranked:
        if match.reference_id not in seen_ids:
            unique_ranked.append(match)
            seen_ids.add(match.reference_id)
    ranked = tuple(unique_ranked)

    truncated = len(ranked) > limit
    # A one-slot budget cannot preserve both the global leader and a diversity
    # nomination. In that case, keep the globally highest-ranked candidate.
    global_quota = (
        min(
            len(ranked),
            limit
            if limit == 1
            else math.floor(limit * FITTER_SHORTLIST_GLOBAL_SHARE + 1e-12),
        )
        if truncated
        else min(len(ranked), limit)
    )
    requested_reserve = limit - global_quota if truncated else 0
    selected_ids = {match.reference_id for match in ranked[:global_quota]}
    peak_assignments: list[dict[str, object]] = []
    reserve_added = 0

    strongest_peaks = tuple(
        index
        for index, _peak in sorted(
            enumerate(observed),
            key=lambda item: (-max(float(item[1].intensity), 0.0), item[1].position_deg, item[0]),
        )[:STRONGEST_OBSERVED_PEAK_COUNT]
    )
    queues = tuple(
        tuple(match for match in ranked if index in match.matched_observed_peak_indices)
        for index in strongest_peaks
    )
    queue_positions = [0 for _ in queues]
    queue_assignments: list[list[str]] = [[] for _ in queues]
    reserve_quota = limit - global_quota

    while reserve_added < reserve_quota:
        added_this_round = False
        for queue_index, queue in enumerate(queues):
            position = queue_positions[queue_index]
            while position < len(queue) and queue[position].reference_id in selected_ids:
                position += 1
            queue_positions[queue_index] = position
            if position >= len(queue):
                continue
            match = queue[position]
            queue_positions[queue_index] += 1
            selected_ids.add(match.reference_id)
            queue_assignments[queue_index].append(match.reference_id)
            reserve_added += 1
            added_this_round = True
            if reserve_added >= reserve_quota:
                break
        if not added_this_round:
            break

    selected_in_rank_order = [match for match in ranked if match.reference_id in selected_ids]
    fallback_count = 0
    if len(selected_in_rank_order) < limit:
        selected_set = {match.reference_id for match in selected_in_rank_order}
        fallback = [match for match in ranked if match.reference_id not in selected_set]
        fallback_count = min(limit - len(selected_in_rank_order), len(fallback))
        selected_in_rank_order.extend(fallback[:fallback_count])

    for queue_index, observed_index in enumerate(strongest_peaks):
        if not queue_assignments[queue_index]:
            continue
        peak = observed[observed_index]
        peak_assignments.append(
            {
                "position_deg": float(peak.position_deg),
                "intensity": float(peak.intensity),
                "candidate_ids": list(queue_assignments[queue_index]),
            }
        )

    receipt: dict[str, object] = {
        "algorithm_version": FITTER_SHORTLIST_VERSION,
        "global_rank_share": FITTER_SHORTLIST_GLOBAL_SHARE,
        "strongest_observed_peak_count": min(len(observed), STRONGEST_OBSERVED_PEAK_COUNT),
        "budget": limit,
        "global_rank_quota": global_quota,
        "global_rank_selected_count": min(global_quota, len(ranked)),
        "peak_diversity_reserve": reserve_quota,
        "peak_diversity_selected_count": reserve_added,
        "fallback_global_fill_count": fallback_count,
        "selected_reference_ids": [match.reference_id for match in selected_in_rank_order],
        "peak_assignments": peak_assignments,
    }
    return tuple(selected_in_rank_order), receipt


def match_references(
    peaks: Iterable[Peak],
    references: ReferenceStore,
    radiation: Radiation,
    *,
    tolerance_deg: float = 0.20,
    limit: int = 10,
    scan_range_deg: tuple[float, float] | None = None,
    use_intensity: bool = True,
    collapse_groups: bool = True,
    d_scale_tolerance: float = 0.0,
) -> tuple[CandidateMatch, ...]:
    """Rank reference phases against detected peaks.

    ``peaks`` is a sparse representation of a scan, so its extrema are not a
    reliable proxy for the acquired angular range.  Callers that still have
    the full pattern should provide ``scan_range_deg``; this makes unobserved
    reference reflections inside the measured range count as missing evidence
    instead of silently removing them from the denominator.  ``collapse_groups``
    is enabled for standalone ranking compatibility; analysis orchestration
    disables it until the on-demand equivalence resolver has recorded every
    member that contributed evidence.
    """

    if not math.isfinite(tolerance_deg) or tolerance_deg <= 0:
        raise ValueError("tolerance_deg must be a positive finite number")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if not isinstance(collapse_groups, bool):
        raise ValueError("collapse_groups must be a boolean")
    resolved_range = _validate_scan_range(scan_range_deg)
    observed = tuple(peaks)
    observed_in_range = (
        tuple(
            peak
            for peak in observed
            if resolved_range is None
            or resolved_range[0] <= peak.position_deg <= resolved_range[1]
        )
        if observed
        else ()
    )
    candidates: list[CandidateMatch] = []
    candidate_provider = getattr(references, "iter_candidates", None)
    reference_iter = (
        candidate_provider(observed, radiation, tolerance_deg)
        if callable(candidate_provider)
        else references
    )
    line_in_range = _line_range_predicate(observed, radiation, resolved_range)
    seen_reference_ids: set[str] = set()
    for reference in reference_iter:
        # A store may expose duplicate records for one logical reference ID.
        # Keep the first record consistently so scoring and later CIF lookup
        # cannot disagree about which structure that ID represents.
        if reference.reference_id in seen_reference_ids:
            continue
        seen_reference_ids.add(reference.reference_id)
        expected_in_range = _lines_in_range(reference, line_in_range)
        if not observed or not expected_in_range:
            candidates.append(
                CandidateMatch(
                    reference_id=reference.reference_id,
                    name=reference.name,
                    formula=reference.formula,
                    score=0.0,
                    status="unresolved",
                    matched_peaks=0,
                    expected_peaks=len(expected_in_range),
                    coverage=0.0,
                    position_rmse_deg=None,
                    evidence=("No observed peaks or no reference lines in the measured range.",),
                    duplicate_group_id=reference.duplicate_group_id,
                    equivalence_group_id=reference.equivalence_group_id,
                    parent_family_group_id=reference.parent_family_group_id,
                    equivalence_kind=reference.equivalence_kind,
                    equivalence_confidence=reference.equivalence_confidence,
                    equivalence_member_ids=(reference.reference_id,),
                    space_group=reference.space_group,
                    matched_observed_peak_indices=(),
                )
            )
            continue
        d_scale = best_d_spacing_scale(
            expected_in_range, observed_in_range, radiation, tolerance_deg, d_scale_tolerance
        )
        if d_scale != 1.0:
            expected_in_range = tuple(
                ReferenceLine(line.d_spacing_angstrom * d_scale, line.relative_intensity, line.hkl)
                for line in expected_in_range
            )
        scoped_reference = ReferencePhase(
            reference_id=reference.reference_id,
            formula=reference.formula,
            name=reference.name,
            space_group=reference.space_group,
            lines=expected_in_range,
            source=reference.source,
            cod_entry_url=reference.cod_entry_url,
            cod_entry_id=reference.cod_entry_id,
            cod_block_id=reference.cod_block_id,
            source_snapshot_id=reference.source_snapshot_id,
            source_manifest_sha256=reference.source_manifest_sha256,
            source_path=reference.source_path,
            source_cif_sha256=reference.source_cif_sha256,
            duplicate_group_id=reference.duplicate_group_id,
            equivalence_group_id=reference.equivalence_group_id,
            parent_family_group_id=reference.parent_family_group_id,
            equivalence_kind=reference.equivalence_kind,
            equivalence_confidence=reference.equivalence_confidence,
        )
        matches = _nearest_matches(
            observed_in_range,
            scoped_reference,
            radiation,
            tolerance_deg,
            use_intensity=use_intensity,
        )
        # A resolved K-alpha doublet can match two observed maxima for one
        # crystallographic reflection. Report independent reflections here;
        # observed signal coverage is counted separately by observed peak ID.
        matched_count = len({match.reference_line_index for match in matches})
        coverage = matched_count / max(len(expected_in_range), 1)
        matches_by_line: dict[int, list[_LineMatch]] = {}
        for match in matches:
            matches_by_line.setdefault(match.reference_line_index, []).append(match)
        if matches_by_line:
            # Average spectral components within a reflection before averaging
            # reflections, so a resolved Kα doublet cannot double its positional
            # contribution or distort the reported RMSE.
            line_position_scores = tuple(
                math.fsum(
                    math.exp(-0.5 * (match.position_error / max(tolerance_deg, 1e-9)) ** 2)
                    for match in line_matches
                )
                / len(line_matches)
                for line_matches in matches_by_line.values()
            )
            line_mean_squared_errors = tuple(
                math.fsum(match.position_error**2 for match in line_matches) / len(line_matches)
                for line_matches in matches_by_line.values()
            )
            position_score = math.fsum(line_position_scores) / len(line_position_scores)
            position_rmse = math.sqrt(math.fsum(line_mean_squared_errors) / len(line_mean_squared_errors))
        else:
            position_score = 0.0
            position_rmse = None
        intensity_score = _top_observed_intensity_agreement(observed_in_range, matches)
        strong_peak_hit_fraction = _strong_observed_peak_hit_fraction(observed_in_range, matches)
        if use_intensity:
            strong_peak_intensity_coverage = _strong_observed_peak_intensity_weighted_coverage(
                observed_in_range,
                matches,
            )
            strong_reference_coverage = _strong_reference_reflection_coverage(expected_in_range, matches)
            score = (
                _CU_RANKING_WEIGHTS["peak_position_agreement"] * position_score
                + _CU_RANKING_WEIGHTS["strongest_observed_peak_intensity_weighted_coverage"]
                * strong_peak_intensity_coverage
                + _CU_RANKING_WEIGHTS["relative_intensity_agreement"] * intensity_score
                + _CU_RANKING_WEIGHTS["strong_reference_reflection_coverage"] * strong_reference_coverage
            )
        else:
            unweighted_line_coverage = coverage
            score = (
                _POSITION_ONLY_RANKING_WEIGHTS["peak_position_agreement"] * position_score
                + _POSITION_ONLY_RANKING_WEIGHTS["strongest_observed_peak_hit_fraction"] * strong_peak_hit_fraction
                + _POSITION_ONLY_RANKING_WEIGHTS["unweighted_reference_line_coverage"]
                * unweighted_line_coverage
            )
        score = max(0.0, min(1.0, score))
        evidence = tuple(
            f"{match.observed.position_deg:.3f}° observed vs {match.expected_deg:.3f}° expected"
            for match in sorted(matches, key=lambda item: item.observed.intensity, reverse=True)[:5]
        )
        candidates.append(
            CandidateMatch(
                reference_id=reference.reference_id,
                name=reference.name,
                formula=reference.formula,
                score=score,
                status=_status(score, matched_count),
                matched_peaks=matched_count,
                expected_peaks=len(expected_in_range),
                coverage=coverage,
                position_rmse_deg=position_rmse,
                evidence=evidence,
                duplicate_group_id=reference.duplicate_group_id,
                equivalence_group_id=reference.equivalence_group_id,
                parent_family_group_id=reference.parent_family_group_id,
                equivalence_kind=reference.equivalence_kind,
                equivalence_confidence=reference.equivalence_confidence,
                equivalence_member_ids=(reference.reference_id,),
                space_group=reference.space_group,
                matched_observed_peak_indices=tuple(
                    sorted({match.observed_index for match in matches})
                ),
                d_spacing_scale=d_scale,
            )
        )
    ranked = sorted(candidates, key=lambda item: (-item.score, item.reference_id))
    if not collapse_groups:
        return tuple(ranked[:limit])
    unique: dict[str, CandidateMatch] = {}
    for candidate in ranked:
        group = candidate.equivalence_group_id or candidate.duplicate_group_id or candidate.reference_id
        if group not in unique:
            unique[group] = candidate
    return tuple(list(unique.values())[:limit])


def _validate_scan_range(
    scan_range_deg: tuple[float, float] | None,
) -> tuple[float, float] | None:
    if scan_range_deg is None:
        return None
    if (
        not isinstance(scan_range_deg, tuple)
        or len(scan_range_deg) != 2
        or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in scan_range_deg)
    ):
        raise ValueError("scan_range_deg must be a two-value tuple")
    lower, upper = (float(value) for value in scan_range_deg)
    if not math.isfinite(lower) or not math.isfinite(upper) or not 0.0 <= lower < upper <= 180.0:
        raise ValueError("scan_range_deg must be finite and satisfy 0 <= min < max <= 180")
    return lower, upper


def _line_range_predicate(
    observed: tuple[Peak, ...],
    radiation: Radiation,
    scan_range_deg: tuple[float, float] | None,
):
    """``_line_in_range`` with bounds and spectral components resolved once."""

    if scan_range_deg is not None:
        lower, upper = scan_range_deg
    elif not observed:
        return lambda _d_spacing: True
    else:
        lower = min(peak.position_deg for peak in observed) - 1.0
        upper = max(peak.position_deg for peak in observed) + 1.0
    wavelengths = tuple(wavelength for wavelength, _weight in radiation_spectral_components(radiation))

    def predicate(d_spacing: float) -> bool:
        try:
            angles = tuple(two_theta_from_wavelength(d_spacing, wavelength) for wavelength in wavelengths)
        except ValueError:
            return False
        return any(lower <= angle <= upper for angle in angles)

    predicate.cache_key = (float(lower), float(upper), wavelengths)  # type: ignore[attr-defined]
    return predicate


_IN_RANGE_LINES_CACHE = IdentityLRU(8000)


def _lines_in_range(reference: ReferencePhase, line_in_range) -> tuple[ReferenceLine, ...]:
    key = getattr(line_in_range, "cache_key", None)
    if key is None:
        return tuple(line for line in reference.lines if line_in_range(line.d_spacing_angstrom))
    return _IN_RANGE_LINES_CACHE.get_or_compute(
        reference,
        key,
        lambda: tuple(line for line in reference.lines if line_in_range(line.d_spacing_angstrom)),
    )


