"""Chemical formula parsing and element sets shared by retrieval and scoring."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

ELEMENT_SYMBOLS: tuple[str, ...] = (
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar",
    "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br",
    "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te",
    "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm",
    "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn",
    "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr",
    "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
)
ELEMENT_INDEX = {symbol: index for index, symbol in enumerate(ELEMENT_SYMBOLS)}
# Deuterium is chemically hydrogen for element-set purposes.
_ALIASES = {"D": "H", "T": "H"}
_TOKEN = re.compile(r"([A-Z][a-z]?)|(\d+(?:\.\d+)?|\.\d+)|([(\[{])|([)\]}])")


def _parse_part(text: str) -> dict[str, float] | None:
    stack: list[dict[str, float]] = [{}]
    position = 0
    last: tuple[str, object] | None = None
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:
            return None
        position = match.end()
        element, number, opening, closing = match.groups()
        if element:
            element = _ALIASES.get(element, element)
            if element not in ELEMENT_INDEX:
                return None
            previous = stack[-1].get(element, 0.0)
            stack[-1][element] = previous + 1.0
            last = ("element", (element, previous))
        elif number:
            value = float(number)
            if last is None or value <= 0:
                return None
            kind, payload = last
            if kind == "element":
                symbol, previous = payload
                stack[-1][symbol] = previous + value
            else:
                for symbol, count in payload.items():
                    stack[-1][symbol] = stack[-1].get(symbol, 0.0) + count * (value - 1.0)
            last = None
        elif opening:
            stack.append({})
            last = None
        elif closing:
            if len(stack) == 1:
                return None
            group = stack.pop()
            for symbol, count in group.items():
                stack[-1][symbol] = stack[-1].get(symbol, 0.0) + count
            last = ("group", group)
    if len(stack) != 1 or not stack[0]:
        return None
    return stack[0]


_CHARGE = re.compile(r"(?<=[A-Za-z)\]\s])\d*[+-]")
_LEADING_MULTIPLIER = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)\s*(?=[A-Z(\[{])")


def parse_formula(formula: str) -> dict[str, float] | None:
    """Parse element counts from database formula text.

    Handles bracketed groups (``Fe(CoO2)2``), ionic charges (``(Co 2+)8``),
    and comma/dot-separated parts with leading multipliers such as
    ``K2 (C O3), 1.5 H2 O`` or ``... . (H2 O)0.5``. Returns ``None`` for
    text that cannot be interpreted or contains an unknown symbol, so it can
    never produce a false match.
    """

    if not isinstance(formula, str) or not formula.strip():
        return None
    parsed = _parse_formula_text(formula)
    if parsed is not None:
        return parsed
    # Two database conventions that hide plain inorganic formulas: a CIF
    # Greek-letter polymorph prefix ("\\b-Ga2 O3" for beta-Ga2O3) and
    # upper-case element symbols ("LA2 TI2 O7").
    cleaned = _GREEK_PREFIX.sub("", formula)
    cleaned = _UPPER_SYMBOL.sub(lambda m: m.group(1) + m.group(2).lower() if m.group(1) + m.group(2).lower() in ELEMENT_INDEX else m.group(0), cleaned)
    return _parse_formula_text(cleaned) if cleaned != formula else None


_GREEK_PREFIX = re.compile(r"^\\[a-z]-")
_UPPER_SYMBOL = re.compile(r"(?<![A-Za-z])([A-Z])([A-Z])(?=[\d.\s()]|$)")


def _parse_formula_text(formula: str) -> dict[str, float] | None:
    text = _CHARGE.sub("", formula.replace("·", ","))
    text = re.sub(r"\s\.\s", ",", text)
    totals: dict[str, float] = {}
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            continue
        multiplier = 1.0
        leading = _LEADING_MULTIPLIER.match(part)
        if leading is not None:
            multiplier = float(leading.group(1))
            part = part[leading.end():]
        parsed = _parse_part(re.sub(r"\s", "", part))
        if parsed is None:
            return None
        for symbol, count in parsed.items():
            totals[symbol] = totals.get(symbol, 0.0) + multiplier * count
    return totals or None



def normalize_elements(values: Iterable[str]) -> tuple[str, ...]:
    """Validate and sort element symbols; raises ``ValueError`` on unknown ones."""

    result: set[str] = set()
    for value in values:
        symbol = _ALIASES.get(str(value).strip(), str(value).strip())
        if symbol not in ELEMENT_INDEX:
            raise ValueError(f"unknown element symbol: {value!r}")
        result.add(symbol)
    if not result:
        raise ValueError("at least one element is required")
    return tuple(sorted(result, key=ELEMENT_INDEX.__getitem__))



NON_METALS = frozenset(
    {"H", "He", "B", "C", "N", "O", "F", "Ne", "Si", "P", "S", "Cl", "Ar", "Se", "Br", "Kr", "I", "Xe", "Rn", "At", "Te", "As"}
)


def is_molecular_organic(parsed: dict[str, float]) -> bool:
    """True for molecular carbon compounds: more carbon than metal atoms, with H or O.

    Used by the sample-context element filter: atmospheric carbon and
    hydrogen are allowed for carbonates, hydroxides and hydrates, but not for
    organic, metal-organic or carbonyl molecular crystals. Elemental carbon,
    carbides (no H/O) and (hydrated) carbonates with C <= metal are kept.
    """

    carbon = parsed.get("C", 0.0)
    if carbon <= 0.0 or (parsed.get("H", 0.0) <= 0.0 and parsed.get("O", 0.0) <= 0.0):
        return False
    if parsed.get("O", 0.0) >= 3.0 * carbon - 1e-9 and set(parsed) - NON_METALS:
        return False  # (hydrogen) carbonates such as Fe(HCO3)2
    metal = sum(count for symbol, count in parsed.items() if symbol not in NON_METALS)
    return carbon > metal + 1e-9


ATMOSPHERIC_ELEMENTS = frozenset({"H", "C", "N", "O"})


NOBLE_METALS = frozenset({"Ag", "Au", "Pt", "Pd", "Rh", "Ir", "Ru", "Os"})


def passes_element_filter(formula: str, allowed: frozenset[str], *, oxidizing: bool = False) -> bool:
    """Allowed chemistry, not molecular-organic, and not purely atmospheric.

    A phase must contain at least one allowed element other than H, C, N, O
    (so solid hydrogen, ice or CO2 cannot fill a fit), except elemental
    carbon when carbon is allowed (graphite can form from carbon sources).

    ``oxidizing`` (synthesis heated in air) additionally rejects oxygen-free
    phases unless they contain a noble metal or are graphite: reactive
    metals, phosphorus, hydrides and carbides do not survive. In the
    non-sealed Precursor Genome labels this keeps 99.6% of human phases.
    """

    parsed = parse_formula(formula)
    if not parsed or not set(parsed) <= allowed:
        return False
    if oxidizing and "O" not in parsed and not (set(parsed) & NOBLE_METALS) and set(parsed) != {"C"}:
        return False
    if is_molecular_organic(parsed):
        return False
    if set(parsed) <= ATMOSPHERIC_ELEMENTS:
        # Graphite/diamond only; molecular carbon allotropes (fullerenes such
        # as C60) cannot form in these syntheses.
        return set(parsed) == {"C"} and parsed["C"] <= 1.0 + 1e-9
    return True


def composition_fractions(formula: str, *, ignore_hydrogen: bool = False) -> dict[str, float] | None:
    parsed = parse_formula(formula)
    if parsed and ignore_hydrogen:
        parsed = {symbol: count for symbol, count in parsed.items() if symbol != "H"}
    if not parsed:
        return None
    total = sum(parsed.values())
    return {symbol: count / total for symbol, count in parsed.items()} if total > 0 else None


def compositions_compatible(
    left: str,
    right: str,
    *,
    relative_tolerance: float = 0.10,
    absolute_tolerance: float = 0.02,
    ignore_hydrogen: bool = False,
) -> bool:
    """Same element set and atomic fractions within tolerance.

    ``ignore_hydrogen`` compares heavy-atom chemistry only: X-ray structures
    often omit H, and deuterated entries describe the same material.
    """

    first = composition_fractions(left, ignore_hydrogen=ignore_hydrogen)
    second = composition_fractions(right, ignore_hydrogen=ignore_hydrogen)
    if first is None or second is None or set(first) != set(second):
        return False
    return all(
        abs(first[symbol] - second[symbol]) <= max(absolute_tolerance, relative_tolerance * max(first[symbol], second[symbol]))
        for symbol in first
    )


def normalize_space_group_symbol(value: str | None) -> str | None:
    """Whitespace/case-insensitive symbol with origin/setting suffixes removed."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.split(":", 1)[0]
    return "".join(text.split()).casefold()


@lru_cache(maxsize=4096)
def charge_balanced(formula: str) -> bool:
    """True when common oxidation states can balance the formula.

    Used only to break ties between indistinguishable database entries:
    POW_COD sometimes stores a structure under an incomplete formula (calcite
    as ``C Ca O``). Unparseable or very large formulas count as balanced.
    """

    parsed = parse_formula(formula)
    if not parsed or len(parsed) < 2 or sum(parsed.values()) > 200:
        return True
    try:
        import warnings

        from pymatgen.core import Composition

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return bool(Composition(parsed).oxi_state_guesses(max_sites=-20))
    except Exception:
        return True
