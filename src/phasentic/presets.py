"""The validated analysis preset and sample-chemistry helper.

``validated`` reproduces the settings of the method frozen and tested on the
sealed held-out cohort (see docs/validation.md). It assumes POW_COD, Cu Ka and
the sample's precursor/target chemistry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phasentic.domain.formula import normalize_elements, parse_formula

_PRESET_PATH = Path(__file__).resolve().parent / "resources" / "validated-preset.json"


def validated_preset() -> dict[str, Any]:
    return json.loads(_PRESET_PATH.read_text(encoding="utf-8"))["settings"]


def chemistry_elements(text: str) -> tuple[str, ...]:
    """Elements of the given formulas plus H, C and O from the furnace atmosphere."""

    elements = {"H", "C", "O"}
    for formula in str(text).replace(",", " ").split():
        parsed = parse_formula(formula)
        if not parsed:
            raise ValueError(f"cannot read the formula {formula!r}")
        elements.update(parsed)
    return normalize_elements(elements)
