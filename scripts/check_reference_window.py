"""Self-check: the reference 2θ window is REFERENCE_TWO_THETA_MAX_DEG in every layer.

Run: python scripts/check_reference_window.py
"""

import math
import sqlite3
import tempfile
from pathlib import Path

from phasentic.domain.models import AnalysisSettings
from phasentic.domain.radiation import REFERENCE_TWO_THETA_MAX_DEG as LIMIT, d_from_two_theta, two_theta_from_d
from phasentic.presets import validated_preset
from phasentic.references.equivalence import _line_angles
from phasentic.references.powcod import PowCodReferenceStore, build_powcod_cache
from phasentic.reporting.service import analyze_file



def main() -> None:
    inside, outside = LIMIT - 10.0, LIMIT + 10.0
    d_in, d_out = d_from_two_theta(inside, "Cu Ka"), d_from_two_theta(outside, "Cu Ka")

    # Store: a line past the limit is dropped when the cache is read.
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "mini.sq"
        with sqlite3.connect(source) as db:
            db.execute("CREATE TABLE id (id TEXT, dvalue TEXT, intensita TEXT, formula TEXT, spacegroup TEXT)")
            db.execute("INSERT INTO id VALUES ('1', ?, '100,50', 'Si', 'F d -3 m')", (f"{d_in},{d_out}",))
        build_powcod_cache(source, Path(tmp) / "mini.xrd.sqlite")
        with PowCodReferenceStore(source, cache_path=Path(tmp) / "mini.xrd.sqlite") as store:
            angles = [two_theta_from_d(line.d_spacing_angstrom, "Cu Ka") for line in store.get("1").lines]
    assert len(angles) == 1 and abs(angles[0] - inside) < 1e-3, angles

    # Equivalence clustering compares only lines inside the window.
    from phasentic.domain.models import ReferenceLine, ReferencePhase
    phase = ReferencePhase("x", "Si", "Si", "F d -3 m", (ReferenceLine(d_in, 100.0), ReferenceLine(d_out, 50.0)))
    assert len(_line_angles(phase, "Cu Ka")) == 1

    # Preset agrees with the window, so reports state the limit that ran.
    assert validated_preset()["matching_two_theta_max_deg"] == LIMIT

    # Full analysis: a synthetic silicon scan (Cu Ka) reaching past the limit is cropped.
    peaks = (28.44, 47.30, 56.12, 69.13, 76.38, 88.03, 94.95, 106.71)
    with tempfile.TemporaryDirectory() as tmp:
        scan = Path(tmp) / "si-10-110.xy"
        rows = []
        for step in range(5001):
            x = 10.0 + step * 0.02
            y = 20.0 + sum(1000.0 * math.exp(-0.5 * ((x - p) / 0.05) ** 2) for p in peaks)
            rows.append(f"{x:.4f} {y:.4f}")
        scan.write_text("\n".join(rows) + "\n")
        report = analyze_file(scan, AnalysisSettings()).to_dict()
    assert report["peaks"] and all(peak["position_deg"] <= LIMIT for peak in report["peaks"])
    assert any(f"0-{LIMIT:g} degrees" in warning for warning in report["quality"]["warnings"]), report["quality"]["warnings"]
    print(f"OK: reference window is 0-{LIMIT:g} deg in store, equivalence, preset and analysis")


if __name__ == "__main__":
    main()
