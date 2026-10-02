"""Shared parsing checks for text and XML importers."""

from __future__ import annotations

import math
from pathlib import Path


def validate_series(angles: list[float], intensities: list[float]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if len(angles) != len(intensities) or len(angles) < 3:
        raise ValueError("A diffraction pattern needs at least three angle/intensity pairs")
    if any(not math.isfinite(value) for value in [*angles, *intensities]):
        raise ValueError("Diffraction data contains a non-finite value")
    if any(not 0.0 <= angle <= 180.0 for angle in angles):
        raise ValueError("2θ coordinates must be between 0 and 180 degrees")
    if any(intensity < 0 for intensity in intensities):
        raise ValueError("Raw intensities cannot be negative")
    if any(right <= left for left, right in zip(angles, angles[1:])):
        raise ValueError("Diffraction angles must be strictly increasing")
    return tuple(angles), tuple(intensities)


def parse_two_columns(path: Path) -> tuple[tuple[float, ...], tuple[float, ...]]:
    angles: list[float] = []
    intensities: list[float] = []
    text = path.read_text(encoding="utf-8-sig", errors="strict")
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "!", ";", "//")):
            continue
        fields = line.replace(",", " ").split()
        if len(fields) < 2:
            raise ValueError(f"line {line_number} does not contain two numeric columns")
        try:
            angles.append(float(fields[0]))
            intensities.append(float(fields[1]))
        except ValueError as exc:
            raise ValueError(f"line {line_number} contains non-numeric data") from exc
    return validate_series(angles, intensities)
