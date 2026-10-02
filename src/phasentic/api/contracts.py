from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from phasentic.domain.models import (
    AnalysisSettings,
    AngleUnit,
    analysis_mode_controls,
    CalibrationResult,
    Geometry,
    InstrumentMetadata,
    KAlphaTreatment,
)
from phasentic.acquisition.calibration import validate_calibration_provenance
from phasentic.presets import chemistry_elements, validated_preset


def _instrument_from_payload(value: Any) -> InstrumentMetadata:
    if not isinstance(value, Mapping):
        raise ValueError("instrument must be a JSON object")
    allowed = {
        "vendor",
        "model",
        "geometry",
        "radiation",
        "k_alpha_treatment",
        "goniometer_radius_mm",
        "sample_displacement_mm",
        "notes",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"Unknown instrument field(s): {', '.join(sorted(unknown))}")
    if not isinstance(value.get("vendor"), str) or not isinstance(value.get("model"), str):
        raise ValueError("Instrument vendor and model must be strings")
    for field_name in ("radiation", "notes"):
        if field_name in value and not isinstance(value[field_name], str):
            raise ValueError(f"Instrument {field_name} must be a string")
    try:
        geometry = Geometry(str(value.get("geometry", Geometry.REFLECTION_BRAGG_BRENTANO.value)))
        k_alpha_treatment = KAlphaTreatment(
            str(value.get("k_alpha_treatment", KAlphaTreatment.AUTO_FROM_SOURCE.value))
        )
        instrument = InstrumentMetadata(
            vendor=str(value["vendor"]),
            model=str(value["model"]),
            geometry=geometry,
            radiation=str(value.get("radiation", "Cu Ka")),
            k_alpha_treatment=k_alpha_treatment,
            goniometer_radius_mm=(
                None
                if value.get("goniometer_radius_mm") is None
                else float(value["goniometer_radius_mm"])
            ),
            sample_displacement_mm=float(value.get("sample_displacement_mm", 0.0)),
            notes=str(value.get("notes", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Instrument metadata has invalid types or values") from exc
    instrument.validate()
    return instrument


def settings_from_payload(payload: Mapping[str, Any]) -> AnalysisSettings:
    """Parse only known analysis controls from a JSON request."""

    allowed = {
        "radiation",
        "angle_unit",
        "reference_source",
        "peak_tolerance_deg",
        "min_prominence_fraction",
        "max_peaks",
        "background_window_points",
        "peak_detection",
        "background_window_deg",
        "peak_min_snr",
        "peak_min_width_deg",
        "peak_smoothing_window_deg",
        "peak_min_relative_prominence",
        "reference_limit",
        "allowed_elements",
        "instrument",
        "calibration",
        "analysis_mode",
        "residual_candidate_queries",
        "max_phases",
        "candidate_pool",
        "candidate_lookup_budget",
        "candidate_retrieval_mode",
        "retained_branches",
        "min_independent_evidence",
        "min_objective_improvement",
        "complexity_penalty",
        "ambiguity_margin",
        "abstain_when_ambiguous",
        "oxidizing_synthesis",
        "missing_intensity_max",
        "inactive_scale_relative_tolerance",
        "profile_width_deg",
        "profile_width_mode",
        "profile_eta",
        "zero_shift_max_deg",
        "zero_shift_step_deg",
        "displacement_search_max_deg",
        "displacement_tolerance_deg",
        "lattice_scale_tolerance",
        "d_spacing_scale_tolerance",
        "max_fit_attempts",
        "swap_fit_attempt_budget",
        "matching_two_theta_max_deg",
    }
    payload = dict(payload)
    preset = payload.pop("preset", None)
    chemistry = payload.pop("chemistry", None)
    if chemistry:
        payload["allowed_elements"] = list(chemistry_elements(chemistry))
    if preset is not None:
        if preset != "validated":
            raise ValueError("preset must be 'validated'")
        if not payload.get("allowed_elements"):
            raise ValueError("the validated preset needs the sample chemistry (precursor and target formulas)")
        kept = {"radiation", "angle_unit", "reference_source", "allowed_elements", "instrument", "calibration"}
        payload = {**validated_preset(), **{key: value for key, value in payload.items() if key in kept}}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"Unknown analysis setting(s): {', '.join(sorted(unknown))}")
    base = AnalysisSettings()
    values = dict(payload)
    if "angle_unit" in values:
        try:
            values["angle_unit"] = AngleUnit(str(values["angle_unit"]))
        except ValueError as exc:
            raise ValueError("Unsupported angle unit") from exc
    if "reference_source" in values and values["reference_source"] not in {"demo", "pow_cod"}:
        raise ValueError("reference_source must be 'demo' or 'pow_cod'")
    if "analysis_mode" in values:
        try:
            internal_mode, residual_queries = analysis_mode_controls(values["analysis_mode"])
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if "residual_candidate_queries" in values:
            requested_queries = values["residual_candidate_queries"]
            if not isinstance(requested_queries, bool):
                raise ValueError("residual_candidate_queries must be boolean")
            if requested_queries != residual_queries:
                raise ValueError("analysis_mode conflicts with residual_candidate_queries")
        values["analysis_mode"] = internal_mode
        values["residual_candidate_queries"] = residual_queries
    if "instrument" in values:
        values["instrument"] = _instrument_from_payload(values["instrument"])
    if values.get("allowed_elements") is not None:
        from phasentic.domain.formula import normalize_elements

        raw_elements = values["allowed_elements"]
        if isinstance(raw_elements, str) or not isinstance(raw_elements, (list, tuple)):
            raise ValueError("allowed_elements must be a list of element symbols")
        values["allowed_elements"] = normalize_elements(raw_elements)
    if "calibration" in values:
        if values["calibration"] is None:
            values["calibration"] = None
        elif not isinstance(values["calibration"], Mapping):
            raise ValueError("calibration must be a JSON object")
        else:
            values["calibration"] = CalibrationResult.from_dict(dict(values["calibration"]))
            if values["calibration"].status.value == "passed":
                validate_calibration_provenance(values["calibration"])
    try:
        settings = replace(base, **values)
    except (TypeError, ValueError) as exc:
        raise ValueError("Analysis settings have invalid types") from exc
    settings.validate()
    return settings
