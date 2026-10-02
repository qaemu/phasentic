"""Curated, versioned equivalence metadata for POW_COD references.

The sidecar is deliberately separate from the large immutable POW_COD cache.
Only reviewed groups are active at runtime; automated discovery belongs in a
review workflow and cannot silently change scientific results.
"""

from __future__ import annotations

from contextlib import closing

from dataclasses import dataclass
import hashlib
import json
import math
from bisect import bisect_left
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping

from phasentic.domain.models import CandidateMatch, ReferencePhase
from phasentic.domain.radiation import Radiation, two_theta_from_d


EQUIVALENCE_SCHEMA_VERSION = "powcod-equivalence-1"
EQUIVALENCE_METHOD_VERSION = "curated-only-2026-09-25"

# This resolver is deliberately separate from the curated sidecar.  It is an
# analysis-time grouping of the bounded candidate pool, not a persistent claim
# that two COD entries are universally interchangeable.
RUNTIME_EQUIVALENCE_SCHEMA_VERSION = "powcod-runtime-equivalence-1"
RUNTIME_EQUIVALENCE_METHOD_VERSION = "on-demand-structural-powder-2026-09-27"


class EquivalenceError(RuntimeError):
    """Named fail-closed error for an invalid equivalence sidecar."""


@dataclass(frozen=True)
class EquivalenceMetadata:
    reference_id: str
    group_id: str
    preferred_name: str
    parent_family_group_id: str | None
    equivalence_kind: str
    confidence: str
    cod_id: str | None


@dataclass(frozen=True)
class RuntimeEquivalenceSettings:
    """Deterministic, reportable bounds for one analysis-time resolution."""

    min_shared_lines: int = 3
    min_line_similarity: float = 0.45
    score_spread_max: float = 0.20
    line_tolerance_deg: float = 0.20
    # Two agreeing names in a three-entry set are sufficient to expose a
    # label; the receipt still records the exact fraction and all members.
    name_consensus_fraction: float = 0.66
    method_version: str = RUNTIME_EQUIVALENCE_METHOD_VERSION

    def validate(self) -> "RuntimeEquivalenceSettings":
        if isinstance(self.min_shared_lines, bool) or not isinstance(self.min_shared_lines, int) or self.min_shared_lines < 1:
            raise ValueError("min_shared_lines must be a positive integer")
        for field_name in ("min_line_similarity", "score_spread_max", "line_tolerance_deg", "name_consensus_fraction"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be finite and numeric")
        if not 0.0 < self.min_line_similarity <= 1.0:
            raise ValueError("min_line_similarity must be in (0, 1]")
        if not 0.0 <= self.score_spread_max <= 1.0:
            raise ValueError("score_spread_max must be in [0, 1]")
        if not 0.0 < self.line_tolerance_deg <= 2.0:
            raise ValueError("line_tolerance_deg must be in (0, 2]")
        if not 0.5 <= self.name_consensus_fraction <= 1.0:
            raise ValueError("name_consensus_fraction must be in [0.5, 1]")
        if not isinstance(self.method_version, str) or not self.method_version.strip():
            raise ValueError("method_version must be a non-empty string")
        return self

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": RUNTIME_EQUIVALENCE_SCHEMA_VERSION,
            "method_version": self.method_version,
            "min_shared_lines": self.min_shared_lines,
            "min_line_similarity": float(self.min_line_similarity),
            "score_spread_max": float(self.score_spread_max),
            "line_tolerance_deg": float(self.line_tolerance_deg),
            "name_consensus_fraction": float(self.name_consensus_fraction),
        }

    @property
    def configuration_sha256(self) -> str:
        return _sha256_bytes(_canonical_json(self.to_dict()))


@dataclass(frozen=True)
class RuntimeEquivalenceResult:
    """Resolved immutable representatives and their audit receipt."""

    references: tuple[ReferencePhase, ...]
    matches: tuple[CandidateMatch, ...]
    receipt: dict[str, Any]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _validate_hash(value: str, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise ValueError(f"{field} must be a SHA-256 hexadecimal string")
    return value.lower()


def _canonical_rows(groups: Iterable[Mapping[str, Any]], members: Iterable[Mapping[str, Any]]) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    group_rows: list[tuple[Any, ...]] = []
    for group in groups:
        group_id = str(group["group_id"]).strip()
        preferred_name = str(group.get("preferred_name", group_id)).strip()
        if not group_id or not preferred_name:
            raise ValueError("equivalence groups require group_id and preferred_name")
        evidence = group.get("evidence", {})
        group_rows.append(
            (
                group_id,
                preferred_name,
                str(group.get("parent_family_group_id") or "") or None,
                str(group.get("equivalence_kind", "exact_phase")),
                str(group.get("confidence", "reviewed")),
                str(group.get("curation_status", "active")),
                json.dumps(evidence, sort_keys=True, separators=(",", ":")),
            )
        )
    member_rows: list[tuple[Any, ...]] = []
    for member in members:
        reference_id = str(member["reference_id"]).strip()
        group_id = str(member["group_id"]).strip()
        if not reference_id or not group_id:
            raise ValueError("equivalence members require reference_id and group_id")
        member_rows.append(
            (
                reference_id,
                group_id,
                str(member.get("cod_id") or "") or None,
                str(member.get("member_kind", "member")),
                str(member.get("mapping_status", "reviewed")),
            )
        )
    return sorted(set(group_rows), key=lambda row: row[0]), sorted(set(member_rows), key=lambda row: row[0])


def _content_hash(group_rows: list[tuple[Any, ...]], member_rows: list[tuple[Any, ...]]) -> str:
    payload = json.dumps({"groups": group_rows, "members": member_rows}, sort_keys=True, separators=(",", ":"), default=str).encode()
    return _sha256_bytes(payload)


def build_equivalence_sidecar(
    path: Path | str,
    *,
    source_sha256: str,
    cache_sha256: str,
    groups: Iterable[Mapping[str, Any]],
    members: Iterable[Mapping[str, Any]],
    method_version: str = EQUIVALENCE_METHOD_VERSION,
) -> "EquivalenceBuildResult":
    """Build a deterministic sidecar atomically from reviewed mappings."""

    source_hash = _validate_hash(source_sha256, "source_sha256")
    cache_hash = _validate_hash(cache_sha256, "cache_sha256")
    group_rows, member_rows = _canonical_rows(groups, members)
    group_ids = {row[0] for row in group_rows}
    if any(row[1] not in group_ids for row in member_rows):
        raise ValueError("every equivalence member must reference a declared group")
    content_hash = _content_hash(group_rows, member_rows)
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.building")
    try:
        with closing(sqlite3.connect(temporary)) as connection:
            connection.executescript(
                """
                PRAGMA user_version = 1;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE equivalence_groups (
                    group_id TEXT PRIMARY KEY,
                    preferred_name TEXT NOT NULL,
                    parent_family_group_id TEXT,
                    equivalence_kind TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    curation_status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                );
                CREATE TABLE equivalence_members (
                    reference_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL REFERENCES equivalence_groups(group_id),
                    cod_id TEXT,
                    member_kind TEXT NOT NULL,
                    mapping_status TEXT NOT NULL
                );
                CREATE INDEX equivalence_members_group_idx ON equivalence_members(group_id);
                """
            )
            metadata = {
                "schema_version": EQUIVALENCE_SCHEMA_VERSION,
                "method_version": method_version,
                "source_sha256": source_hash,
                "cache_sha256": cache_hash,
                "content_sha256": content_hash,
                "build_status": "building",
            }
            connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", sorted(metadata.items()))
            connection.executemany("INSERT INTO equivalence_groups VALUES (?, ?, ?, ?, ?, ?, ?)", group_rows)
            connection.executemany("INSERT INTO equivalence_members VALUES (?, ?, ?, ?, ?)", member_rows)
            connection.execute("UPDATE metadata SET value = 'complete' WHERE key = 'build_status'")
            connection.commit()
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return EquivalenceBuildResult(destination, content_hash, len(group_rows), len(member_rows))


@dataclass(frozen=True)
class EquivalenceBuildResult:
    path: Path
    content_sha256: str
    group_count: int
    member_count: int


class EquivalenceSidecar:
    """Read-only access to active curated mappings."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    @classmethod
    def open(
        cls,
        path: Path | str,
        *,
        expected_source_sha256: str | None = None,
        expected_cache_sha256: str | None = None,
    ) -> "EquivalenceSidecar":
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise EquivalenceError(f"NOT_FOUND: {resolved}")
        try:
            connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            metadata = {str(row["key"]): str(row["value"]) for row in connection.execute("SELECT key, value FROM metadata")}
            if metadata.get("build_status") != "complete":
                raise EquivalenceError("INCOMPLETE")
            if metadata.get("schema_version") != EQUIVALENCE_SCHEMA_VERSION:
                raise EquivalenceError("SCHEMA_UNSUPPORTED")
            group_rows = [tuple(row) for row in connection.execute(
                "SELECT group_id, preferred_name, parent_family_group_id, equivalence_kind, confidence, curation_status, evidence_json FROM equivalence_groups ORDER BY group_id"
            )]
            member_rows = [tuple(row) for row in connection.execute(
                "SELECT reference_id, group_id, cod_id, member_kind, mapping_status FROM equivalence_members ORDER BY reference_id"
            )]
            if metadata.get("content_sha256") != _content_hash(group_rows, member_rows):
                raise EquivalenceError("CONTENT_HASH_MISMATCH")
            if expected_source_sha256 is not None and metadata.get("source_sha256") != _validate_hash(expected_source_sha256, "source_sha256"):
                raise EquivalenceError("SOURCE_CHANGED")
            if expected_cache_sha256 is not None and metadata.get("cache_sha256") != _validate_hash(expected_cache_sha256, "cache_sha256"):
                raise EquivalenceError("CACHE_CHANGED")
            return cls(connection)
        except EquivalenceError:
            connection.close()
            raise
        except sqlite3.Error as exc:
            try:
                connection.close()
            except UnboundLocalError:
                pass
            raise EquivalenceError("UNREADABLE") from exc

    def lookup(self, reference_id: str) -> EquivalenceMetadata | None:
        row = self._connection.execute(
            """
            SELECT m.reference_id, m.cod_id, g.group_id, g.preferred_name,
                   g.parent_family_group_id, g.equivalence_kind, g.confidence
            FROM equivalence_members AS m
            JOIN equivalence_groups AS g ON g.group_id = m.group_id
            WHERE m.reference_id = ? AND g.curation_status = 'active'
            """,
            (reference_id,),
        ).fetchone()
        if row is None:
            return None
        return EquivalenceMetadata(
            reference_id=str(row["reference_id"]),
            group_id=str(row["group_id"]),
            preferred_name=str(row["preferred_name"]),
            parent_family_group_id=str(row["parent_family_group_id"]) if row["parent_family_group_id"] else None,
            equivalence_kind=str(row["equivalence_kind"]),
            confidence=str(row["confidence"]),
            cod_id=str(row["cod_id"]) if row["cod_id"] else None,
        )

    def metadata(self) -> dict[str, str]:
        return {str(row["key"]): str(row["value"]) for row in self._connection.execute("SELECT key, value FROM metadata")}

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "EquivalenceSidecar":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*(?:\.\d+)?)")
_SOURCE_PHASE_LABEL = re.compile(r"^(?P<formula>.+?)_(?P<space_group>\d+)_\(icsd_(?P<icsd>\d+)\)-(?P<variant>.+)$", re.IGNORECASE)


def _formula_composition(formula: str) -> dict[str, float] | None:
    """Parse a conservative composition key without guessing chemistry.

    POW_COD and Precursor labels use several harmless formatting variants
    (spaces, parentheses, hydration separators, and near-integer occupancies).
    We compare the element/count tokens only; malformed or unsupported text is
    returned as ``None`` and can never create an equivalence cluster.
    """

    if not isinstance(formula, str) or not formula.strip():
        return None
    text = formula.replace(" ", "").replace("·", ".")
    tokens = list(_FORMULA_TOKEN.finditer(text))
    if not tokens:
        return None
    totals: dict[str, float] = {}
    for token in tokens:
        element, raw_count = token.groups()
        try:
            count = float(raw_count) if raw_count else 1.0
        except ValueError:
            return None
        if not math.isfinite(count) or count <= 0:
            return None
        totals[element] = totals.get(element, 0.0) + count
    return totals


def _formula_compatible(left: str, right: str) -> bool:
    first = _formula_composition(left)
    second = _formula_composition(right)
    if first is None or second is None or set(first) != set(second):
        return False
    first_scale = max(first.values())
    second_scale = max(second.values())
    for element in first:
        a, b = first[element] / first_scale, second[element] / second_scale
        if abs(a - b) > max(0.02, 0.02 * max(abs(a), abs(b), 1.0)):
            return False
    return True


def formulas_compatible(left: str, right: str) -> bool:
    """Public conservative formula comparison used by validation receipts."""

    return _formula_compatible(left, right)


def parse_source_phase_label(label: str) -> dict[str, Any] | None:
    """Extract formula/space-group evidence from a Precursor label.

    Five source records use a compact ``formula_name(icsd)`` spelling without
    an explicit space-group number.  Those labels remain usable for formula
    matching, but a strict resolution requires a unique runtime group.
    """

    if not isinstance(label, str) or not label.strip():
        return None
    match = _SOURCE_PHASE_LABEL.fullmatch(label.strip())
    if match is not None:
        return {
            "source_label": label.strip(),
            "formula": match.group("formula").strip(),
            "space_group_number": int(match.group("space_group")),
            "icsd_id": match.group("icsd"),
            "variant": match.group("variant"),
        }
    # Compact entries such as ``KH2PO4(51075)`` have no reliable SG field.
    compact = re.match(r"^(?P<formula>[A-Z].*?)\((?P<icsd>\d+)\)$", label.strip())
    if compact is None:
        compact = re.match(r"^(?P<formula>[A-Z][A-Za-z0-9.()]+)_(?P<icsd>\d+)$", label.strip())
    if compact is None:
        return None
    return {
        "source_label": label.strip(),
        "formula": compact.group("formula").split("_", 1)[0].strip(),
        "space_group_number": None,
        "icsd_id": compact.group("icsd"),
        "variant": None,
    }


def space_group_number(value: str | None) -> int | None:
    """Resolve a crystallographic space-group symbol without guessing."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        import gemmi  # type: ignore

        group = gemmi.find_spacegroup_by_name(value)
        if group is not None:
            return int(group.number)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    common = {
        "p 1": 1,
        "p -1": 2,
        "p 21/c": 14,
        "p n -3 m": 224,
        "f m -3 m": 225,
    }
    return common.get(" ".join(value.casefold().split()))


def _formula_signature(formula: str) -> str | None:
    composition = _formula_composition(formula)
    if composition is None:
        return None
    scale = max(composition.values())
    return ";".join(
        f"{element}:{value / scale:.3f}".rstrip("0").rstrip(".")
        for element, value in sorted(composition.items())
    )


def _space_group_key(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return " ".join(value.casefold().split())


def _line_angles(reference: ReferencePhase, radiation: Radiation) -> tuple[float, ...]:
    values: list[float] = []
    for line in reference.lines:
        try:
            angle = two_theta_from_d(float(line.d_spacing_angstrom), radiation)
        except (TypeError, ValueError):
            continue
        if 0.0 <= angle <= 120.0 and math.isfinite(angle):
            values.append(float(angle))
    return tuple(sorted(set(round(value, 8) for value in values)))


def _line_similarity(first: tuple[float, ...], second: tuple[float, ...], tolerance: float) -> tuple[int, float]:
    """Greedy one-to-one line pairing; returns (shared, Jaccard similarity).

    Each ``first`` value, in order, takes the closest still-unpaired ``second``
    value within ``tolerance`` (ties: lowest remaining index). For a strictly
    increasing ``second`` (the sorted unique angles from ``_line_angles``)
    the closest remaining value is always one of the two bisection neighbours,
    which gives the same pairing in O(n log n) instead of O(n^2).
    """

    if not first or not second:
        return 0, 0.0
    if all(left < right for left, right in zip(second, second[1:])):
        remaining_sorted = list(second)
        shared = 0
        for value in first:
            position = bisect_left(remaining_sorted, value)
            best_index = -1
            best_distance = 0.0
            for index in (position - 1, position):
                if 0 <= index < len(remaining_sorted):
                    distance = abs(value - remaining_sorted[index])
                    if distance <= tolerance and (best_index < 0 or distance < best_distance):
                        best_index = index
                        best_distance = distance
            if best_index < 0:
                continue
            remaining_sorted.pop(best_index)
            shared += 1
        denominator = len(first) + len(second) - shared
        return shared, shared / denominator if denominator else 0.0
    remaining = list(second)
    shared = 0
    for value in first:
        candidates = [(abs(value - other), index) for index, other in enumerate(remaining) if abs(value - other) <= tolerance]
        if not candidates:
            continue
        _distance, index = min(candidates, key=lambda item: (item[0], item[1]))
        remaining.pop(index)
        shared += 1
    denominator = len(first) + len(second) - shared
    return shared, shared / denominator if denominator else 0.0


def _meaningful_name(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    name = " ".join(value.split()).strip()
    if not name or name.casefold() in {"unknown", "none", "n/a"}:
        return None
    if re.fullmatch(r"cod[ -]?\d+", name, flags=re.IGNORECASE):
        return None
    return name


def _name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _match_status(score: float, matched: int) -> str:
    if matched < 2 or score < 0.35:
        return "unresolved"
    if score >= 0.75:
        return "supported"
    return "tentative"


def _cluster_compatible(
    left: tuple[ReferencePhase, CandidateMatch],
    right: tuple[ReferencePhase, CandidateMatch],
    line_cache: Mapping[str, tuple[float, ...]],
    radiation: Radiation,
    settings: RuntimeEquivalenceSettings,
) -> tuple[bool, int, float]:
    first, first_match = left
    second, second_match = right
    if not _formula_compatible(first.formula, second.formula):
        return False, 0, 0.0
    first_space = _space_group_key(first.space_group)
    second_space = _space_group_key(second.space_group)
    if first_space is None or second_space is None or first_space != second_space:
        return False, 0, 0.0
    if abs(float(first_match.score) - float(second_match.score)) > settings.score_spread_max:
        return False, 0, 0.0
    first_lines = line_cache.get(first.reference_id)
    if first_lines is None:
        first_lines = _line_angles(first, radiation)
    second_lines = line_cache.get(second.reference_id)
    if second_lines is None:
        second_lines = _line_angles(second, radiation)
    shared, similarity = _line_similarity(first_lines, second_lines, settings.line_tolerance_deg)
    if shared < settings.min_shared_lines or similarity < settings.min_line_similarity:
        return False, shared, similarity
    return True, shared, similarity


def resolve_on_demand_equivalences(
    references: Iterable[ReferencePhase],
    matches: Iterable[CandidateMatch],
    radiation: Radiation,
    *,
    settings: RuntimeEquivalenceSettings | None = None,
) -> RuntimeEquivalenceResult:
    """Resolve equivalent POW_COD candidates for one analysis only.

    The input pool is already bounded by the selected reference store.  A
    complete-linkage pass prevents transitive chains from joining candidates
    whose score spread is too large.  The resolver returns one immutable
    representative per coherent cluster and a receipt containing all member
    IDs; it never writes a persistent grouping table.
    """

    config = (settings or RuntimeEquivalenceSettings()).validate()
    reference_map = {reference.reference_id: reference for reference in references}
    usable: list[tuple[ReferencePhase, CandidateMatch]] = []
    for match in matches:
        reference = reference_map.get(match.reference_id)
        if reference is not None:
            usable.append((reference, match))
    usable.sort(key=lambda item: (-float(item[1].score), item[1].reference_id))
    line_cache = {reference.reference_id: _line_angles(reference, radiation) for reference, _match in usable}

    clusters: list[list[tuple[ReferencePhase, CandidateMatch]]] = []
    pair_evidence: dict[tuple[str, str], tuple[int, float]] = {}
    for item in usable:
        placed = False
        for cluster in clusters:
            checks: list[tuple[int, float]] = []
            compatible = True
            for member in cluster:
                ok, shared, similarity = _cluster_compatible(item, member, line_cache, radiation, config)
                if not ok:
                    compatible = False
                    break
                checks.append((shared, similarity))
            if compatible and checks:
                cluster.append(item)
                for member, evidence in zip(cluster[:-1], checks, strict=True):
                    key = tuple(sorted((member[0].reference_id, item[0].reference_id)))
                    pair_evidence[key] = evidence
                placed = True
                break
        if not placed:
            clusters.append([item])

    representatives: list[ReferencePhase] = []
    aggregate_matches: list[CandidateMatch] = []
    receipt_groups: list[dict[str, Any]] = []
    for cluster in clusters:
        cluster.sort(key=lambda item: (-float(item[1].score), item[1].reference_id))
        representative, representative_match = cluster[0]
        member_ids = tuple(sorted(item[0].reference_id for item in cluster))
        scores = tuple(float(item[1].score) for item in cluster)
        score_spread = max(scores) - min(scores) if scores else 0.0
        similarities = [
            similarity
            for left_index, left in enumerate(cluster)
            for right in cluster[left_index + 1 :]
            for _shared, similarity in [
                _line_similarity(
                    line_cache[left[0].reference_id],
                    line_cache[right[0].reference_id],
                    config.line_tolerance_deg,
                )
            ]
        ]
        line_similarity = min(similarities) if similarities else 1.0
        names: dict[str, list[str]] = {}
        for reference, _match in cluster:
            name = _meaningful_name(reference.name)
            if name is not None:
                names.setdefault(_name_key(name), []).append(name)
        named_key, named_values = (max(names.items(), key=lambda item: (len(item[1]), item[0])) if names else (None, []))
        name_consensus = bool(
            named_values
            and len(named_values) >= 2
            and len(named_values) / len(cluster) >= config.name_consensus_fraction
        )
        resolved_name = named_values[0] if name_consensus else representative.name
        if len(cluster) == 1:
            group_id = representative.equivalence_group_id or representative.duplicate_group_id
            resolution = "singleton_reference"
            equivalence_kind = representative.equivalence_kind
            confidence = representative.equivalence_confidence
        else:
            digest = _sha256_bytes(_canonical_json({
                "method_version": config.method_version,
                "configuration_sha256": config.configuration_sha256,
                "radiation": radiation.key,
                "member_ids": member_ids,
            }))[:20]
            group_id = f"runtime:eq:{digest}"
            resolution = "consensus_named" if name_consensus else "unnamed_coherent_set"
            equivalence_kind = "runtime_similarity"
            confidence = "high" if line_similarity >= 0.8 and score_spread <= 0.10 else "bounded"
        representative_reference = ReferencePhase(
            **{
                **representative.__dict__,
                "name": resolved_name,
                "equivalence_group_id": group_id,
                "equivalence_kind": equivalence_kind,
                "equivalence_confidence": confidence,
            }
        )
        representatives.append(representative_reference)
        total_weight = sum(max(float(item[1].matched_peaks), 1.0) for item in cluster)
        aggregate_score = sum(
            float(item[1].score) * max(float(item[1].matched_peaks), 1.0) for item in cluster
        ) / max(total_weight, 1.0)
        aggregate_matched = max(item[1].matched_peaks for item in cluster)
        aggregate_expected = max(item[1].expected_peaks for item in cluster)
        aggregate_coverage = aggregate_matched / max(aggregate_expected, 1)
        rmse_values = [
            (float(item[1].position_rmse_deg), max(float(item[1].matched_peaks), 1.0))
            for item in cluster
            if item[1].position_rmse_deg is not None
        ]
        aggregate_rmse = (
            sum(value * weight for value, weight in rmse_values) / sum(weight for _value, weight in rmse_values)
            if rmse_values
            else None
        )
        evidence: list[str] = []
        for _reference, match in cluster:
            for line in match.evidence:
                if line not in evidence:
                    evidence.append(line)
        if len(cluster) > 1:
            evidence.append(
                f"On-demand equivalence set contains {len(cluster)} POW_COD entries; "
                f"minimum line similarity {line_similarity:.3f}, score spread {score_spread:.3f}."
            )
        aggregate_matches.append(
            CandidateMatch(
                reference_id=representative.reference_id,
                name=resolved_name,
                formula=representative.formula,
                score=max(0.0, min(1.0, aggregate_score)),
                status=_match_status(aggregate_score, aggregate_matched),
                matched_peaks=aggregate_matched,
                expected_peaks=aggregate_expected,
                coverage=aggregate_coverage,
                position_rmse_deg=aggregate_rmse,
                evidence=tuple(evidence[:6]),
                duplicate_group_id=representative.duplicate_group_id,
                equivalence_group_id=group_id,
                parent_family_group_id=representative.parent_family_group_id,
                equivalence_kind=equivalence_kind,
                equivalence_confidence=confidence,
                equivalence_member_ids=member_ids,
                equivalence_label=(resolved_name if name_consensus else None),
                equivalence_resolution=resolution,
                space_group=representative.space_group,
            )
        )
        receipt_groups.append(
            {
                "group_id": group_id or representative.reference_id,
                "member_reference_ids": list(member_ids),
                "representative_reference_id": representative.reference_id,
                "member_count": len(cluster),
                "formula": representative.formula,
                "formula_signature": _formula_signature(representative.formula),
                "space_group": representative.space_group,
                "name": resolved_name if name_consensus else None,
                "name_status": "consensus" if name_consensus else ("unnamed" if len(cluster) > 1 else "single"),
                "line_similarity_min": float(line_similarity),
                "score_min": min(scores) if scores else None,
                "score_max": max(scores) if scores else None,
                "score_spread": float(score_spread),
                "resolution": resolution,
            }
        )
    order = sorted(range(len(aggregate_matches)), key=lambda index: (-aggregate_matches[index].score, aggregate_matches[index].reference_id))
    sorted_matches = tuple(aggregate_matches[index] for index in order)
    sorted_references = tuple(representatives[index] for index in order)
    receipt_base: dict[str, Any] = {
        "schema_version": RUNTIME_EQUIVALENCE_SCHEMA_VERSION,
        "method_version": config.method_version,
        "configuration": config.to_dict(),
        "configuration_sha256": config.configuration_sha256,
        "radiation": radiation.key,
        "input_candidate_count": len(usable),
        "output_group_count": len(sorted_matches),
        "groups": sorted(receipt_groups, key=lambda item: str(item["group_id"])),
    }
    receipt = {**receipt_base, "receipt_sha256": _sha256_bytes(_canonical_json(receipt_base))}
    return RuntimeEquivalenceResult(sorted_references, sorted_matches, receipt)


__all__ = [
    "EQUIVALENCE_METHOD_VERSION",
    "EQUIVALENCE_SCHEMA_VERSION",
    "RUNTIME_EQUIVALENCE_METHOD_VERSION",
    "RUNTIME_EQUIVALENCE_SCHEMA_VERSION",
    "EquivalenceBuildResult",
    "EquivalenceError",
    "EquivalenceMetadata",
    "EquivalenceSidecar",
    "RuntimeEquivalenceResult",
    "RuntimeEquivalenceSettings",
    "build_equivalence_sidecar",
    "formulas_compatible",
    "parse_source_phase_label",
    "resolve_on_demand_equivalences",
    "space_group_number",
]
