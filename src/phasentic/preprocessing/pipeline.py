from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import math

import numpy as np

from phasentic.domain.models import Peak


@dataclass(frozen=True)
class ProcessedPattern:
    angles_deg: np.ndarray
    raw_intensities: np.ndarray
    background: np.ndarray
    corrected_intensities: np.ndarray
    baseline_fraction: float
    signal_to_noise: float


def _rolling_percentile(values: np.ndarray, window: int, percentile: float) -> np.ndarray:
    window = max(5, int(window))
    if window % 2 == 0:
        window += 1
    half = window // 2
    padded = np.pad(values, (half, half), mode="edge")
    result = np.empty_like(values, dtype=float)
    for index in range(values.size):
        result[index] = np.percentile(padded[index : index + window], percentile)
    return result


def preprocess(
    angles_deg: np.ndarray,
    intensities: np.ndarray,
    *,
    window: int = 31,
    background: np.ndarray | None = None,
) -> ProcessedPattern:
    angles = np.asarray(angles_deg, dtype=float).copy()
    raw = np.asarray(intensities, dtype=float).copy()
    if angles.ndim != 1 or raw.ndim != 1 or angles.size != raw.size or angles.size < 3:
        raise ValueError("Angles and intensities must be one-dimensional arrays of equal length")
    if not np.all(np.isfinite(angles)) or not np.all(np.isfinite(raw)):
        raise ValueError("Angles and intensities must be finite")
    if np.any(np.diff(angles) <= 0):
        raise ValueError("Diffraction angles must be strictly increasing")
    if np.any(raw < 0):
        raise ValueError("Raw intensities cannot be negative")
    if background is None:
        background = _rolling_percentile(raw, window, 20.0)
    else:
        background = np.asarray(background, dtype=float).copy()
        if background.shape != raw.shape or not np.all(np.isfinite(background)):
            raise ValueError("background must be finite and match the intensities")
        background = np.maximum(background, 0.0)
    corrected = np.clip(raw - background, 0.0, None)
    noise = float(np.median(np.abs(corrected - np.median(corrected)))) * 1.4826
    signal = float(np.max(corrected)) if corrected.size else 0.0
    snr = signal / max(noise, 1e-12)
    baseline_fraction = float(np.mean(background) / max(np.mean(raw), 1e-12))
    return ProcessedPattern(angles, raw, background, corrected, baseline_fraction, snr)


def _fallback_peak_indices(values: np.ndarray, minimum_prominence: float) -> list[int]:
    candidates: list[int] = []
    for index in range(1, values.size - 1):
        if values[index] >= values[index - 1] and values[index] > values[index + 1]:
            left = float(np.min(values[max(0, index - 10) : index + 1]))
            right = float(np.min(values[index : min(values.size, index + 11)]))
            if values[index] - max(left, right) >= minimum_prominence:
                candidates.append(index)
    return candidates


def detect_peaks(
    angles_deg: np.ndarray,
    corrected_intensities: np.ndarray,
    *,
    prominence_fraction: float = 0.025,
    max_peaks: int = 40,
) -> tuple[Peak, ...]:
    angles = np.asarray(angles_deg, dtype=float)
    intensities = np.asarray(corrected_intensities, dtype=float)
    if angles.size != intensities.size or angles.size < 3:
        return ()
    peak_height = float(np.max(intensities))
    if not math.isfinite(peak_height) or peak_height <= 0:
        return ()
    minimum_prominence = max(peak_height * prominence_fraction, 1e-12)
    indices: list[int]
    prominences: np.ndarray
    widths: np.ndarray
    try:
        from scipy.signal import find_peaks, peak_widths

        indices_array, properties = find_peaks(intensities, prominence=minimum_prominence)
        indices = [int(index) for index in indices_array]
        prominences = np.asarray(properties.get("prominences", np.zeros(len(indices))), dtype=float)
        widths = peak_widths(intensities, indices_array, rel_height=0.5)[0] if indices else np.array([])
    except Exception:
        indices = _fallback_peak_indices(intensities, minimum_prominence)
        prominences = np.array(
            [intensities[index] - max(np.min(intensities[max(0, index - 10) : index + 1]), np.min(intensities[index : min(intensities.size, index + 11)])) for index in indices],
            dtype=float,
        )
        widths = np.ones(len(indices), dtype=float)
    spacing = float(np.median(np.diff(angles))) if angles.size > 1 else 1.0
    peaks = [
        Peak(
            position_deg=float(angles[index]),
            intensity=float(intensities[index]),
            prominence=float(prominences[offset]),
            width_deg=max(float(widths[offset]) * spacing, spacing),
        )
        for offset, index in enumerate(indices)
    ]
    peaks.sort(key=lambda peak: peak.intensity, reverse=True)
    return tuple(peaks[:max_peaks])


# ---------------------------------------------------------------------------
# Noise-aware detection (remediation step 3.1)
# ---------------------------------------------------------------------------

NOISE_AWARE_PEAK_DETECTION_VERSION = "noise-aware-peaks-1"
PEAK_DETECTION_MODES = ("noise_aware", "legacy")


def _odd_window(points: float, *, minimum: int, maximum: int) -> int:
    window = int(round(points))
    window = max(minimum, min(window, maximum))
    if window % 2 == 0:
        window = window + 1 if window < maximum else window - 1
    return max(window, 3)


def _median_step(angles: np.ndarray) -> float:
    return float(np.median(np.diff(angles)))


def estimate_background_deg(
    angles_deg: np.ndarray,
    raw_intensities: np.ndarray,
    *,
    window_deg: float,
    percentile: float = 20.0,
) -> np.ndarray:
    """Rolling low-percentile background with a window set in degrees 2θ.

    A window defined in points shrinks to a fraction of a degree on finely
    stepped scans and then follows broad peaks, removing real signal. A
    degree-based window keeps the estimate below reflections regardless of
    step size. The percentile curve is then box-smoothed so its steps do not
    create artificial shoulders.
    """

    from scipy.ndimage import percentile_filter, uniform_filter1d

    angles = np.asarray(angles_deg, dtype=float)
    raw = np.asarray(raw_intensities, dtype=float)
    size = _odd_window(window_deg / _median_step(angles), minimum=5, maximum=max(5, raw.size - (1 - raw.size % 2)))
    background = percentile_filter(raw, percentile, size=size, mode="nearest")
    background = uniform_filter1d(background, size=size, mode="nearest")
    return np.minimum(background, np.maximum(raw.max(), 0.0))


def estimate_noise_sigma(
    angles_deg: np.ndarray,
    raw_intensities: np.ndarray,
    *,
    smoothing_points: int,
    local_window_deg: float = 2.0,
) -> tuple[np.ndarray, float]:
    """Return per-point raw noise sigma and the smoothing noise gain.

    The high-frequency residual ``raw - SG(raw)`` is dominated by counting
    noise. Its local median absolute deviation (robust to the few residual
    points on sharp peaks) estimates sigma after correcting for the part of
    the noise the filter keeps. The second value is the factor by which the
    same Savitzky-Golay filter reduces white noise, used to scale thresholds
    applied to the smoothed trace.
    """

    from scipy.ndimage import median_filter
    from scipy.signal import savgol_coeffs, savgol_filter

    angles = np.asarray(angles_deg, dtype=float)
    raw = np.asarray(raw_intensities, dtype=float)
    smoothed = savgol_filter(raw, smoothing_points, 2, mode="interp")
    coefficients = savgol_coeffs(smoothing_points, 2)
    center = float(coefficients[smoothing_points // 2])
    residual_gain = math.sqrt(max(1.0 - center, 1e-6))
    smoothing_gain = math.sqrt(float(np.sum(coefficients**2)))
    residual = np.abs(raw - smoothed)
    size = _odd_window(local_window_deg / _median_step(angles), minimum=5, maximum=max(5, raw.size - (1 - raw.size % 2)))
    sigma = median_filter(residual, size=size, mode="nearest") * 1.4826 / residual_gain
    floor = max(float(np.median(sigma)) * 0.25, 1e-9)
    return np.maximum(sigma, floor), smoothing_gain


def detect_peaks_noise_aware(
    angles_deg: np.ndarray,
    raw_intensities: np.ndarray,
    background: np.ndarray,
    *,
    smoothing_window_deg: float = 0.05,
    min_snr: float = 6.0,
    min_width_deg: float = 0.03,
    min_relative_prominence: float = 0.002,
    max_peaks: int = 80,
    relative_width_gate: float = 0.35,
) -> tuple[tuple[Peak, ...], dict[str, object]]:
    """Detect reflections on a smoothed copy with a noise-based threshold.

    * The raw trace is never modified; a Savitzky-Golay copy is used only to
      locate maxima.
    * A maximum must rise ``min_snr`` noise units (noise of the smoothed
      trace) above its surroundings, and at least ``min_relative_prominence``
      of the strongest peak.
    * Its full width at half prominence must be at least ``min_width_deg``
      and at least ``relative_width_gate`` times the median width of the
      strongest maxima (a data-driven instrument width), so noise
      wiggles narrower than any real reflection in this scan are rejected.
    * Maxima closer than half the stronger peak's width are merged.
    * Peaks are selected by prominence (not height) up to ``max_peaks``.
    * Positions are refined to sub-step precision with a three-point parabola.
    """

    from scipy.signal import find_peaks, savgol_filter

    angles = np.asarray(angles_deg, dtype=float)
    raw = np.asarray(raw_intensities, dtype=float)
    base = np.asarray(background, dtype=float)
    receipt: dict[str, object] = {
        "algorithm_version": NOISE_AWARE_PEAK_DETECTION_VERSION,
        "smoothing": "savitzky-golay order 2 (detection copy only)",
        "smoothing_window_deg": smoothing_window_deg,
        "min_snr": min_snr,
        "min_width_deg": min_width_deg,
        "min_relative_prominence": min_relative_prominence,
        "max_peaks": max_peaks,
        "relative_width_gate": relative_width_gate,
        "selection": "top prominence",
    }
    if angles.size < 7 or raw.size != angles.size or base.size != angles.size:
        receipt.update({"candidate_maxima": 0, "accepted": 0})
        return (), receipt
    step = _median_step(angles)
    smoothing_points = _odd_window(smoothing_window_deg / step, minimum=5, maximum=max(5, min(51, raw.size - (1 - raw.size % 2))))
    sigma, smoothing_gain = estimate_noise_sigma(angles, raw, smoothing_points=smoothing_points)
    smoothed = savgol_filter(raw, smoothing_points, 2, mode="interp") - base
    peak_height = float(np.max(smoothed))
    if not math.isfinite(peak_height) or peak_height <= 0:
        receipt.update({"candidate_maxima": 0, "accepted": 0})
        return (), receipt
    threshold = np.maximum(min_snr * sigma * smoothing_gain, min_relative_prominence * peak_height)
    all_maxima, _ = find_peaks(smoothed)
    indices, properties = find_peaks(
        smoothed,
        prominence=threshold,
        width=max(min_width_deg / step, 1.0),
        rel_height=0.5,
    )
    prominences = np.asarray(properties.get("prominences", np.zeros(len(indices))), dtype=float)
    widths = np.asarray(properties.get("widths", np.ones(len(indices))), dtype=float) * step
    order = np.argsort(-prominences, kind="stable")
    # Instrument width reference: the strongest maxima (at least 20 noise
    # units), up to ten of them; fall back to the three most prominent.
    smoothed_sigma = float(np.median(sigma)) * smoothing_gain
    strong = [position for position in order[:10] if prominences[position] >= 20.0 * smoothed_sigma]
    reference_positions = strong if len(strong) >= 2 else list(order[:3])
    reference_width = float(np.median(widths[reference_positions])) if reference_positions else 0.0
    width_gate = max(min_width_deg, relative_width_gate * reference_width)
    keep = widths >= width_gate
    rejected_narrow = int(np.count_nonzero(~keep))
    order = np.array([position for position in order if keep[position]], dtype=int)
    accepted: list[int] = []
    merged = 0
    for position in order:
        index = int(indices[position])
        if any(
            abs(angles[index] - angles[int(indices[other])]) < 0.5 * widths[other]
            for other in accepted
        ):
            merged += 1
            continue
        accepted.append(int(position))
        if len(accepted) >= max_peaks:
            break
    peaks: list[Peak] = []
    for position in accepted:
        index = int(indices[position])
        center = float(angles[index])
        if 0 < index < angles.size - 1:
            left, middle, right = smoothed[index - 1 : index + 2]
            denominator = left - 2.0 * middle + right
            if denominator < 0:
                offset = 0.5 * (left - right) / denominator
                if abs(offset) <= 1.0:
                    center = float(angles[index] + offset * (angles[index + 1] - angles[index - 1]) / 2.0)
        peaks.append(
            Peak(
                position_deg=center,
                intensity=float(smoothed[index]),
                prominence=float(prominences[position]),
                width_deg=float(widths[position]),
            )
        )
    peaks.sort(key=lambda peak: peak.intensity, reverse=True)
    receipt.update(
        {
            "smoothing_points": smoothing_points,
            "median_noise_sigma": float(np.median(sigma)),
            "smoothed_noise_gain": smoothing_gain,
            "candidate_maxima": int(all_maxima.size),
            "passed_threshold_and_width": int(indices.size),
            "merged_close_maxima": merged,
            "reference_width_deg": reference_width,
            "width_gate_deg": width_gate,
            "rejected_narrow": rejected_narrow,
            "accepted": len(peaks),
            "capped": bool(indices.size - merged > max_peaks),
            "median_accepted_width_deg": float(np.median([peak.width_deg for peak in peaks])) if peaks else None,
        }
    )
    return tuple(peaks), receipt


WIDTH_MODEL_VERSION = "fwhm-a-plus-b-tan-theta-1"


def estimate_width_model(
    peaks: tuple[Peak, ...],
    *,
    doublet_separation: "Callable[[float], float] | None" = None,
    max_peaks: int = 20,
    min_peaks: int = 4,
) -> tuple[tuple[float, float] | None, dict[str, object]]:
    """Fit FWHM(2θ) = a + b·tan(θ) to the most prominent detected peaks.

    ``doublet_separation(two_theta)`` (degrees) optionally removes the
    Kα1/Kα2 splitting that broadens measured widths when the fit renders both
    components separately. The fit is least squares with two rounds of
    outlier rejection (overlapped peaks are wider than the instrument). Returns
    ``None`` with a reason when too few peaks remain.
    """

    receipt: dict[str, object] = {"algorithm_version": WIDTH_MODEL_VERSION}
    strongest = sorted(peaks, key=lambda peak: -peak.prominence)[:max_peaks]
    points: list[tuple[float, float]] = []
    for peak in strongest:
        width = float(peak.width_deg)
        if doublet_separation is not None:
            separation = float(doublet_separation(peak.position_deg))
            width = math.sqrt(max(width * width - (0.5 * separation) ** 2, (0.5 * width) ** 2))
        points.append((math.tan(math.radians(peak.position_deg) / 2.0), width))
    if len(points) < min_peaks:
        receipt.update({"status": "insufficient_peaks", "peak_count": len(points)})
        return None, receipt
    x = np.array([point[0] for point in points])
    y = np.array([point[1] for point in points])
    keep = np.ones(x.size, dtype=bool)
    a, b = float(np.median(y)), 0.0
    for _ in range(3):
        if np.count_nonzero(keep) < min_peaks:
            break
        design = np.column_stack([np.ones(np.count_nonzero(keep)), x[keep]])
        solution, *_ = np.linalg.lstsq(design, y[keep], rcond=None)
        a, b = float(solution[0]), float(solution[1])
        if b < 0.0:  # widths do not shrink with angle; fall back to a constant
            a, b = float(np.median(y[keep])), 0.0
        residual = y - (a + b * x)
        scale = 1.4826 * float(np.median(np.abs(residual[keep]))) or 1e-6
        keep = residual <= 2.5 * scale  # only broad outliers (overlaps) are removed
    a = max(a, 0.01)
    receipt.update(
        {
            "status": "estimated",
            "a_deg": a,
            "b_deg": b,
            "peak_count": int(x.size),
            "peaks_used": int(np.count_nonzero(keep)),
            "fwhm_at_30_deg": a + b * math.tan(math.radians(15.0)),
            "fwhm_at_90_deg": a + b * math.tan(math.radians(45.0)),
            "doublet_correction": doublet_separation is not None,
        }
    )
    return (a, b), receipt
