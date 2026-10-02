"""Immutable-ish data contracts exchanged between the analysis layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from copy import deepcopy
from typing import Any

from .radiation import get_radiation


class AngleUnit(str, Enum):
    TWO_THETA = "two_theta"
    TWO_ALPHA = "two_alpha"
    Q = "q"
    D_SPACING = "d_spacing"


class Geometry(str, Enum):
    REFLECTION_BRAGG_BRENTANO = "reflection_bragg_brentano"


class KAlphaTreatment(str, Enum):
    AUTO_FROM_SOURCE = "auto_from_source"
    SINGLE_EFFECTIVE = "single_effective"
    DOUBLETS_RESOLVED = "doublets_resolved"
    UNKNOWN = "unknown"


class CalibrationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INSUFFICIENT_DATA = "insufficient_data"
    UNVERIFIED = "unverified"


PUBLIC_ANALYSIS_MODES = ("screening", "joint_no_requery", "full_mixture")
"""Stable public names for the WP-4 analysis variants."""

PUBLIC_ANALYSIS_MODE_ALIASES = {"mixture": "full_mixture"}
"""Historical public spellings retained for backwards-compatible requests."""


def normalize_analysis_mode(value: str) -> str:
    """Return the canonical public name for an analysis-mode request.

    The application keeps the older internal ``mixture`` flag pair so stored
    reports remain readable.  Requests at the CLI/API boundary use the three
    explicit WP-4 names; ``mixture`` is retained as an alias for the complete
    residual-query variant.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError("analysis_mode must be a non-empty string")
    canonical = PUBLIC_ANALYSIS_MODE_ALIASES.get(value, value)
    if canonical not in PUBLIC_ANALYSIS_MODES:
        choices = ", ".join((*PUBLIC_ANALYSIS_MODES, *PUBLIC_ANALYSIS_MODE_ALIASES))
        raise ValueError(f"analysis_mode must be one of: {choices}")
    return canonical


def analysis_mode_controls(value: str) -> tuple[str, bool]:
    """Map a public analysis variant to the persisted internal controls."""

    canonical = normalize_analysis_mode(value)
    if canonical == "screening":
        return "screening", False
    return "mixture", canonical == "full_mixture"


@dataclass(frozen=True)
class InstrumentMetadata:
    vendor: str
    model: str
    geometry: Geometry = Geometry.REFLECTION_BRAGG_BRENTANO
    radiation: str = "Cu Ka"
    k_alpha_treatment: KAlphaTreatment = KAlphaTreatment.AUTO_FROM_SOURCE
    goniometer_radius_mm: float | None = None
    sample_displacement_mm: float = 0.0
    notes: str = ""

    def validate(self) -> "InstrumentMetadata":
        if not self.vendor.strip() or not self.model.strip():
            raise ValueError("Instrument vendor and model are required")
        if self.geometry is not Geometry.REFLECTION_BRAGG_BRENTANO:
            raise ValueError("The alpha supports reflection Bragg–Brentano geometry only")
        if not isinstance(self.k_alpha_treatment, KAlphaTreatment):
            raise ValueError("k_alpha_treatment must be a supported K-alpha treatment")
        get_radiation(self.radiation)
        if self.goniometer_radius_mm is not None and (
            not math.isfinite(self.goniometer_radius_mm) or self.goniometer_radius_mm <= 0
        ):
            raise ValueError("goniometer_radius_mm must be positive when provided")
        if not math.isfinite(self.sample_displacement_mm) or abs(self.sample_displacement_mm) > 10.0:
            raise ValueError("sample_displacement_mm must be finite and within ±10 mm")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "model": self.model,
            "geometry": self.geometry.value,
            "radiation": self.radiation,
            "k_alpha_treatment": self.k_alpha_treatment.value,
            "goniometer_radius_mm": self.goniometer_radius_mm,
            "sample_displacement_mm": self.sample_displacement_mm,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CalibrationLine:
    label: str
    d_spacing_angstrom: float
    observed_two_theta_deg: float


@dataclass(frozen=True)
class CalibrationResidual:
    """One matched standard reflection retained for auditability."""

    label: str
    d_spacing_angstrom: float
    observed_two_theta_deg: float
    expected_two_theta_deg: float
    residual_deg: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "label": self.label,
            "d_spacing_angstrom": self.d_spacing_angstrom,
            "observed_two_theta_deg": self.observed_two_theta_deg,
            "expected_two_theta_deg": self.expected_two_theta_deg,
            "residual_deg": self.residual_deg,
        }


@dataclass(frozen=True)
class CalibrationResult:
    standard_id: str
    radiation_key: str
    status: CalibrationStatus
    zero_shift_deg: float
    wavelength_scale: float
    rmse_deg: float | None
    max_abs_residual_deg: float | None
    line_count: int
    message: str
    standard_status: str = "unspecified"
    standard_reference: str | None = None
    standard_source_url: str | None = None
    standard_manifest_sha256: str | None = None
    standard_certificate_id: str | None = None
    standard_scan_sha256: str | None = None
    match_tolerance_deg: float | None = None
    residuals: tuple[CalibrationResidual, ...] = ()
    algorithm_version: str = "line-position-calibration-0.2"

    def validate(self) -> "CalibrationResult":
        """Validate a persisted correction and its derived residual evidence.

        A JSON calibration result is an input boundary.  Its ``passed`` flag
        and summary metrics must therefore agree with the retained line-level
        observations; callers must not trust those values independently.
        Manifest/source authentication is performed by
        ``validate_calibration_provenance`` once the standard is available.
        """

        if not isinstance(self.standard_id, str) or not self.standard_id.strip():
            raise ValueError("Calibration standard_id must be a non-empty string")
        if not isinstance(self.radiation_key, str) or not self.radiation_key.strip():
            raise ValueError("Calibration radiation_key must be a non-empty string")
        if not isinstance(self.status, CalibrationStatus):
            raise ValueError("Calibration status is invalid")
        if not isinstance(self.line_count, int) or isinstance(self.line_count, bool) or self.line_count < 0:
            raise ValueError("Calibration line_count must be a non-negative integer")
        if not math.isfinite(self.zero_shift_deg):
            raise ValueError("Calibration zero shift must be finite")
        if not math.isfinite(self.wavelength_scale) or not 0.9 <= self.wavelength_scale <= 1.1:
            raise ValueError("Calibration wavelength scale must be between 0.9 and 1.1")
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version.strip():
            raise ValueError("Calibration algorithm_version must be a non-empty string")
        for field_name in ("rmse_deg", "max_abs_residual_deg"):
            value = getattr(self, field_name)
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"Calibration {field_name} must be non-negative and finite")
        if self.match_tolerance_deg is not None and (
            not math.isfinite(self.match_tolerance_deg)
            or not 0.05 <= self.match_tolerance_deg <= 2.0
        ):
            raise ValueError("Calibration match_tolerance_deg must be between 0.05 and 2.0 degrees")

        for field_name in ("standard_manifest_sha256", "standard_scan_sha256"):
            value = getattr(self, field_name)
            if value is not None and (
                len(value) != 64
                or any(character not in "0123456789abcdef" for character in value.lower())
            ):
                raise ValueError(f"Calibration {field_name} must be a SHA-256 hexadecimal string")

        if len(self.residuals) != self.line_count:
            raise ValueError("Calibration residual count does not match line_count")
        labels: set[str] = set()
        d_spacings: list[float] = []
        residual_values: list[float] = []
        for residual in self.residuals:
            if not residual.label.strip() or residual.label in labels:
                raise ValueError("Calibration residual labels must be non-empty and unique")
            labels.add(residual.label)
            values = (
                residual.d_spacing_angstrom,
                residual.observed_two_theta_deg,
                residual.expected_two_theta_deg,
                residual.residual_deg,
            )
            if any(not math.isfinite(value) for value in values):
                raise ValueError("Calibration residuals contain non-finite values")
            if residual.d_spacing_angstrom <= 0:
                raise ValueError("Calibration residual d spacings must be positive")
            if any(math.isclose(residual.d_spacing_angstrom, value, rel_tol=0.0, abs_tol=1e-9) for value in d_spacings):
                raise ValueError("Calibration residual d spacings must be unique")
            d_spacings.append(residual.d_spacing_angstrom)
            if not 0.0 < residual.observed_two_theta_deg < 180.0:
                raise ValueError("Calibration observed 2θ values must be between 0 and 180 degrees")
            if not 0.0 < residual.expected_two_theta_deg < 180.0:
                raise ValueError("Calibration expected 2θ values must be between 0 and 180 degrees")
            if not math.isclose(
                residual.observed_two_theta_deg - residual.expected_two_theta_deg,
                residual.residual_deg,
                rel_tol=0.0,
                abs_tol=1e-7,
            ):
                raise ValueError("Calibration residual evidence is internally inconsistent")
            residual_values.append(residual.residual_deg)

        if residual_values:
            calculated_rmse = math.sqrt(sum(value * value for value in residual_values) / len(residual_values))
            calculated_max_abs = max(abs(value) for value in residual_values)
            if self.rmse_deg is None or self.max_abs_residual_deg is None:
                raise ValueError("Calibration residual metrics are missing")
            if not math.isclose(self.rmse_deg, calculated_rmse, rel_tol=0.0, abs_tol=1e-7):
                raise ValueError("Calibration RMSE does not match residual evidence")
            if not math.isclose(self.max_abs_residual_deg, calculated_max_abs, rel_tol=0.0, abs_tol=1e-7):
                raise ValueError("Calibration maximum residual does not match residual evidence")
        elif self.rmse_deg is not None or self.max_abs_residual_deg is not None:
            raise ValueError("Calibration metrics require line-level residual evidence")

        if self.status is CalibrationStatus.PASSED:
            if self.line_count < 3 or len(self.residuals) < 3:
                raise ValueError("A passed calibration requires at least three residual lines")
            if not self.standard_manifest_sha256 or not self.standard_scan_sha256:
                raise ValueError("A passed calibration requires standard and scan hashes")
            if not self.standard_certificate_id:
                raise ValueError("A passed calibration requires a standard certificate identifier")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard_id": self.standard_id,
            "radiation_key": self.radiation_key,
            "status": self.status.value,
            "zero_shift_deg": self.zero_shift_deg,
            "wavelength_scale": self.wavelength_scale,
            "rmse_deg": self.rmse_deg,
            "max_abs_residual_deg": self.max_abs_residual_deg,
            "line_count": self.line_count,
            "message": self.message,
            "standard_status": self.standard_status,
            "standard_reference": self.standard_reference,
            "standard_source_url": self.standard_source_url,
            "standard_manifest_sha256": self.standard_manifest_sha256,
            "standard_certificate_id": self.standard_certificate_id,
            "standard_scan_sha256": self.standard_scan_sha256,
            "match_tolerance_deg": self.match_tolerance_deg,
            "residuals": [residual.to_dict() for residual in self.residuals],
            "algorithm_version": self.algorithm_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CalibrationResult":
        if not isinstance(payload, dict):
            raise ValueError("Invalid calibration result")
        required_string_fields = ("standard_id", "radiation_key", "status")
        if any(not isinstance(payload.get(name), str) for name in required_string_fields):
            raise ValueError("Calibration result identifiers must be strings")
        def _number(value: Any, field_name: str) -> float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Calibration {field_name} must be numeric")
            return float(value)

        def _integer(value: Any, field_name: str) -> int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Calibration {field_name} must be an integer")
            return value

        try:
            status = CalibrationStatus(str(payload["status"]))
            result = cls(
                standard_id=payload["standard_id"],
                radiation_key=payload["radiation_key"],
                status=status,
                zero_shift_deg=_number(payload["zero_shift_deg"], "zero_shift_deg"),
                wavelength_scale=_number(payload["wavelength_scale"], "wavelength_scale"),
                rmse_deg=None if payload.get("rmse_deg") is None else _number(payload["rmse_deg"], "rmse_deg"),
                max_abs_residual_deg=None
                if payload.get("max_abs_residual_deg") is None
                else _number(payload["max_abs_residual_deg"], "max_abs_residual_deg"),
                line_count=_integer(payload["line_count"], "line_count"),
                message=str(payload.get("message", "")),
                standard_status=str(payload.get("standard_status", "unspecified")),
                standard_reference=(
                    None
                    if payload.get("standard_reference") is None
                    else str(payload["standard_reference"])
                ),
                standard_source_url=(
                    None
                    if payload.get("standard_source_url") is None
                    else str(payload["standard_source_url"])
                ),
                standard_manifest_sha256=(
                    None
                    if payload.get("standard_manifest_sha256") is None
                    else str(payload["standard_manifest_sha256"])
                ),
                standard_certificate_id=(
                    None
                    if payload.get("standard_certificate_id") is None
                    else str(payload["standard_certificate_id"])
                ),
                standard_scan_sha256=(
                    None
                    if payload.get("standard_scan_sha256") is None
                    else str(payload["standard_scan_sha256"])
                ),
                match_tolerance_deg=(
                    None
                    if payload.get("match_tolerance_deg") is None
                    else _number(payload["match_tolerance_deg"], "match_tolerance_deg")
                ),
                residuals=tuple(
                    CalibrationResidual(
                        label=str(item["label"]),
                        d_spacing_angstrom=_number(item["d_spacing_angstrom"], "d_spacing_angstrom"),
                        observed_two_theta_deg=_number(item["observed_two_theta_deg"], "observed_two_theta_deg"),
                        expected_two_theta_deg=_number(item["expected_two_theta_deg"], "expected_two_theta_deg"),
                        residual_deg=_number(item["residual_deg"], "residual_deg"),
                    )
                    for item in payload.get("residuals", [])
                ),
                algorithm_version=str(
                    payload.get("algorithm_version", "line-position-calibration-0.2")
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid calibration result") from exc
        try:
            result.validate()
        except ValueError as exc:
            raise ValueError("Calibration result contains an invalid correction") from exc
        return result


@dataclass(frozen=True)
class AnalysisSettings:
    radiation: str = "Cu Ka"
    angle_unit: AngleUnit = AngleUnit.TWO_THETA
    # Narrowed from 0.20 once zero shift and data-estimated widths were added
    # (remediation step 3.3); wide windows admit coincidental matches.
    peak_tolerance_deg: float = 0.10
    min_prominence_fraction: float = 0.025
    max_peaks: int = 40
    background_window_points: int = 31
    # Peak detection. ``noise_aware`` (default) smooths a detection copy,
    # thresholds on estimated counting noise, gates on width and selects by
    # prominence; ``legacy`` keeps the original fraction-of-maximum detector.
    peak_detection: str = "noise_aware"
    background_window_deg: float = 3.0
    peak_min_snr: float = 6.0
    peak_min_width_deg: float = 0.03
    peak_smoothing_window_deg: float = 0.05
    peak_min_relative_prominence: float = 0.002
    reference_limit: int = 10
    # Optional sample-context chemistry constraint: reference phases containing
    # any other element are excluded before ranking. ``None`` disables it.
    allowed_elements: tuple[str, ...] | None = None
    # Synthesis heated in air: oxygen-free phases need a noble metal (or are
    # graphite). Applied together with ``allowed_elements``.
    oxidizing_synthesis: bool = False
    # Reject a candidate phase when more than this fraction of its clearly
    # visible predicted intensity is absent from the scan (1.0 disables).
    missing_intensity_max: float = 1.0
    instrument: InstrumentMetadata | None = None
    calibration: CalibrationResult | None = None
    reference_source: str = "demo"
    # Optional benchmark/evaluation window.  ``None`` preserves the indexed
    # reference range used by ordinary application analyses.
    matching_two_theta_max_deg: float | None = None
    analysis_mode: str = "screening"
    # WP-4F evaluation control.  It is deliberately separate from
    # ``analysis_mode`` so screening and the two mixture variants can be
    # compared without changing the public mixture result schema.
    residual_candidate_queries: bool = False
    max_phases: int = 3
    # ``candidate_pool`` is the expensive mixture-fitter budget.  A separate
    # optional retrieval limit lets a broad lookup be ranked before truncation.
    candidate_pool: int = 100
    candidate_lookup_budget: int | None = None
    candidate_retrieval_mode: str = "bounded_coarse"
    retained_branches: int = 3
    min_independent_evidence: int = 2
    min_objective_improvement: float = 0.02
    # Relative (see mixture query metadata): an extra phase must lower the
    # objective by more than this fraction; alternatives within this relative
    # margin of the best selection score make the result ambiguous.
    complexity_penalty: float = 0.10
    ambiguity_margin: float = 0.05
    # False reports the best hypothesis even when ambiguous (it and its rival
    # stay marked ``ambiguous``); True returns no selection instead.
    abstain_when_ambiguous: bool = True
    inactive_scale_relative_tolerance: float = 1e-6
    profile_width_deg: float = 0.20
    # ``estimated`` fits FWHM = a + b*tan(theta) to the detected peaks and
    # falls back to ``profile_width_deg`` when too few peaks are available.
    profile_width_mode: str = "estimated"
    profile_eta: float = 0.5
    zero_shift_max_deg: float = 0.10
    zero_shift_step_deg: float = 0.02
    # Specimen-displacement search (D*cos(theta)) before matching; 0 disables.
    displacement_search_max_deg: float = 0.60
    displacement_tolerance_deg: float = 0.06
    # Per-phase isotropic d-spacing scale searched during matching (doped,
    # solid-solution or non-stoichiometric phases differ from database cells).
    lattice_scale_tolerance: float = 0.006
    d_spacing_scale_tolerance: float = 0.0
    max_fit_attempts: int = 300
    swap_fit_attempt_budget: int = 25

    @property
    def analysis_variant(self) -> str:
        """Return the canonical public variant represented by these controls."""

        if self.analysis_mode == "screening":
            return "screening"
        if self.analysis_mode == "mixture":
            return "full_mixture" if self.residual_candidate_queries else "joint_no_requery"
        raise ValueError("analysis_mode is invalid; call validate() first")

    @property
    def effective_candidate_lookup_budget(self) -> int:
        """Return the retrieval cap, preserving the old shared-cap default."""

        return self.candidate_pool if self.candidate_lookup_budget is None else self.candidate_lookup_budget

    def validate(self) -> None:
        if not isinstance(self.reference_source, str) or self.reference_source not in {"demo", "pow_cod"}:
            raise ValueError("reference_source must be 'demo', 'pow_cod', or 'cod'")
        if not isinstance(self.radiation, str) or not self.radiation.strip():
            raise ValueError("radiation must be a non-empty string")
        if not isinstance(self.angle_unit, AngleUnit):
            raise ValueError("angle_unit must be a supported AngleUnit")
        if (
            isinstance(self.peak_tolerance_deg, bool)
            or not isinstance(self.peak_tolerance_deg, (int, float))
            or not math.isfinite(float(self.peak_tolerance_deg))
            or not 0.01 <= self.peak_tolerance_deg <= 2.0
        ):
            raise ValueError("peak_tolerance_deg must be between 0.01 and 2.0 degrees")
        if (
            isinstance(self.min_prominence_fraction, bool)
            or not isinstance(self.min_prominence_fraction, (int, float))
            or not math.isfinite(float(self.min_prominence_fraction))
            or not 0.0 < self.min_prominence_fraction <= 1.0
        ):
            raise ValueError("min_prominence_fraction must be in (0, 1]")
        if not isinstance(self.max_peaks, int) or isinstance(self.max_peaks, bool) or not 3 <= self.max_peaks <= 200:
            raise ValueError("max_peaks must be between 3 and 200")
        if (
            not isinstance(self.background_window_points, int)
            or isinstance(self.background_window_points, bool)
            or self.background_window_points < 5
            or self.background_window_points > 10001
            or self.background_window_points % 2 == 0
        ):
            raise ValueError("background_window_points must be odd and at least 5")
        if isinstance(self.missing_intensity_max, bool) or not isinstance(self.missing_intensity_max, (int, float)) or not 0.0 <= float(self.missing_intensity_max) <= 1.0:
            raise ValueError("missing_intensity_max must be between 0 and 1")
        if not isinstance(self.oxidizing_synthesis, bool):
            raise ValueError("oxidizing_synthesis must be a boolean")
        if self.allowed_elements is not None:
            from phasentic.domain.formula import normalize_elements

            if not isinstance(self.allowed_elements, tuple) or normalize_elements(self.allowed_elements) != self.allowed_elements:
                raise ValueError("allowed_elements must be a sorted tuple of known element symbols")
        if self.profile_width_mode not in {"estimated", "fixed"}:
            raise ValueError("profile_width_mode must be 'estimated' or 'fixed'")
        for name, low, high in (
            ("profile_eta", 0.0, 1.0),
            ("zero_shift_max_deg", 0.0, 0.5),
            ("zero_shift_step_deg", 0.001, 0.2),
            ("displacement_search_max_deg", 0.0, 1.0),
            ("displacement_tolerance_deg", 0.01, 0.5),
            ("lattice_scale_tolerance", 0.0, 0.03),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not low <= float(value) <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
        if self.peak_detection not in {"noise_aware", "legacy"}:
            raise ValueError("peak_detection must be 'noise_aware' or 'legacy'")
        for name, low, high in (
            ("background_window_deg", 0.2, 30.0),
            ("peak_min_snr", 1.0, 100.0),
            ("peak_min_width_deg", 0.0, 2.0),
            ("peak_smoothing_window_deg", 0.005, 1.0),
            ("peak_min_relative_prominence", 0.0, 0.5),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not low <= float(value) <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
        if not isinstance(self.reference_limit, int) or isinstance(self.reference_limit, bool) or not 1 <= self.reference_limit <= 100:
            raise ValueError("reference_limit must be between 1 and 100")
        if self.matching_two_theta_max_deg is not None:
            if (
                isinstance(self.matching_two_theta_max_deg, bool)
                or not isinstance(self.matching_two_theta_max_deg, (int, float))
                or not math.isfinite(float(self.matching_two_theta_max_deg))
                or not 0.0 < float(self.matching_two_theta_max_deg) <= 180.0
            ):
                raise ValueError("matching_two_theta_max_deg must be in (0, 180] when configured")
        if self.analysis_mode not in {"screening", "mixture"}:
            raise ValueError("analysis_mode must be 'screening' or 'mixture'")
        if not isinstance(self.residual_candidate_queries, bool):
            raise ValueError("residual_candidate_queries must be boolean")
        if self.analysis_mode != "mixture" and self.residual_candidate_queries:
            raise ValueError("residual_candidate_queries requires analysis_mode='mixture'")
        if not isinstance(self.max_phases, int) or isinstance(self.max_phases, bool) or not 1 <= self.max_phases <= 10:
            raise ValueError("max_phases must be between 1 and 10")
        if not isinstance(self.candidate_pool, int) or isinstance(self.candidate_pool, bool) or not 1 <= self.candidate_pool <= 2000:
            raise ValueError("candidate_pool must be between 1 and 2000")
        if self.candidate_lookup_budget is not None and (
            not isinstance(self.candidate_lookup_budget, int)
            or isinstance(self.candidate_lookup_budget, bool)
            or not 1 <= self.candidate_lookup_budget <= 20000
        ):
            raise ValueError("candidate_lookup_budget must be between 1 and 20000 when configured")
        if self.candidate_retrieval_mode not in {"bounded_coarse", "exhaustive_exact"}:
            raise ValueError("candidate_retrieval_mode must be 'bounded_coarse' or 'exhaustive_exact'")
        if not isinstance(self.retained_branches, int) or isinstance(self.retained_branches, bool) or not 1 <= self.retained_branches <= 10:
            raise ValueError("retained_branches must be between 1 and 10")
        if not isinstance(self.min_independent_evidence, int) or isinstance(self.min_independent_evidence, bool) or not 1 <= self.min_independent_evidence <= 10:
            raise ValueError("min_independent_evidence must be between 1 and 10")
        if isinstance(self.min_objective_improvement, bool) or not isinstance(self.min_objective_improvement, (int, float)) or not math.isfinite(float(self.min_objective_improvement)) or not 0.0 < self.min_objective_improvement <= 1.0:
            raise ValueError("min_objective_improvement must be in (0, 1]")
        if isinstance(self.complexity_penalty, bool) or not isinstance(self.complexity_penalty, (int, float)) or not math.isfinite(float(self.complexity_penalty)) or not 0.0 <= self.complexity_penalty <= 1.0:
            raise ValueError("complexity_penalty must be between 0 and 1")
        if isinstance(self.ambiguity_margin, bool) or not isinstance(self.ambiguity_margin, (int, float)) or not math.isfinite(float(self.ambiguity_margin)) or not 0.0 <= self.ambiguity_margin <= 1.0:
            raise ValueError("ambiguity_margin must be between 0 and 1")
        if not isinstance(self.abstain_when_ambiguous, bool):
            raise ValueError("abstain_when_ambiguous must be a boolean")
        if isinstance(self.inactive_scale_relative_tolerance, bool) or not isinstance(self.inactive_scale_relative_tolerance, (int, float)) or not math.isfinite(float(self.inactive_scale_relative_tolerance)) or not 0.0 < self.inactive_scale_relative_tolerance <= 0.1:
            raise ValueError("inactive_scale_relative_tolerance must be in (0, 0.1]")
        if isinstance(self.profile_width_deg, bool) or not isinstance(self.profile_width_deg, (int, float)) or not math.isfinite(float(self.profile_width_deg)) or not 0.01 <= self.profile_width_deg <= 2.0:
            raise ValueError("profile_width_deg must be between 0.01 and 2.0 degrees")
        if (
            isinstance(self.d_spacing_scale_tolerance, bool)
            or not isinstance(self.d_spacing_scale_tolerance, (int, float))
            or not math.isfinite(float(self.d_spacing_scale_tolerance))
            or not 0.0 <= self.d_spacing_scale_tolerance <= 0.03
        ):
            raise ValueError("d_spacing_scale_tolerance must be between 0 and 0.03")
        if not isinstance(self.max_fit_attempts, int) or isinstance(self.max_fit_attempts, bool) or not 1 <= self.max_fit_attempts <= 10000:
            raise ValueError("max_fit_attempts must be between 1 and 10000")
        if (
            not isinstance(self.swap_fit_attempt_budget, int)
            or isinstance(self.swap_fit_attempt_budget, bool)
            or not 0 <= self.swap_fit_attempt_budget <= 1000
        ):
            raise ValueError("swap_fit_attempt_budget must be between 0 and 1000")
        if self.angle_unit is not AngleUnit.TWO_THETA:
            raise ValueError(
                "The research alpha matcher requires calibrated 2θ input; "
                f"'{self.angle_unit.value}' is metadata-only until a calibration transform is configured."
            )
        selected_radiation = get_radiation(self.radiation).key
        if self.instrument is not None:
            if not isinstance(self.instrument, InstrumentMetadata):
                raise ValueError("instrument must be InstrumentMetadata")
            self.instrument.validate()
            if get_radiation(self.instrument.radiation).key != selected_radiation:
                raise ValueError("Instrument radiation and analysis radiation must match")
        if self.calibration is not None:
            if not isinstance(self.calibration, CalibrationResult):
                raise ValueError("calibration must be CalibrationResult")
            self.calibration.validate()
            if self.calibration.radiation_key != selected_radiation:
                raise ValueError("Calibration radiation and analysis radiation must match")
            if self.calibration.status is CalibrationStatus.PASSED:
                # Import lazily to avoid the calibration module importing this
                # domain model during module initialization.
                from phasentic.acquisition.calibration import validate_calibration_provenance

                validate_calibration_provenance(self.calibration)


@dataclass(frozen=True)
class Pattern:
    angles_deg: tuple[float, ...]
    intensities: tuple[float, ...]
    source_name: str
    source_format: str
    angle_unit: AngleUnit = AngleUnit.TWO_THETA
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def point_count(self) -> int:
        return len(self.angles_deg)


@dataclass(frozen=True)
class Peak:
    position_deg: float
    intensity: float
    prominence: float
    width_deg: float


@dataclass(frozen=True)
class ReferenceLine:
    d_spacing_angstrom: float
    relative_intensity: float
    hkl: str | None = None


@dataclass(frozen=True)
class ReferencePhase:
    reference_id: str
    formula: str
    name: str
    space_group: str
    lines: tuple[ReferenceLine, ...]
    source: str = "demo"
    cod_entry_url: str | None = None
    cod_entry_id: str | None = None
    cod_block_id: str | None = None
    source_snapshot_id: str | None = None
    source_manifest_sha256: str | None = None
    source_path: str | None = None
    source_cif_sha256: str | None = None
    duplicate_group_id: str | None = None
    equivalence_group_id: str | None = None
    parent_family_group_id: str | None = None
    equivalence_kind: str | None = None
    equivalence_confidence: str | None = None


@dataclass(frozen=True)
class CandidateMatch:
    reference_id: str
    name: str
    formula: str
    score: float
    status: str
    matched_peaks: int
    expected_peaks: int
    coverage: float
    position_rmse_deg: float | None
    evidence: tuple[str, ...] = ()
    duplicate_group_id: str | None = None
    equivalence_group_id: str | None = None
    parent_family_group_id: str | None = None
    equivalence_kind: str | None = None
    equivalence_confidence: str | None = None
    # Runtime equivalence resolution keeps the representative visible while
    # retaining every source entry that contributed evidence.  These fields
    # are optional so reports produced by older stores remain readable.
    equivalence_member_ids: tuple[str, ...] = ()
    equivalence_label: str | None = None
    equivalence_resolution: str | None = None
    space_group: str = ""
    # Indices refer to observed peaks sorted by position. This internal support
    # map lets bounded fitter shortlists retain candidates for distinct major
    # measured peaks without recomputing diffraction matches.
    matched_observed_peak_indices: tuple[int, ...] = ()
    # Per-phase isotropic d-spacing scale chosen from peak positions (1.0 =
    # database cell). Screening adjustment only; not a refined lattice.
    d_spacing_scale: float = 1.0


@dataclass(frozen=True)
class InputSummary:
    file_name: str
    file_extension: str
    point_count: int
    angle_min_deg: float
    angle_max_deg: float
    sha256: str


@dataclass(frozen=True)
class QualityReport:
    signal_to_noise: float
    baseline_fraction: float
    warnings: tuple[str, ...]
    checks: dict[str, str]
    calibration_status: str = CalibrationStatus.UNVERIFIED.value
    calibration_rmse_deg: float | None = None


@dataclass(frozen=True)
class AnalysisReport:
    schema_version: str
    analysis_id: str
    decision: str
    input: InputSummary
    radiation_key: str
    radiation_label: str
    angle_unit: str
    peaks: tuple[Peak, ...]
    candidates: tuple[CandidateMatch, ...]
    quality: QualityReport
    provenance: dict[str, Any]
    mixture: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "analysis_id": self.analysis_id,
            "decision": self.decision,
            "input": {
                "file_name": self.input.file_name,
                "file_extension": self.input.file_extension,
                "point_count": self.input.point_count,
                "angle_min_deg": self.input.angle_min_deg,
                "angle_max_deg": self.input.angle_max_deg,
                "sha256": self.input.sha256,
            },
            "radiation": {"key": self.radiation_key, "label": self.radiation_label},
            "angle_unit": self.angle_unit,
            "peaks": [
                {
                    "position_deg": peak.position_deg,
                    "intensity": peak.intensity,
                    "prominence": peak.prominence,
                    "width_deg": peak.width_deg,
                }
                for peak in self.peaks
            ],
            "candidates": [
                {
                    "reference_id": candidate.reference_id,
                    "name": candidate.name,
                    "formula": candidate.formula,
                    "score": candidate.score,
                    "status": candidate.status,
                    "matched_peaks": candidate.matched_peaks,
                    "expected_peaks": candidate.expected_peaks,
                    "coverage": candidate.coverage,
                    "position_rmse_deg": candidate.position_rmse_deg,
                    "evidence": list(candidate.evidence),
                    "duplicate_group_id": candidate.duplicate_group_id,
                    "equivalence_group_id": candidate.equivalence_group_id,
                    "parent_family_group_id": candidate.parent_family_group_id,
                    "equivalence_kind": candidate.equivalence_kind,
                    "equivalence_confidence": candidate.equivalence_confidence,
                    "equivalence_member_ids": list(candidate.equivalence_member_ids),
                    "equivalence_label": candidate.equivalence_label,
                    "equivalence_resolution": candidate.equivalence_resolution,
                    "space_group": candidate.space_group,
                }
                for candidate in self.candidates
            ],
            "quality": {
                "signal_to_noise": self.quality.signal_to_noise,
                "baseline_fraction": self.quality.baseline_fraction,
                "warnings": list(self.quality.warnings),
                "checks": deepcopy(self.quality.checks),
                "calibration_status": self.quality.calibration_status,
                "calibration_rmse_deg": self.quality.calibration_rmse_deg,
            },
            "provenance": deepcopy(self.provenance),
            "mixture": self.mixture.to_dict() if self.mixture is not None else None,
        }
