from __future__ import annotations

from pathlib import Path

from phasentic.domain.models import AngleUnit, Pattern

from .common import parse_two_columns


def parse_xy(path: Path) -> Pattern:
    angles, intensities = parse_two_columns(path)
    return Pattern(
        angles_deg=angles,
        intensities=intensities,
        source_name=path.name,
        source_format="xy",
        angle_unit=AngleUnit.TWO_THETA,
        metadata={"parser": "two-column-text", "comment_prefixes": ["#", "!", ";", "//"]},
    )
