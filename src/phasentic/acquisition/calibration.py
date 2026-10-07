"""Line-position calibration for reflection Bragg–Brentano scans."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from phasentic.domain.models import (
    CalibrationLine,
    CalibrationResidual,
    CalibrationResult,
    CalibrationStatus,
)
from phasentic.domain.radiation import Radiation, get_radiation, two_theta_from_d
from phasentic.importers import import_pattern
from phasentic.preprocessing.pipeline import detect_peaks, preprocess


@dataclass(frozen=True)
class CalibrationStandard:
    standard_id: str
    name: str
    lines: tuple[tuple[str, float], ...]
    status: str
    material_formula: str
    source_reference: str
    source_url: str
    source_note: str
    lattice_parameter_angstrom: float | None = None
    lattice_parameter_temperature_c: float | None = None
    lattice_parameter_uncertainty_angstrom: float | None = None
    expanded_uncertainty_k: int | None = None
    certificate_id: str | None = None
    license_note: str = ""
    line_derivation: str = ""
    reference_radiation: str | None = None
    reference_wavelength_angstrom: float | None = None
    manifest_sha256: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "standard_id": self.standard_id,
            "name": self.name,
            "status": self.status,
            "material_formula": self.material_formula,
            "source_reference": self.source_reference,
            "source_url": self.source_url,
            "source_note": self.source_note,
            "lattice_parameter_angstrom": self.lattice_parameter_angstrom,
            "lattice_parameter_temperature_c": self.lattice_parameter_temperature_c,
            "lattice_parameter_uncertainty_angstrom": self.lattice_parameter_uncertainty_angstrom,
            "expanded_uncertainty_k": self.expanded_uncertainty_k,
            "certificate_id": self.certificate_id,
            "license_note": self.license_note,
            "line_derivation": self.line_derivation,
            "reference_radiation": self.reference_radiation,
            "reference_wavelength_angstrom": self.reference_wavelength_angstrom,
            "manifest_sha256": self.manifest_sha256,
            "lines": [
                {"label": label, "d_spacing_angstrom": d_spacing}
                for label, d_spacing in self.lines
            ],
        }


_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "resources" / "calibration-standards.json"


def _load_standards() -> dict[str, CalibrationStandard]:
    """Load standards from the versioned manifest instead of source constants."""

    try:
        raw = _MANIFEST_PATH.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("The calibration standard manifest cannot be loaded") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("standards"), list):
        raise RuntimeError("The calibration standard manifest has an invalid schema")
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    standards: dict[str, CalibrationStandard] = {}
    for item in payload["standards"]:
        if not isinstance(item, dict):
            raise RuntimeError("The calibration standard manifest contains an invalid entry")
        try:
            lines = tuple(
                (str(line["label"]), float(line["d_spacing_angstrom"]))
                for line in item["lines"]
            )
            standard = CalibrationStandard(
                standard_id=str(item["standard_id"]),
                name=str(item["name"]),
                lines=lines,
                status=str(item["status"]),
                material_formula=str(item["material_formula"]),
                source_reference=str(item["source_reference"]),
                source_url=str(item["source_url"]),
                source_note=str(item["source_note"]),
                lattice_parameter_angstrom=(
                    None
                    if item.get("lattice_parameter_angstrom") is None
                    else float(item["lattice_parameter_angstrom"])
                ),
                lattice_parameter_temperature_c=(
                    None
                    if item.get("lattice_parameter_temperature_c") is None
                    else float(item["lattice_parameter_temperature_c"])
                ),
                lattice_parameter_uncertainty_angstrom=(
                    None
                    if item.get("lattice_parameter_uncertainty_angstrom") is None
                    else float(item["lattice_parameter_uncertainty_angstrom"])
                ),
                expanded_uncertainty_k=(
                    None
                    if item.get("expanded_uncertainty_k") is None
                    else int(item["expanded_uncertainty_k"])
                ),
                certificate_id=(
                    None if item.get("certificate_id") is None else str(item["certificate_id"])
                ),
                license_note=str(item.get("license_note", "")),
                line_derivation=str(item.get("line_derivation", "")),
                reference_radiation=(
                    None
                    if item.get("reference_radiation") is None
                    else str(item["reference_radiation"])
                ),
                reference_wavelength_angstrom=(
                    None
                    if item.get("reference_wavelength_angstrom") is None
                    else float(item["reference_wavelength_angstrom"])
                ),
                manifest_sha256=manifest_sha256,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("The calibration standard manifest contains an invalid entry") from exc
        if not standard.standard_id.strip() or not standard.lines:
            raise RuntimeError("The calibration standard manifest contains an incomplete entry")
        if any(not label.strip() or not math.isfinite(d) or d <= 0 for label, d in standard.lines):
            raise RuntimeError("The calibration standard manifest contains invalid line positions")
        if standard.standard_id in standards:
            raise RuntimeError(f"Duplicate calibration standard '{standard.standard_id}'")
        standards[standard.standard_id] = standard
    return standards


_STANDARDS = _load_standards()


def get_calibration_standard(standard_id: str) -> CalibrationStandard:
    try:
        return _STANDARDS[standard_id]
    except KeyError as exc:
        raise ValueError(f"Unknown calibration standard '{standard_id}'") from exc


def validate_calibration_provenance(result: CalibrationResult) -> CalibrationStandard:
    """Require a passed result to match the local certified manifest exactly."""

    result.validate()
    standard = get_calibration_standard(result.standard_id)
    if result.status is not CalibrationStatus.PASSED:
        return standard
    if standard.status != "certified":
        raise ValueError("A teaching or unverified standard cannot authorize a passed calibration")
    if (
        result.standard_status != standard.status
        or result.standard_reference != standard.source_reference
        or result.standard_source_url != standard.source_url
        or result.standard_manifest_sha256 != standard.manifest_sha256
        or result.standard_certificate_id != standard.certificate_id
        or not result.standard_scan_sha256
        or len(result.standard_scan_sha256) != 64
    ):
        raise ValueError("Calibration provenance does not match the local certified standard manifest")

    # Recompute every expected line from the selected wavelength scale.  A
    # client may submit a serialized result, so neither the ``passed`` flag nor
    # the expected positions can be trusted without checking them against the
    # immutable standard manifest and the fitted correction.
    preset = get_radiation(result.radiation_key)
    scaled_radiation = Radiation(
        key=preset.key,
        label=preset.label,
        wavelength_angstrom=preset.wavelength_angstrom * result.wavelength_scale,
        ka1_angstrom=preset.ka1_angstrom,
        ka2_angstrom=preset.ka2_angstrom,
    )
    standard_d_values = tuple(float(d_spacing) for _, d_spacing in standard.lines)
    for residual in result.residuals:
        if not any(math.isclose(residual.d_spacing_angstrom, value, rel_tol=0.0, abs_tol=1e-9) for value in standard_d_values):
            raise ValueError("Calibration residual references a d spacing outside the certified standard")
        expected = two_theta_from_d(residual.d_spacing_angstrom, scaled_radiation) + result.zero_shift_deg
        if not math.isclose(expected, residual.expected_two_theta_deg, rel_tol=0.0, abs_tol=1e-7):
            raise ValueError("Calibration expected position does not match the fitted correction")
        if not math.isclose(
            residual.observed_two_theta_deg - expected,
            residual.residual_deg,
            rel_tol=0.0,
            abs_tol=1e-7,
        ):
            raise ValueError("Calibration residual does not match the fitted correction")
    return standard


def fit_calibration(
    lines: tuple[CalibrationLine, ...],
    radiation: str,
    *,
    standard_id: str = "unspecified",
    max_rmse_deg: float = 0.05,
    max_abs_residual_deg: float = 0.10,
    max_wavelength_deviation: float = 0.005,
    standard_scan_sha256: str | None = None,
    match_tolerance_deg: float | None = None,
) -> CalibrationResult:
    """Fit a constant 2θ zero shift and wavelength scale.

    The fitted observation model is
    ``observed_2theta = Bragg(d, lambda * scale) + zero_shift``.
    Sample displacement is recorded separately because its correction depends
    on the instrument radius and sign convention supplied by the instrument.
    """

    preset = get_radiation(radiation)
    if (
        any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or value <= 0
            for value in (max_rmse_deg, max_abs_residual_deg, max_wavelength_deviation)
        )
    ):
        raise ValueError("Calibration quality limits must be positive")
    if match_tolerance_deg is not None and (
        not isinstance(match_tolerance_deg, (int, float))
        or isinstance(match_tolerance_deg, bool)
        or not math.isfinite(float(match_tolerance_deg))
        or not 0.05 <= match_tolerance_deg <= 2.0
    ):
        raise ValueError("match_tolerance_deg must be between 0.05 and 2.0 degrees")
    standard = _STANDARDS.get(standard_id)
    standard_status = standard.status if standard is not None else "unspecified"
    standard_reference = standard.source_reference if standard is not None else None
    standard_source_url = standard.source_url if standard is not None else None
    standard_manifest_sha256 = standard.manifest_sha256 if standard is not None else None
    standard_certificate_id = standard.certificate_id if standard is not None else None
    if len(lines) < 3:
        return CalibrationResult(
            standard_id=standard_id,
            radiation_key=preset.key,
            status=CalibrationStatus.INSUFFICIENT_DATA,
            zero_shift_deg=0.0,
            wavelength_scale=1.0,
            rmse_deg=None,
            max_abs_residual_deg=None,
            # No line was fitted; line_count must match the (empty) residuals
            # or the result fails its own validation when it is sent back.
            line_count=0,
            message=f"Only {len(lines)} standard line(s) detected; at least three non-overlapping lines are required.",
            standard_status=standard_status,
            standard_reference=standard_reference,
            standard_source_url=standard_source_url,
            standard_manifest_sha256=standard_manifest_sha256,
            standard_certificate_id=standard_certificate_id,
            standard_scan_sha256=standard_scan_sha256,
            match_tolerance_deg=match_tolerance_deg,
        )
    d_values = np.asarray([line.d_spacing_angstrom for line in lines], dtype=float)
    observed = np.asarray([line.observed_two_theta_deg for line in lines], dtype=float)
    if (
        not np.all(np.isfinite(d_values))
        or not np.all(np.isfinite(observed))
        or np.any(d_values <= 0)
        or np.any(observed <= 0)
        or np.any(observed >= 180)
        or len(set(float(value) for value in d_values)) != len(d_values)
    ):
        raise ValueError("Calibration lines must have unique, finite d spacings and valid 2θ values")

    try:
        from scipy.optimize import least_squares

        def residual(parameters: np.ndarray) -> np.ndarray:
            zero_shift, scale = parameters
            wavelength = preset.wavelength_angstrom * scale
            arguments = wavelength / (2.0 * d_values)
            if np.any(arguments >= 1.0):
                return np.full_like(observed, 1e3)
            expected = np.degrees(2.0 * np.arcsin(arguments)) + zero_shift
            return expected - observed

        fit = least_squares(
            residual,
            x0=np.array([0.0, 1.0]),
            bounds=(np.array([-2.0, 0.9]), np.array([2.0, 1.1])),
            loss="soft_l1",
            f_scale=0.02,
        )
        if not bool(getattr(fit, "success", False)):
            raise RuntimeError("Calibration optimization did not converge")
        if not hasattr(fit, "x") or np.asarray(fit.x).shape != (2,) or not np.all(np.isfinite(fit.x)):
            raise RuntimeError("Calibration optimizer returned an invalid correction")
        zero_shift, scale = (float(value) for value in fit.x)
    except ImportError as exc:
        raise RuntimeError("SciPy is required for line-position calibration") from exc

    scaled_radiation = Radiation(
        key=preset.key,
        label=preset.label,
        wavelength_angstrom=preset.wavelength_angstrom * scale,
        ka1_angstrom=preset.ka1_angstrom,
        ka2_angstrom=preset.ka2_angstrom,
    )
    expected = np.asarray(
        [two_theta_from_d(float(d), scaled_radiation) + zero_shift for d in d_values],
        dtype=float,
    )
    residuals = observed - expected
    rmse = float(np.sqrt(np.mean(residuals**2)))
    max_abs = float(np.max(np.abs(residuals)))
    passed = (
        rmse <= max_rmse_deg
        and max_abs <= max_abs_residual_deg
        and abs(scale - 1.0) <= max_wavelength_deviation
    )
    status = CalibrationStatus.PASSED if passed else CalibrationStatus.FAILED
    message = (
        "Calibration passed provisional line-position limits."
        if passed
        else "Calibration failed provisional line-position or wavelength limits."
    )
    matched_residuals = tuple(
        CalibrationResidual(
            label=line.label,
            d_spacing_angstrom=line.d_spacing_angstrom,
            observed_two_theta_deg=line.observed_two_theta_deg,
            expected_two_theta_deg=float(expected[index]),
            residual_deg=float(residuals[index]),
        )
        for index, line in enumerate(lines)
    )
    return CalibrationResult(
        standard_id=standard_id,
        radiation_key=preset.key,
        status=status,
        zero_shift_deg=zero_shift,
        wavelength_scale=scale,
        rmse_deg=rmse,
        max_abs_residual_deg=max_abs,
        line_count=len(lines),
        message=message,
        standard_status=standard_status,
        standard_reference=standard_reference,
        standard_source_url=standard_source_url,
        standard_manifest_sha256=standard_manifest_sha256,
        standard_certificate_id=standard_certificate_id,
        standard_scan_sha256=standard_scan_sha256,
        match_tolerance_deg=match_tolerance_deg,
        residuals=matched_residuals,
    )


def calibrate_standard_file(
    path: str | Path,
    standard_id: str,
    radiation: str,
    *,
    match_tolerance_deg: float = 0.50,
) -> CalibrationResult:
    """Detect standard peaks and fit calibration from a local scan file."""

    if not 0.05 <= match_tolerance_deg <= 2.0:
        raise ValueError("match_tolerance_deg must be between 0.05 and 2.0 degrees")
    standard = get_calibration_standard(standard_id)
    pattern = import_pattern(path, radiation=radiation)
    if pattern.angle_unit.value != "two_theta":
        raise ValueError("Calibration standard files must use 2θ coordinates")
    processed = preprocess(
        np.asarray(pattern.angles_deg, dtype=float),
        np.asarray(pattern.intensities, dtype=float),
        window=31,
    )
    peaks = detect_peaks(
        processed.angles_deg,
        processed.corrected_intensities,
        prominence_fraction=0.01,
        max_peaks=100,
    )
    preset = get_radiation(radiation)
    scan_min = min(pattern.angles_deg)
    scan_max = max(pattern.angles_deg)
    lines: list[CalibrationLine] = []
    used_peak_positions: set[float] = set()
    for label, d_spacing in standard.lines:
        # Some standard reflections are inaccessible for long-wavelength
        # anodes, and valid scans may cover only a subset of the standard.  A
        # calibration attempt should account for those lines as unavailable,
        # rather than aborting on the first physically impossible reflection.
        try:
            expected = two_theta_from_d(d_spacing, preset)
        except ValueError:
            continue
        if expected < scan_min - match_tolerance_deg or expected > scan_max + match_tolerance_deg:
            continue
        candidates = [
            peak
            for peak in peaks
            if abs(peak.position_deg - expected) <= match_tolerance_deg
            and peak.position_deg not in used_peak_positions
        ]
        if candidates:
            selected = min(candidates, key=lambda peak: abs(peak.position_deg - expected))
            used_peak_positions.add(selected.position_deg)
            lines.append(CalibrationLine(label, d_spacing, selected.position_deg))
    return fit_calibration(
        tuple(lines),
        radiation,
        standard_id=standard_id,
        standard_scan_sha256=_sha256(Path(path)),
        match_tolerance_deg=match_tolerance_deg,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
