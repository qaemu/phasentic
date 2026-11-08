"""Phase alternatives (near-equal fits, duplicates removed) and operator-pinned phases."""

import numpy as np

from phasentic.domain.models import Peak, ReferenceLine, ReferencePhase
from phasentic.domain.radiation import d_from_two_theta, get_radiation
from phasentic.search.mixtures import MixtureSettings, select_mixture_hypotheses

CU = get_radiation("Cu Ka")


def phase(reference_id, formula, space_group, lines):
    return ReferencePhase(
        reference_id, formula, formula, space_group,
        tuple(ReferenceLine(d_from_two_theta(angle, CU), intensity) for angle, intensity in lines),
    )


MAJOR = [(25.0, 100), (35.0, 60), (43.0, 80), (52.0, 40), (57.0, 30)]
MINOR = [(30.0, 100), (47.0, 70), (63.0, 50)]
A = phase("a", "Al2O3", "R-3c", MAJOR)
A_DUP = phase("a2", "Al2O3", "R -3 c", MAJOR)  # same material, another entry
B = phase("b", "Ga2O3", "R-3c", [(25.02, 100), (35.0, 55), (43.02, 85), (52.0, 40), (57.0, 25)])  # near-equal fit
C = phase("c", "MgO", "Fm-3m", MINOR)
POOR = phase("p", "ZnO", "P6_3mc", [(25.0, 100), (31.0, 90), (60.0, 90)])


def scan():
    angles = np.arange(20.0, 70.0, 0.02)
    y = np.full_like(angles, 5.0)
    for lines, scale in ((MAJOR, 1.0), (MINOR, 0.3)):
        for angle, intensity in lines:
            y += scale * intensity * np.exp(-0.5 * ((angles - angle) / 0.06) ** 2)
    peaks = [Peak(angle, float(np.interp(angle, angles, y)), 1.0, 0.14) for lines in (MAJOR, MINOR) for angle, _ in lines]
    return angles, y, peaks


def run(**kwargs):
    angles, y, peaks = scan()
    return select_mixture_hypotheses(
        angles, y, peaks, (A, A_DUP, B, C, POOR), CU, tolerance_deg=0.1,
        settings=MixtureSettings(max_phases=3, swap_fit_attempt_budget=0), **kwargs,
    )


def test_alternatives_and_pinning():
    result = run()
    selected = next(h for h in result.hypotheses if h.hypothesis_id == result.selected_hypothesis_id)
    ids = {component.reference_id for component in selected.components}
    assert ids & {"a", "a2"} and "c" in ids, ids
    alternatives = {rid: (fit, items) for rid, fit, items in result.phase_alternatives}
    major_id = next(item for item in ids if item in {"a", "a2"})
    selected_fit, items = alternatives[major_id]
    major_alts = {item.reference_id: item.fit_percent for item in items}
    assert 0 < selected_fit <= 100 and all(0 <= v <= 100 for v in major_alts.values()), (selected_fit, major_alts)
    assert "b" in major_alts and major_alts["b"] >= 0.8 * max(selected_fit, *major_alts.values()), major_alts
    assert not {"a", "a2"} & set(major_alts), "duplicate of the selected phase listed"
    assert "p" not in major_alts, "poor fit listed"
    payload = result.to_dict()["phase_alternatives"][major_id]
    assert payload["fit_percent"] == selected_fit and "fit_percent" in payload["alternatives"][0]

    pinned = run(pinned_references=(B,))
    best = pinned.hypotheses[0]
    names = [component.reference_id for component in best.components]
    assert "b" in names and "c" in names, names  # the minor phase is refitted around the choice
    assert all("b" in [c.reference_id for c in h.components] for h in pinned.hypotheses)
    assert pinned.query["pinned_reference_ids"] == ["b"]


def test_local_improvement_accepts_minor_phase():
    angles = np.arange(20.0, 70.0, 0.02)
    y = np.full_like(angles, 1.0)
    for lines, scale in ((MAJOR, 1.0), (MINOR, 0.03)):
        for angle, intensity in lines:
            y += scale * intensity * np.exp(-0.5 * ((angles - angle) / 0.06) ** 2)
    peaks = [Peak(angle, float(np.interp(angle, angles, y)), 1.0, 0.14) for lines in (MAJOR, MINOR) for angle, _ in lines]

    def phases(**kwargs):
        result = select_mixture_hypotheses(
            angles, y, peaks, (A, C), CU, tolerance_deg=0.1,
            settings=MixtureSettings(max_phases=2, swap_fit_attempt_budget=0, min_objective_improvement=0.05, **kwargs),
        )
        return any({c.reference_id for c in h.components} == {"a", "c"} for h in result.hypotheses)

    assert not phases(), "minor phase should fail the 5% global gate"
    assert phases(local_improvement_min=0.3)
    assert phases(local_improvement_min=0.3, local_improvement_skips_evidence=True)


def test_space_group_order():
    from phasentic.search.mixtures import _space_group_order

    assert _space_group_order("F d -3 m :2") > _space_group_order("F -4 3 m") > 0
    assert _space_group_order("I a -3") > _space_group_order("I 21 3")
    assert _space_group_order("not a group") == 0


if __name__ == "__main__":
    test_alternatives_and_pinning()
    print("ok")
    test_space_group_order()
    test_local_improvement_accepts_minor_phase()
