"""Radiation presets and Bragg-law conversions.

The matcher stores reference lines as d spacings so the selected anode is
applied at analysis time.  This prevents a Cu-only reference table from being
silently reused for Co, Cr, Mo, or Ag radiation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from functools import lru_cache
from typing import Mapping


@dataclass(frozen=True)
class Radiation:
    key: str
    label: str
    wavelength_angstrom: float
    ka1_angstrom: float | None = None
    ka2_angstrom: float | None = None
    ka2_to_ka1_intensity_ratio: float | None = None


_PRESETS: Mapping[str, Radiation] = {
    "cu_ka": Radiation("cu_ka", "Cu Kα", 1.5406, 1.54056, 1.54439),
    "co_ka": Radiation("co_ka", "Co Kα", 1.78897, 1.788965, 1.792850),
    "cr_ka": Radiation("cr_ka", "Cr Kα", 2.28970, 2.28970, 2.29361),
    "mo_ka": Radiation("mo_ka", "Mo Kα", 0.71073, 0.70930, 0.71359),
    "ag_ka": Radiation("ag_ka", "Ag Kα", 0.55942, 0.55936, 0.56381),
}


def _normalise_key(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")


def get_radiation(value: str | Radiation) -> Radiation:
    """Return a known radiation preset, rejecting ambiguous values."""

    if isinstance(value, Radiation):
        return value
    key = _normalise_key(value)
    aliases = {
        "cu_k_a": "cu_ka",
        "cu_kalpha": "cu_ka",
        "cuka": "cu_ka",
        "co_k_a": "co_ka",
        "coka": "co_ka",
        "cr_k_a": "cr_ka",
        "crka": "cr_ka",
        "mo_k_a": "mo_ka",
        "moka": "mo_ka",
        "ag_k_a": "ag_ka",
        "agka": "ag_ka",
    }
    key = aliases.get(key, key)
    try:
        return _PRESETS[key]
    except KeyError as exc:
        choices = ", ".join(sorted(preset.label for preset in _PRESETS.values()))
        raise ValueError(f"Unknown radiation '{value}'. Choose one of: {choices}.") from exc


def two_theta_from_d(d_spacing_angstrom: float, radiation: Radiation | str) -> float:
    """Calculate 2θ in degrees from d and the selected wavelength."""

    if not math.isfinite(d_spacing_angstrom) or d_spacing_angstrom <= 0:
        raise ValueError("d spacing must be a positive finite number")
    wavelength = get_radiation(radiation).wavelength_angstrom
    return two_theta_from_wavelength(d_spacing_angstrom, wavelength)


@lru_cache(maxsize=1 << 18)
def two_theta_from_wavelength(d_spacing_angstrom: float, wavelength_angstrom: float) -> float:
    """Calculate 2θ for a d spacing and one explicit spectral component.

    Pure and deterministic, so results are memoized: the same reference lines
    are converted repeatedly by range filtering, line matching, QualX ranking
    and residual re-queries. Invalid inputs still raise on every call.
    """

    if not math.isfinite(d_spacing_angstrom) or d_spacing_angstrom <= 0:
        raise ValueError("d spacing must be a positive finite number")
    if not math.isfinite(wavelength_angstrom) or wavelength_angstrom <= 0:
        raise ValueError("wavelength_angstrom must be positive and finite")
    argument = wavelength_angstrom / (2.0 * d_spacing_angstrom)
    if argument > 1.0:
        raise ValueError("The selected wavelength cannot diffract from this d spacing")
    return math.degrees(2.0 * math.asin(argument))


def radiation_spectral_components(radiation: Radiation | str) -> tuple[tuple[float, float], ...]:
    """Return wavelength/relative-weight pairs for one reference reflection.

    Presets and text scans remain single-wavelength by default. A doublet is
    used only when its K-alpha-2/K-alpha-1 ratio is explicit.
    """

    selected = get_radiation(radiation)
    ratio = selected.ka2_to_ka1_intensity_ratio
    if ratio is None:
        return ((selected.wavelength_angstrom, 1.0),)
    if (
        not math.isfinite(ratio)
        or ratio < 0.0
        or ratio > 1.0
        or selected.ka1_angstrom is None
        or selected.ka2_angstrom is None
        or not math.isfinite(selected.ka1_angstrom)
        or not math.isfinite(selected.ka2_angstrom)
        or selected.ka1_angstrom <= 0.0
        or selected.ka2_angstrom <= 0.0
    ):
        raise ValueError("The selected radiation has invalid K-alpha doublet metadata")
    if ratio == 0.0:
        return ((selected.ka1_angstrom, 1.0),)
    return ((selected.ka1_angstrom, 1.0), (selected.ka2_angstrom, ratio))


def d_from_two_theta(two_theta_deg: float, radiation: Radiation | str) -> float:
    """Calculate d in Å from a 2θ angle and the selected wavelength."""

    if not math.isfinite(two_theta_deg) or not 0.0 < two_theta_deg < 180.0:
        raise ValueError("2θ must be between 0 and 180 degrees")
    theta = math.radians(two_theta_deg / 2.0)
    return get_radiation(radiation).wavelength_angstrom / (2.0 * math.sin(theta))


