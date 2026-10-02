"""Sample-displacement estimation before phase matching.

In Bragg-Brentano geometry a specimen surface displaced from the goniometer
axis shifts every reflection by approximately ``D * cos(theta)`` (degrees 2θ).
The Precursor scans show systematic shifts of +0.2 to +0.35° 2θ, larger than
the matching tolerance, so the true phases were being rejected before any
scoring. This module estimates ``D`` from the strongest measured peaks and a
bounded set of chemically plausible candidates, using the consensus of the
best-matching candidates (all phases in one specimen share one displacement).
The estimate is accepted only when it clearly improves agreement over no
correction; otherwise ``D = 0`` is returned with the reason recorded.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

from phasentic.domain.models import Peak, ReferencePhase
from phasentic.domain.radiation import Radiation, two_theta_from_wavelength

DISPLACEMENT_ESTIMATION_VERSION = "displacement-consensus-1"


def displacement_shift(two_theta_deg: np.ndarray | float, displacement_deg: float) -> np.ndarray | float:
    """Angular shift D*cos(theta) at the given 2θ (degrees)."""

    return displacement_deg * np.cos(np.radians(np.asarray(two_theta_deg, dtype=float) / 2.0))


def correct_angles(two_theta_deg: np.ndarray, displacement_deg: float) -> np.ndarray:
    """Map measured 2θ to displacement-corrected 2θ (monotonic for |D| < 1°)."""

    angles = np.asarray(two_theta_deg, dtype=float)
    return angles - displacement_shift(angles, displacement_deg)


def estimate_sample_displacement(
    peaks: Sequence[Peak],
    candidates: Iterable[ReferencePhase],
    radiation: Radiation,
    scan_range_deg: tuple[float, float],
    *,
    max_displacement_deg: float = 0.45,
    step_deg: float = 0.01,
    tolerance_deg: float = 0.06,
    top_peaks: int = 12,
    top_candidates: int = 10,
    reference_lines: int = 10,
    min_improvement: float = 0.10,
    scale_tolerance: float = 0.0,
    scale_points: int = 13,
) -> tuple[float, dict[str, object]]:
    grid = np.round(np.arange(-max_displacement_deg, max_displacement_deg + step_deg / 2, step_deg), 6)
    zero_index = int(np.argmin(np.abs(grid)))
    strongest = sorted(peaks, key=lambda peak: -peak.prominence)[:top_peaks]
    receipt: dict[str, object] = {
        "algorithm_version": DISPLACEMENT_ESTIMATION_VERSION,
        "model": "delta_2theta = D * cos(theta)",
        "max_displacement_deg": max_displacement_deg,
        "step_deg": step_deg,
        "tolerance_deg": tolerance_deg,
        "top_peaks": len(strongest),
        "per_candidate_scale_tolerance": scale_tolerance,
    }
    if len(strongest) < 3:
        receipt.update({"status": "insufficient_peaks", "displacement_deg": 0.0})
        return 0.0, receipt
    observed = np.array([peak.position_deg for peak in strongest], dtype=float)
    weights = np.array([max(peak.prominence, 0.0) for peak in strongest], dtype=float)
    weights = weights / max(float(weights.sum()), 1e-12)
    lower, upper = scan_range_deg
    curves: list[tuple[float, np.ndarray, str, str]] = []
    wavelength = radiation.wavelength_angstrom
    for phase in candidates:
        positions: list[float] = []
        intensities: list[float] = []
        for line in sorted(phase.lines, key=lambda item: -item.relative_intensity):
            try:
                position = two_theta_from_wavelength(line.d_spacing_angstrom, wavelength)
            except ValueError:
                continue
            if lower <= position <= upper:
                positions.append(position)
                intensities.append(max(float(line.relative_intensity), 0.0))
            if len(positions) >= reference_lines:
                break
        if len(positions) < 2 or sum(intensities) <= 0:
            continue
        predicted = np.array(positions)
        line_weights = np.array(intensities) / sum(intensities)
        # A per-candidate isotropic cell scale (doping, solid solution) shifts
        # lines ~ tan(theta); the specimen displacement shifts them ~ cos(theta).
        scales = (
            np.linspace(1.0 - scale_tolerance, 1.0 + scale_tolerance, scale_points)
            if scale_tolerance > 0
            else np.array([1.0])
        )
        theta = np.radians(predicted / 2.0)
        # d -> d*s changes 2theta by about -2*tan(theta)*(s-1) radians.
        scaled = predicted[None, :] - np.degrees(2.0 * np.tan(theta))[None, :] * (scales[:, None] - 1.0)
        shifted = scaled[:, None, :] + grid[None, :, None] * np.cos(theta)[None, None, :]
        hits = np.abs(observed[None, None, :, None] - shifted[:, :, None, :]) < tolerance_deg
        observed_coverage = (hits.any(axis=3) * weights[None, None, :]).sum(axis=2)
        reference_coverage = (hits.any(axis=2) * line_weights[None, None, :]).sum(axis=2)
        curve = (observed_coverage * reference_coverage).max(axis=0)
        curves.append((float(curve.max()), curve, phase.reference_id, phase.formula))
    if not curves:
        receipt.update({"status": "no_candidates", "displacement_deg": 0.0})
        return 0.0, receipt
    curves.sort(key=lambda item: (-item[0], item[2]))
    leaders = curves[:top_candidates]
    consensus = np.sum([best * curve for best, curve, _id, _formula in leaders], axis=0)
    peak_value = float(consensus.max())
    plateau = np.flatnonzero(consensus >= peak_value - 1e-12)
    displacement = float(np.round(np.mean(grid[plateau]), 4))
    at_zero = float(consensus[zero_index])
    normaliser = max(sum(best for best, *_rest in leaders), 1e-12)
    improvement = (peak_value - at_zero) / normaliser
    accepted = improvement >= min_improvement and abs(displacement) > step_deg / 2
    receipt.update(
        {
            "status": "accepted" if accepted else "rejected_small_improvement",
            "displacement_deg": displacement if accepted else 0.0,
            "candidate_displacement_deg": displacement,
            "consensus_score": peak_value / normaliser,
            "consensus_score_at_zero": at_zero / normaliser,
            "improvement": improvement,
            "candidate_count": len(curves),
            "leaders": [
                {
                    "reference_id": reference_id,
                    "formula": formula,
                    "best_score": best,
                    "best_displacement_deg": float(grid[int(np.argmax(curve))]),
                }
                for best, curve, reference_id, formula in leaders[:5]
            ],
            "semantics": "instrument/specimen geometry correction; not a lattice refinement",
        }
    )
    return (displacement if accepted else 0.0), receipt


__all__ = [
    "DISPLACEMENT_ESTIMATION_VERSION",
    "correct_angles",
    "displacement_shift",
    "estimate_sample_displacement",
]
