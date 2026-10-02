"""Validated importers for common powder diffractometer exports."""

from __future__ import annotations

from pathlib import Path

from phasentic.acquisition.gsas2 import GSAS2AdapterError
from phasentic.domain.models import Pattern
from phasentic.domain.validation import validate_input_path

from .xy import parse_xy
from .xrdml import parse_xrdml
from .raw import parse_raw


class ImportErrorDetail(ValueError):
    """Safe, user-facing import error that omits local filesystem details."""


def import_pattern(
    path: str | Path,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    radiation: str = "Cu Ka",
) -> Pattern:
    try:
        candidate = validate_input_path(Path(path), max_bytes=max_bytes)
    except ValueError as exc:
        raise ImportErrorDetail(str(exc)) from exc
    try:
        suffix = candidate.suffix.lower()
        if suffix == ".xy":
            return parse_xy(candidate)
        if suffix == ".xrdml":
            return parse_xrdml(candidate)
        if suffix == ".raw":
            return parse_raw(candidate, radiation=radiation)
        raise ImportErrorDetail("Unsupported diffraction file extension")
    except ImportErrorDetail:
        raise
    except (OSError, UnicodeError, ValueError, GSAS2AdapterError) as exc:
        raise ImportErrorDetail(f"Could not parse the selected diffraction file: {exc}") from exc


__all__ = ["ImportErrorDetail", "import_pattern"]
