"""Boundary validation shared by CLI and HTTP layers."""

from __future__ import annotations

from pathlib import Path

from .models import AnalysisSettings
from .radiation import get_radiation


ALLOWED_EXTENSIONS = frozenset({".xy", ".xrdml", ".raw"})
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def validate_input_path(path: Path, max_bytes: int = MAX_UPLOAD_BYTES) -> Path:
    """Validate a user-selected local file without exposing host details."""

    candidate = Path(path)
    if not candidate.is_file():
        raise ValueError("The selected diffraction file could not be found")
    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file extension; use .xy, .xrdml, or .raw")
    try:
        size = candidate.stat().st_size
    except OSError as exc:
        raise ValueError("The selected diffraction file cannot be inspected") from exc
    if size > max_bytes:
        raise ValueError(f"The selected diffraction file exceeds the {max_bytes // (1024 * 1024)} MiB limit")
    return candidate


def validate_settings(settings: AnalysisSettings) -> AnalysisSettings:
    settings.validate()
    get_radiation(settings.radiation)
    return settings
