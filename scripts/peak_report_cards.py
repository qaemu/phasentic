#!/usr/bin/env python3
"""Render per-case peak-detection report cards (legacy vs noise-aware).

Visual audit tool for remediation step 3. Each PNG shows the full scan with
both backgrounds and both peak lists, plus three zoom panels around the
strongest reflections. Labels are not read; the cards show detection only.
Requires the optional ``evaluation`` extra (matplotlib).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phasentic.domain.models import AnalysisSettings  # noqa: E402
from phasentic.importers import import_pattern  # noqa: E402
from phasentic.preprocessing.pipeline import (  # noqa: E402
    detect_peaks,
    detect_peaks_noise_aware,
    estimate_background_deg,
    preprocess,
)


def render(path: Path, output: Path, *, max_angle: float, legacy: dict, settings: AnalysisSettings) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pattern = import_pattern(path)
    angles = np.asarray(pattern.angles_deg, dtype=float)
    raw = np.asarray(pattern.intensities, dtype=float)
    mask = angles <= max_angle
    angles, raw = angles[mask], raw[mask]
    old_processed = preprocess(angles, raw, window=legacy["background_window_points"])
    old_peaks = detect_peaks(
        angles,
        old_processed.corrected_intensities,
        prominence_fraction=legacy["min_prominence_fraction"],
        max_peaks=legacy["max_peaks"],
    )
    background = estimate_background_deg(angles, raw, window_deg=settings.background_window_deg)
    new_peaks, receipt = detect_peaks_noise_aware(
        angles,
        raw,
        background,
        smoothing_window_deg=settings.peak_smoothing_window_deg,
        min_snr=settings.peak_min_snr,
        min_width_deg=settings.peak_min_width_deg,
        min_relative_prominence=settings.peak_min_relative_prominence,
        max_peaks=settings.max_peaks,
    )
    figure = plt.figure(figsize=(15, 8.5), constrained_layout=True)
    grid = figure.add_gridspec(2, 3, height_ratios=[1.3, 1.0])
    top = figure.add_subplot(grid[0, :])

    def draw(axis, lower, upper):
        window = (angles >= lower) & (angles <= upper)
        axis.plot(angles[window], raw[window], color="#8a8a8a", lw=0.6, label="raw counts")
        axis.plot(angles[window], old_processed.background[window], color="#d9534f", lw=1.0, ls=":", label="legacy background (points)")
        axis.plot(angles[window], background[window], color="#1f6fb2", lw=1.2, ls="--", label=f"new background ({settings.background_window_deg:g}°)")
        span = float(raw[window].max() - raw[window].min()) if window.any() else 1.0
        for peak in old_peaks:
            if lower <= peak.position_deg <= upper:
                index = int(np.argmin(np.abs(angles - peak.position_deg)))
                axis.plot(peak.position_deg, raw[index] + 0.06 * span, "v", color="#d9534f", ms=5)
        for peak in new_peaks:
            if lower <= peak.position_deg <= upper:
                index = int(np.argmin(np.abs(angles - peak.position_deg)))
                axis.plot(peak.position_deg, raw[index] + 0.14 * span, "^", color="#2e8b57", ms=6)
        axis.set_xlim(lower, upper)

    draw(top, float(angles[0]), float(angles[-1]))
    top.plot([], [], "v", color="#d9534f", label=f"legacy peaks ({len(old_peaks)}, {sum(p.width_deg < 0.03 for p in old_peaks)} narrower than 0.03°)")
    top.plot([], [], "^", color="#2e8b57", label=f"noise-aware peaks ({len(new_peaks)})")
    top.legend(loc="upper right", fontsize=8)
    top.set_title(f"{path.stem} — median noise σ {receipt.get('median_noise_sigma', 0):.0f} counts, width gate {receipt.get('width_gate_deg', 0):.3f}°")
    top.set_xlabel("2θ (°)")
    strongest = sorted(new_peaks, key=lambda peak: -peak.prominence)[:3]
    for column, peak in enumerate(strongest):
        axis = figure.add_subplot(grid[1, column])
        draw(axis, peak.position_deg - 1.2, peak.position_deg + 1.2)
        axis.set_title(f"zoom {peak.position_deg:.2f}°  FWHM {peak.width_deg:.3f}°", fontsize=9)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=110)
    plt.close(figure)
    return {
        "case": path.stem,
        "legacy_peaks": len(old_peaks),
        "legacy_narrow": sum(peak.width_deg < 0.03 for peak in old_peaks),
        "noise_aware_peaks": len(new_peaks),
        "receipt": receipt,
        "image": output.name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scans", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-angle", type=float, default=100.0)
    parser.add_argument("--legacy-min-prominence-fraction", type=float, default=0.01)
    parser.add_argument("--legacy-background-window-points", type=int, default=51)
    parser.add_argument("--max-peaks", type=int, default=80)
    args = parser.parse_args(argv)
    legacy = {
        "min_prominence_fraction": args.legacy_min_prominence_fraction,
        "background_window_points": args.legacy_background_window_points,
        "max_peaks": args.max_peaks,
    }
    settings = AnalysisSettings(max_peaks=args.max_peaks)
    summary = [
        render(scan, args.output / f"{scan.stem}.png", max_angle=args.max_angle, legacy=legacy, settings=settings)
        for scan in args.scans
    ]
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for item in summary:
        print(item["case"], item["legacy_peaks"], item["legacy_narrow"], item["noise_aware_peaks"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
