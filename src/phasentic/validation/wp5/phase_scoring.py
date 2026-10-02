"""Chemistry-based phase agreement for Precursor development scoring.

Predicted phases are compared with source labels directly by element set,
stoichiometry and space-group number. The comparison never uses runtime
equivalence-group identifiers, so a correct phase is recognised whether it
came from the initial lookup, a residual lookup, or any duplicate POW_COD
entry. Each prediction may satisfy at most one label (one-to-one pairing).

Levels, from strongest to weakest:

* ``strict``   – same elements, compatible stoichiometry, same space group;
* ``family``   – same elements and compatible stoichiometry;
* ``elements`` – same element set only.

A label without a space group can reach ``family`` at most; when the gate
level is ``strict`` such a label is evaluated at ``family`` and this is
recorded per label.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from phasentic.domain.formula import parse_formula
from phasentic.references.equivalence import parse_source_phase_label

PHASE_SCORING_VERSION = "precursor-chemistry-scoring-2"
MATCH_LEVELS = ("strict", "family", "elements")
_LEVEL_RANK = {"strict": 3, "family": 2, "elements": 1}
DEFAULT_RELATIVE_TOLERANCE = 0.10
DEFAULT_ABSOLUTE_TOLERANCE = 0.02


class PhaseScoringError(ValueError):
    """Raised when scoring inputs cannot be interpreted safely."""


@dataclass(frozen=True)
class ChemicalPhase:
    identifier: str
    formula: str
    space_group_number: int | None
    weight: float = 0.0


def space_group_to_number(value: Any) -> int | None:
    """Return a space-group number, requiring gemmi for symbol lookup."""

    if value is None:
        return None
    if isinstance(value, bool):
        raise PhaseScoringError("space group must not be boolean")
    if isinstance(value, int):
        return value if 1 <= value <= 230 else None
    text = str(value).strip()
    if not text or text in {"?", "."}:
        return None
    if text.isdigit():
        number = int(text)
        return number if 1 <= number <= 230 else None
    try:
        import gemmi  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment guard
        raise PhaseScoringError(
            "gemmi is required to compare space-group symbols; install the cod-index extra"
        ) from exc
    group = gemmi.find_spacegroup_by_name(text)
    return int(group.number) if group is not None else None


TRACE_ELEMENT_FRACTION = 0.02
# X-rays scatter almost nothing from H/D, so partial hydrogen or deuterium in a
# database entry (e.g. ``D0.09 O2 Ti`` for anatase) is invisible to XRD.
HYDROGEN_TRACE_FRACTION = 0.05


def composition_fractions(formula: str) -> dict[str, float] | None:
    """Atomic fractions with trace dopants (< 2 at.%, H/D < 5 at.%) removed and renormalized.

    Refined labels such as ``In31.648Co0.352O48`` describe a doped host; for
    phase identification they are compared with the host (In2O3).
    """

    totals = parse_formula(formula)
    if not totals:
        return None
    total = math.fsum(totals.values())
    if total <= 0:
        return None
    fractions = {element: count / total for element, count in totals.items()}
    kept = {
        element: value
        for element, value in fractions.items()
        if value >= (HYDROGEN_TRACE_FRACTION if element == "H" else TRACE_ELEMENT_FRACTION)
    }
    if not kept:
        return None
    kept_total = math.fsum(kept.values())
    return {element: value / kept_total for element, value in kept.items()}


def compositions_compatible(
    left: str,
    right: str,
    *,
    relative_tolerance: float = DEFAULT_RELATIVE_TOLERANCE,
    absolute_tolerance: float = DEFAULT_ABSOLUTE_TOLERANCE,
) -> bool:
    """Compare atomic fractions, tolerating partial occupancy and vacancies."""

    first = composition_fractions(left)
    second = composition_fractions(right)
    if first is None or second is None or set(first) != set(second):
        return False
    for element, value in first.items():
        other = second[element]
        if abs(value - other) > max(absolute_tolerance, relative_tolerance * max(value, other)):
            return False
    return True


# Enantiomorphic space-group pairs give identical powder patterns.
_ENANTIOMORPHS = {
    76: 78, 78: 76, 91: 95, 95: 91, 92: 96, 96: 92, 144: 145, 145: 144, 151: 153, 153: 151,
    152: 154, 154: 152, 169: 170, 170: 169, 171: 172, 172: 171, 178: 179, 179: 178,
    180: 181, 181: 180, 212: 213, 213: 212,
}


def _same_space_group(left: int | None, right: int | None) -> bool:
    if left is None or right is None:
        return False
    return left == right or _ENANTIOMORPHS.get(left) == right


def match_level(label: ChemicalPhase, predicted: ChemicalPhase) -> str | None:
    first = composition_fractions(label.formula)
    second = composition_fractions(predicted.formula)
    if first is None or second is None or set(first) != set(second):
        return None
    if not compositions_compatible(label.formula, predicted.formula):
        return "elements"
    if _same_space_group(label.space_group_number, predicted.space_group_number):
        return "strict"
    return "family"


def _required_rank(label: ChemicalPhase, level: str) -> int:
    rank = _LEVEL_RANK[level]
    if level == "strict" and label.space_group_number is None:
        return _LEVEL_RANK["family"]
    return rank


def _pair(
    labels: Sequence[ChemicalPhase],
    predicted: Sequence[ChemicalPhase],
    level: str,
) -> dict[int, int]:
    """Maximum one-to-one pairing (label index -> prediction index)."""

    allowed: list[list[int]] = []
    for label in labels:
        need = _required_rank(label, level)
        allowed.append(
            [
                index
                for index, item in enumerate(predicted)
                if (found := match_level(label, item)) is not None and _LEVEL_RANK[found] >= need
            ]
        )
    owner: dict[int, int] = {}

    def augment(label_index: int, seen: set[int]) -> bool:
        for prediction_index in allowed[label_index]:
            if prediction_index in seen:
                continue
            seen.add(prediction_index)
            if prediction_index not in owner or augment(owner[prediction_index], seen):
                owner[prediction_index] = label_index
                return True
        return False

    for label_index in range(len(labels)):
        augment(label_index, set())
    return {label_index: prediction_index for prediction_index, label_index in owner.items()}


def labels_from_source(
    labels: Sequence[str],
    weights: Mapping[str, Any] | None,
) -> tuple[list[ChemicalPhase], list[dict[str, str]]]:
    parsed: list[ChemicalPhase] = []
    problems: list[dict[str, str]] = []
    for raw in labels:
        label = str(raw)
        info = parse_source_phase_label(label)
        if info is None or composition_fractions(str(info["formula"])) is None:
            problems.append({"source_label": label, "reason": "label_unparseable"})
            continue
        weight = (weights or {}).get(label)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(float(weight)):
            problems.append({"source_label": label, "reason": "source_weight_invalid"})
            weight = 0.0
        parsed.append(
            ChemicalPhase(label, str(info["formula"]), info.get("space_group_number"), float(weight))
        )
    return parsed, problems


def predictions_from_components(components: Sequence[Mapping[str, Any]]) -> list[ChemicalPhase]:
    result: list[ChemicalPhase] = []
    for component in components:
        formula = component.get("formula")
        if not isinstance(formula, str) or not formula.strip():
            continue
        identifier = str(component.get("reference_id") or formula)
        result.append(ChemicalPhase(identifier, formula, space_group_to_number(component.get("space_group"))))
    return result


def score_phase_agreement(
    labels: Sequence[ChemicalPhase],
    predicted: Sequence[ChemicalPhase],
    *,
    gate_level: str = "strict",
    top_n: int = 5,
    minimum_ratio: float = 0.80,
    label_problems: Sequence[Mapping[str, str]] = (),
    reference_coverage: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Score one case at every level; ``passed`` uses ``gate_level``.

    Recall uses the ``top_n`` heaviest labels. Precision uses every label, so
    a correct minor phase outside the top ``n`` is not a false prediction.
    Unparseable labels stay in the denominator as unmatched labels.
    """

    if gate_level not in MATCH_LEVELS:
        raise PhaseScoringError(f"gate_level must be one of {MATCH_LEVELS}")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise PhaseScoringError("top_n must be a positive integer")
    if not 0.0 < float(minimum_ratio) <= 1.0:
        raise PhaseScoringError("minimum_ratio must be in (0, 1]")
    ordered = sorted(labels, key=lambda item: (-item.weight, item.identifier))
    top = ordered[:top_n]
    unparsed = [str(item.get("source_label")) for item in label_problems if item.get("reason") == "label_unparseable"]
    # Unparseable labels still occupy top-n slots in weight order when weighted.
    top_denominator = min(top_n, len(ordered) + len(unparsed))
    levels: dict[str, Any] = {}
    for level in MATCH_LEVELS:
        top_pairs = _pair(top, predicted, level)
        all_pairs = _pair(ordered, predicted, level)
        matched_predictions = set(all_pairs.values())
        recall = len(top_pairs) / top_denominator if top_denominator else None
        precision = len(matched_predictions) / len(predicted) if predicted else 0.0
        levels[level] = {
            "recall": recall,
            "precision": precision,
            "matched_labels": sorted(top[index].identifier for index in top_pairs),
            "missing_labels": sorted(
                [label.identifier for index, label in enumerate(top) if index not in top_pairs]
                + unparsed[: max(0, top_denominator - len(top))]
            ),
            "unexpected_predictions": [
                item.identifier for index, item in enumerate(predicted) if index not in matched_predictions
            ],
            "passed": bool(
                recall is not None and recall >= minimum_ratio and precision >= minimum_ratio
            ),
        }
    gate = levels[gate_level]
    coverage = None
    if reference_coverage is not None:
        coverage = {
            "labels_absent_from_reference": sorted(
                label.identifier for label in ordered if int(reference_coverage.get(label.identifier, 0)) == 0
            ),
        }
    return {
        "scoring_version": PHASE_SCORING_VERSION,
        "status": "pass" if gate["passed"] else ("insufficient_truth" if not top_denominator else "fail"),
        "passed": gate["passed"],
        "gate_level": gate_level,
        "recall": gate["recall"],
        "precision": gate["precision"],
        "predicted_count": len(predicted),
        "reference_count": top_denominator,
        "reference_total_count": len(ordered) + len(unparsed),
        "labels_evaluated_at_family_for_missing_space_group": sorted(
            label.identifier for label in top if label.space_group_number is None
        ) if gate_level == "strict" else [],
        "unexpected_groups": gate["unexpected_predictions"],
        "levels": levels,
        "label_problems": [dict(item) for item in label_problems],
        "reference_coverage": coverage,
    }


def best_hypothesis_rank(
    labels: Sequence[ChemicalPhase],
    hypotheses: Sequence[Mapping[str, Any]],
    *,
    level: str = "family",
) -> dict[str, int | None]:
    """Diagnostic: 1-based rank of the first hypothesis containing each label."""

    ranks: dict[str, int | None] = {label.identifier: None for label in labels}
    for rank, hypothesis in enumerate(hypotheses, start=1):
        predictions = predictions_from_components(hypothesis.get("components", []))
        for label in labels:
            if ranks[label.identifier] is not None:
                continue
            need = _required_rank(label, level)
            if any(
                (found := match_level(label, item)) is not None and _LEVEL_RANK[found] >= need
                for item in predictions
            ):
                ranks[label.identifier] = rank
    return ranks


__all__ = [
    "MATCH_LEVELS",
    "PHASE_SCORING_VERSION",
    "ChemicalPhase",
    "PhaseScoringError",
    "best_hypothesis_rank",
    "compositions_compatible",
    "labels_from_source",
    "match_level",
    "predictions_from_components",
    "score_phase_agreement",
    "space_group_to_number",
]
