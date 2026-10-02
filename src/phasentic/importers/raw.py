"""Safe RAW importer.

Vendor RAW is a family of binary formats rather than one stable standard. The
alpha intentionally supports the documented two-column ASCII export variant
and routes binary data through the validated GSAS-II mapping boundary without
making this parser guess at bytes.
"""

from __future__ import annotations

from pathlib import Path

from phasentic.domain.models import AngleUnit, Pattern
from phasentic.acquisition.gsas2 import GSAS2Adapter

from .common import parse_two_columns


def parse_raw(path: Path, *, radiation: str = "Cu Ka") -> Pattern:
    raw = path.read_bytes()
    # A vendor RAW binary is not a text format with a few unusual bytes.  The
    # core importer only accepts the documented two-column ASCII export and
    # delegates anything containing NUL/non-UTF-8 bytes to the explicit
    # GSAS-II mapping boundary.
    if b"\x00" in raw:
        return GSAS2Adapter().import_raw(path, radiation=radiation)
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return GSAS2Adapter().import_raw(path, radiation=radiation)
    angles, intensities = parse_two_columns(path)
    return Pattern(
        angles_deg=angles,
        intensities=intensities,
        source_name=path.name,
        source_format="raw-ascii",
        angle_unit=AngleUnit.TWO_THETA,
        metadata={"parser": "two-column-ascii-raw", "binary_adapter": "not-configured"},
    )
