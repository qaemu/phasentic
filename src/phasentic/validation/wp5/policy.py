"""Frozen evaluation-policy defaults for the WP-5 Precursor campaign.

The policy deliberately separates the benchmark window from the indexed
reference range.  Raw scans remain auditable in full; only the primary
matching trace is bounded to the declared 2theta window.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


WP5_EVALUATION_POLICY_VERSION = "wp5-precursor-evaluation-policy-3"
WP5_PRIMARY_TWO_THETA_MAX_DEG = 100.0
WP5_PHASE_AGREEMENT_TOP_N = 5
WP5_PHASE_AGREEMENT_MINIMUM_RATIO = 0.80
WP5_PHASE_MATCH_LEVEL = "strict"
WP5_PHASE_MATCH_LEVELS = ("strict", "family", "elements")


def evaluation_policy_from_query(query: Mapping[str, Any]) -> dict[str, float | int | str]:
    """Read and validate the policy fields from a frozen protocol query.

    Older frozen bundles do not contain these fields.  They receive the
    current versioned defaults so the revised policy is applied explicitly
    and recorded in the resulting run provenance.
    """

    if not isinstance(query, Mapping):
        raise ValueError("evaluation policy query must be an object")
    raw_upper = query.get("primary_two_theta_max_deg", WP5_PRIMARY_TWO_THETA_MAX_DEG)
    raw_top_n = query.get("phase_agreement_top_n", WP5_PHASE_AGREEMENT_TOP_N)
    raw_ratio = query.get("phase_agreement_minimum_ratio", WP5_PHASE_AGREEMENT_MINIMUM_RATIO)
    raw_level = query.get("phase_match_level", WP5_PHASE_MATCH_LEVEL)
    if raw_level not in WP5_PHASE_MATCH_LEVELS:
        raise ValueError(f"phase_match_level must be one of {WP5_PHASE_MATCH_LEVELS}")
    if isinstance(raw_upper, bool) or not isinstance(raw_upper, (int, float)):
        raise ValueError("primary_two_theta_max_deg must be numeric")
    upper = float(raw_upper)
    if not math.isfinite(upper) or not 0.0 < upper <= 180.0:
        raise ValueError("primary_two_theta_max_deg must be in (0, 180]")
    if isinstance(raw_top_n, bool) or not isinstance(raw_top_n, int) or raw_top_n < 1:
        raise ValueError("phase_agreement_top_n must be a positive integer")
    if isinstance(raw_ratio, bool) or not isinstance(raw_ratio, (int, float)):
        raise ValueError("phase_agreement_minimum_ratio must be numeric")
    ratio = float(raw_ratio)
    if not math.isfinite(ratio) or not 0.0 < ratio <= 1.0:
        raise ValueError("phase_agreement_minimum_ratio must be in (0, 1]")
    return {
        "version": WP5_EVALUATION_POLICY_VERSION,
        "primary_two_theta_max_deg": upper,
        "phase_agreement_top_n": raw_top_n,
        "phase_agreement_minimum_ratio": ratio,
        "phase_match_level": raw_level,
    }
