"""Label-blind tune/check split of the Precursor development cases.

Step-5 tuning used a 70/30 split (seed 20260930): settings were chosen on the
tune set and the untouched check set exposed overfitting. All cases remain
development material; nothing here is held-out evidence.
"""

from __future__ import annotations

import hashlib
from typing import Sequence


class StagedTuningError(ValueError):
    """Raised for unsafe or inconsistent split inputs."""


def _ordered(case_ids: Sequence[str], salt: str) -> list[str]:
    return sorted(case_ids, key=lambda case_id: (hashlib.sha256(f"{salt}|{case_id}".encode()).hexdigest(), case_id))


def split_case_ids(case_ids: Sequence[str], *, seed: int, tune_fraction: float) -> tuple[list[str], list[str]]:
    """Label-blind split: order by a salted hash of the case ID only."""

    unique = sorted(set(case_ids))
    if len(unique) < 2:
        raise StagedTuningError("at least two cases are required to split")
    ordered = _ordered(unique, f"split-{seed}")
    tune_count = min(len(unique) - 1, max(1, round(len(unique) * tune_fraction)))
    return sorted(ordered[:tune_count]), sorted(ordered[tune_count:])
