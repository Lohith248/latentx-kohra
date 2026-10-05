"""Source reliability (A-F) x information credibility (1-6) grading from config/grading.yaml."""

from __future__ import annotations

from typing import Any


def detection_quality(r: float, r_max: float, posture: str) -> float:
    factor = {"moving": 1.0, "stationary": 0.8, "dug_in": 0.6}[posture]
    return min(max(1.0 - r / r_max, 0.0), 1.0) * factor


def grade(cfg: dict[str, Any], source_type: str, q: float | None) -> str:
    rel = cfg["reliability_by_source"].get(source_type, cfg["reliability_by_source"]["unknown"])
    if q is None:
        return f"{rel}{cfg['unknown_credibility']}"
    for row in cfg["credibility_by_quality"]:  # ordered high to low
        if q >= row["min_q"]:
            return f"{rel}{row['grade']}"
    return f"{rel}{cfg['unknown_credibility']}"
