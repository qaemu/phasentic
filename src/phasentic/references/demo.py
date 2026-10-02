from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from phasentic.domain.models import ReferencePhase, ReferenceLine


_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "resources" / "demo-references.json"


class DemoReferenceStore:
    """Small transparent reference set used for offline smoke tests and demos."""

    def __init__(self, path: Path | None = None) -> None:
        source = path or _DEFAULT_PATH
        payload = json.loads(source.read_text(encoding="utf-8"))
        self._references = tuple(
            ReferencePhase(
                reference_id=item["reference_id"],
                formula=item["formula"],
                name=item["name"],
                space_group=item["space_group"],
                lines=tuple(
                    ReferenceLine(
                        d_spacing_angstrom=float(line["d_spacing_angstrom"]),
                        relative_intensity=float(line["relative_intensity"]),
                        hkl=line.get("hkl"),
                    )
                    for line in item["lines"]
                ),
                source=item.get("source", "demo"),
                cod_entry_url=item.get("cod_entry_url"),
            )
            for item in payload
        )
        self._by_id = {reference.reference_id: reference for reference in self._references}

    def all(self) -> tuple[ReferencePhase, ...]:
        return self._references

    def get(self, reference_id: str) -> ReferencePhase:
        return self._by_id[reference_id]

    def __iter__(self) -> Iterable[ReferencePhase]:
        return iter(self._references)

