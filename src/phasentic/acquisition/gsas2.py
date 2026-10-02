"""Optional GSAS-II vendor import boundary.

The adapter keeps GSAS-II outside the core dependency set. A mapping is
selected from a versioned registry using the binary signature, then the
official ``G2Project.add_powder_histogram`` API is used. No byte-level vendor
guessing is performed by Phasentic itself.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterator

import numpy as np

from phasentic.domain.models import AngleUnit, Pattern
from phasentic.domain.radiation import get_radiation


_MAPPING_PATH = Path(__file__).resolve().parents[1] / "resources" / "gsas2-vendor-mappings.json"


class GSAS2AdapterError(RuntimeError):
    """Named failure at the optional vendor-normalization boundary."""


@dataclass(frozen=True)
class GSAS2Mapping:
    mapping_id: str
    vendor: str
    format: str
    extensions: tuple[str, ...]
    header_signatures: tuple[str, ...]
    gsas2_module: str
    gsas2_format_hint: str
    angle_unit: str
    allowed_scan_types: tuple[str, ...]
    documentation_url: str
    fixture_ids: tuple[str, ...]
    validation_note: str


def gsas2_import_mappings() -> tuple[GSAS2Mapping, ...]:
    """Return the immutable mapping registry loaded from project config."""

    try:
        payload = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
        entries = payload["mappings"]
        return tuple(
            GSAS2Mapping(
                mapping_id=str(item["mapping_id"]),
                vendor=str(item["vendor"]),
                format=str(item["format"]),
                extensions=tuple(str(value).lower() for value in item["extensions"]),
                header_signatures=tuple(str(value) for value in item["header_signatures"]),
                gsas2_module=str(item["gsas2_module"]),
                gsas2_format_hint=str(item["gsas2_format_hint"]),
                angle_unit=str(item["angle_unit"]),
                allowed_scan_types=tuple(str(value) for value in item["allowed_scan_types"]),
                documentation_url=str(item["documentation_url"]),
                fixture_ids=tuple(str(value) for value in item["fixture_ids"]),
                validation_note=str(item["validation_note"]),
            )
            for item in entries
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GSAS2AdapterError("The GSAS-II vendor mapping registry is invalid") from exc


def detect_gsas2_mapping(path: str | Path) -> GSAS2Mapping | None:
    """Select a mapping from a small, explicit vendor header signature."""

    candidate = Path(path)
    try:
        header = candidate.read_bytes()[:16].decode("latin-1", errors="replace")
    except OSError:
        return None
    for mapping in gsas2_import_mappings():
        if any(header.startswith(signature) for signature in mapping.header_signatures):
            return mapping
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _gsas2_path() -> Iterator[None]:
    """Temporarily add an externally installed GSAS-II root to ``sys.path``."""

    configured = os.environ.get("GSASII_PATH", "")
    paths = tuple(value for value in configured.split(os.pathsep) if value)
    inserted: list[str] = []
    for value in reversed(paths):
        if value not in sys.path:
            sys.path.insert(0, value)
            inserted.append(value)
    try:
        yield
    finally:
        for value in inserted:
            if value in sys.path:
                sys.path.remove(value)


def _load_scriptable() -> tuple[Any, str]:
    errors: list[str] = []
    with _gsas2_path():
        for module_name in ("GSASII.GSASIIscriptable", "GSASIIscriptable"):
            try:
                return importlib.import_module(module_name), module_name
            except Exception as exc:  # optional third-party runtime has platform-specific failures
                errors.append(f"{module_name}: {type(exc).__name__}")
    detail = "; ".join(errors)
    raise GSAS2AdapterError(
        "GSAS-II scripting runtime is unavailable. Install the documented optional runtime"
        + (f" ({detail})." if detail else ".")
    )


def _instrument_parameters(radiation: str) -> list[dict[str, object]]:
    preset = get_radiation(radiation)
    lam2 = preset.ka2_angstrom or preset.wavelength_angstrom
    lam1 = preset.ka1_angstrom or preset.wavelength_angstrom
    instrument = {
        "I(L2)/I(L1)": [0.5, 0.5, False],
        "Lam2": [lam2, lam2, False],
        "Source": [preset.key.replace("_", "").replace("ka", "Ka"), "?"],
        "Zero": [0.0, 0.0, False],
        "Lam1": [lam1, lam1, False],
        "Type": ["PXC", "PXC", False],
        "Bank": [1.0, 1.0, False],
        "Polariz.": [0.7, 0.7, False],
    }
    return [instrument, {}]


def _as_float_array(value: Any, *, label: str) -> np.ndarray:
    if hasattr(value, "filled"):
        value = value.filled(0.0)
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise GSAS2AdapterError(f"GSAS-II returned non-numeric {label} data") from exc
    if array.ndim != 1 or array.size < 3 or not np.all(np.isfinite(array)):
        raise GSAS2AdapterError(f"GSAS-II returned invalid {label} data")
    return array


def _comment_metadata(comments: Any) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if not isinstance(comments, (list, tuple)):
        return parsed
    for item in comments:
        text = str(item)
        if "=" in text:
            key, value = text.split("=", 1)
            parsed[key.strip()] = value.strip()
    return parsed


def _normalise_histogram(
    histogram: Any,
    path: Path,
    mapping: GSAS2Mapping,
    *,
    module_name: str,
    module_version: str,
) -> Pattern:
    try:
        data = histogram.data["data"][1]
        angles = _as_float_array(data[0], label="angle")
        intensities = _as_float_array(data[1], label="intensity")
    except (AttributeError, KeyError, IndexError, TypeError) as exc:
        raise GSAS2AdapterError("GSAS-II returned no normalized powder histogram") from exc
    if angles.size != intensities.size:
        raise GSAS2AdapterError("GSAS-II returned angle and intensity arrays with different lengths")
    if np.any(np.diff(angles) <= 0):
        raise GSAS2AdapterError("GSAS-II returned non-monotonic 2θ coordinates")
    if np.any(intensities < 0):
        raise GSAS2AdapterError("GSAS-II returned negative intensities")

    histogram_data = histogram.data
    comments = tuple(str(item) for item in histogram_data.get("Comments", ()))
    comment_fields = _comment_metadata(comments)
    scan_type = next(
        (
            value
            for key, value in comment_fields.items()
            if key.replace(" ", "").casefold() in {"scantype", "scantype"}
        ),
        None,
    )
    if scan_type is not None and scan_type.casefold() not in {
        value.casefold() for value in mapping.allowed_scan_types
    }:
        raise GSAS2AdapterError(
            f"GSAS-II returned unsupported scan type '{scan_type}' for mapping {mapping.mapping_id}."
        )
    sample = histogram_data.get("Sample Parameters", {})
    instrument = histogram_data.get("Instrument Parameters", ({},))[0]
    instrument_summary = {
        key: instrument[key]
        for key in ("Type", "Lam1", "Lam2", "Zero", "Source")
        if key in instrument
    }
    metadata = {
        "parser": "GSAS-II",
        "gsas2_module": module_name,
        "gsas2_version": module_version,
        "mapping_id": mapping.mapping_id,
        "format_name": mapping.gsas2_format_hint,
        "angle_unit": mapping.angle_unit,
        "histogram_name": str(getattr(histogram, "name", "")),
        "bank": 0,
        "input_sha256": _sha256(path),
        "comments": comments,
        "comment_fields": comment_fields,
        "scan_type": scan_type,
        "scan_type_validation": "passed" if scan_type is not None else "not_declared",
        "sample": {
            key: sample[key]
            for key in ("Type", "Gonio. radius", "Temperature", "Omega")
            if key in sample
        },
        "instrument_parameters": instrument_summary,
    }
    return Pattern(
        angles_deg=tuple(float(value) for value in angles),
        intensities=tuple(float(value) for value in intensities),
        source_name=path.name,
        source_format=f"{mapping.mapping_id}-gsas2",
        angle_unit=AngleUnit.TWO_THETA,
        metadata=metadata,
    )


class GSAS2Adapter:
    @staticmethod
    def available() -> bool:
        try:
            _load_scriptable()
        except GSAS2AdapterError:
            return False
        return True

    @staticmethod
    def file_sha256(path: str | Path) -> str:
        return _sha256(Path(path))

    def import_raw(self, path: Path, *, radiation: str = "Cu Ka") -> Pattern:
        candidate = Path(path)
        mapping = detect_gsas2_mapping(candidate)
        if mapping is None:
            raise GSAS2AdapterError(
                "Unsupported binary RAW signature; no validated GSAS-II vendor mapping is configured."
            )
        if mapping.angle_unit != AngleUnit.TWO_THETA.value:
            raise GSAS2AdapterError("The configured GSAS-II mapping does not produce calibrated 2θ data.")
        module, module_name = _load_scriptable()
        try:
            with tempfile.TemporaryDirectory(prefix="xrd-gsas2-") as directory:
                project_path = Path(directory) / "import.gpx"
                project = module.G2Project(newgpx=str(project_path))
                histogram = project.add_powder_histogram(
                    str(candidate),
                    iparams=_instrument_parameters(radiation),
                    fmthint=mapping.gsas2_format_hint,
                    multiple=False,
                )
                if isinstance(histogram, (list, tuple)):
                    if len(histogram) != 1:
                        raise GSAS2AdapterError(
                            "GSAS-II returned multiple RAW banks; select one bank before importing."
                        )
                    histogram = histogram[0]
                return _normalise_histogram(
                    histogram,
                    candidate,
                    mapping,
                    module_name=module_name,
                    module_version=str(getattr(module, "__version__", "unknown")),
                )
        except GSAS2AdapterError:
            raise
        except Exception as exc:
            raise GSAS2AdapterError(
                f"GSAS-II could not import the validated {mapping.format} mapping: {type(exc).__name__}."
            ) from exc
