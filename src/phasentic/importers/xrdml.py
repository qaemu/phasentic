from __future__ import annotations

import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from phasentic.domain.models import AngleUnit, Pattern

from .common import parse_float, validate_series


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _numbers(value: str | None) -> list[float]:
    if not value:
        return []
    try:
        return [parse_float(token) for token in re.split(r"[\s,;]+", value.strip()) if token]
    except ValueError as exc:
        raise ValueError("XRDML scan contains a non-numeric value") from exc


def _first_text(root: ET.Element, names: set[str]) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) in names and element.text and element.text.strip():
            return element.text
    return None


def _source_radiation_metadata(root: ET.Element) -> dict[str, object] | None:
    wavelength = next(
        (element for element in root.iter() if _local_name(element.tag) == "usedWavelength"),
        None,
    )
    if wavelength is None:
        return None
    values: dict[str, object] = {}
    anode = _first_text(root, {"anodeMaterial"})
    if anode:
        values["anode_material"] = anode
    intended = wavelength.attrib.get("intended")
    if intended:
        values["intended"] = intended
    for xml_name, payload_name in (
        ("kAlpha1", "ka1_angstrom"),
        ("kAlpha2", "ka2_angstrom"),
        ("ratioKAlpha2KAlpha1", "ka2_to_ka1_intensity_ratio"),
    ):
        element = next(
            (child for child in wavelength.iter() if _local_name(child.tag) == xml_name),
            None,
        )
        if element is None or element.text is None or not element.text.strip():
            continue
        try:
            value = float(element.text.strip())
        except ValueError as exc:
            raise ValueError(f"XRDML {xml_name} value is not numeric") from exc
        if not math.isfinite(value):
            raise ValueError(f"XRDML {xml_name} value must be finite")
        if payload_name == "ka2_to_ka1_intensity_ratio":
            if not 0.0 <= value <= 1.0:
                raise ValueError("XRDML K-alpha intensity ratio must be between 0 and 1")
        elif value <= 0.0:
            raise ValueError(f"XRDML {xml_name} wavelength must be positive")
        values[payload_name] = value
    return values or None


def _descendants(root: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == name]


def _axis_key(value: str) -> str:
    return value.replace(" ", "").replace("_", "").casefold()


def _is_two_theta(element: ET.Element) -> bool:
    return _axis_key(element.attrib.get("axis", "")) in {"2theta", "twotheta", "2θ"}


def _validate_angle_unit(position_element: ET.Element) -> str:
    unit = position_element.attrib.get("unit")
    if unit is None:
        start = next(
            (child for child in position_element.iter() if _local_name(child.tag) == "startPosition"),
            None,
        )
        unit = start.attrib.get("unit") if start is not None else None
    normalised = (unit or "deg").replace(" ", "").casefold()
    if normalised not in {"deg", "degree", "degrees", "°"}:
        raise ValueError(
            f"XRDML position unit '{unit}' is unsupported; only degree 2Theta is accepted"
        )
    return unit or "deg"


def parse_xrdml(path: Path) -> Pattern:
    raw_xml = path.read_bytes()
    # XML declarations and DTDs may be UTF-16/UTF-32 encoded.  Removing NUL
    # bytes before inspecting the declaration catches those encodings while
    # leaving the actual XML parser responsible for decoding the document.
    lowered_xml = raw_xml.replace(b"\x00", b"").lower()
    if re.search(br"<!\s*(doctype|entity)\b", lowered_xml):
        raise ValueError("XRDML DTD/entity declarations are not supported")
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise ValueError("XRDML XML is malformed") from exc

    scans = _descendants(root, "scan")
    if not scans:
        raise ValueError("XRDML file does not contain a scan")
    if len(scans) != 1:
        raise ValueError("XRDML files with multiple scans are not supported; select one scan")
    scan = scans[0]

    intensity_elements = [
        element
        for element in scan.iter()
        if _local_name(element.tag) in {"intensities", "counts", "intensity"}
    ]
    if len(intensity_elements) != 1:
        if not intensity_elements:
            raise ValueError("XRDML scan does not contain an intensity series")
        raise ValueError("XRDML scan contains multiple intensity series")
    intensities = _numbers(intensity_elements[0].text)
    if not intensities:
        raise ValueError("XRDML scan does not contain an intensity series")

    positions = _descendants(scan, "positions")
    theta_positions = [element for element in positions if _is_two_theta(element)]
    if not theta_positions:
        axis_names = sorted({element.attrib.get("axis", "unknown") for element in positions})
        detail = ", ".join(axis_names) if axis_names else "none"
        raise ValueError(
            f"XRDML position axis is unsupported ({detail}); only calibrated 2Theta is accepted"
        )
    if len(theta_positions) != 1:
        raise ValueError("XRDML scan contains multiple 2Theta position series")
    position_element = theta_positions[0]
    position_unit = _validate_angle_unit(position_element)
    explicit_positions = _numbers(position_element.text)
    start_text = _first_text(position_element, {"startPosition"})
    end_text = _first_text(position_element, {"endPosition"})
    if explicit_positions and len(explicit_positions) == len(intensities):
        angles = explicit_positions
    elif start_text is not None and end_text is not None:
        start = parse_float(start_text)
        end = parse_float(end_text)
        if len(intensities) < 2:
            raise ValueError("XRDML scan must contain at least two positions")
        increment = (end - start) / (len(intensities) - 1)
        angles = [start + index * increment for index in range(len(intensities))]
    else:
        raise ValueError("XRDML positions must provide start/end or explicit values")
    data_points_text = _first_text(scan, {"dataPoints"})
    if data_points_text is not None:
        try:
            data_points = int(data_points_text.strip())
        except ValueError as exc:
            raise ValueError("XRDML dataPoints is not an integer") from exc
        if data_points != len(intensities):
            raise ValueError("XRDML dataPoints does not match the intensity series length")
    angles, intensities = validate_series(angles, intensities)
    angle_unit = AngleUnit.TWO_THETA
    metadata = {
        "parser": "xrdml-xml",
        "format_owner": "PANalytical/Malvern Panalytical",
        "position_axis": position_element.attrib.get("axis", "2Theta"),
        "position_unit": position_unit,
        "scan_count": 1,
    }
    source_radiation = _source_radiation_metadata(root)
    if source_radiation is not None:
        metadata["source_radiation"] = source_radiation
    return Pattern(
        angles_deg=angles,
        intensities=intensities,
        source_name=path.name,
        source_format="xrdml",
        angle_unit=angle_unit,
        metadata=metadata,
    )
