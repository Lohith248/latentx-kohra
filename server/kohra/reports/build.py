"""Render templated message text. Phrasing comes from the `reports` stream unless fixed."""

from __future__ import annotations

import numpy as np

from kohra.reports.parse import CALLSIGN_FIELDS, GARBLED, all_templates, template_fields


def render(kind: str, fields: dict[str, str], phrasing: int | None, rng: np.random.Generator) -> tuple[str, int]:
    phrasings = all_templates()[kind]
    i = int(rng.integers(len(phrasings))) if phrasing is None else phrasing
    return phrasings[i].format(**fields), i


def garble(kind: str, phrasing: int, fields: dict[str, str], rng: np.random.Generator) -> dict[str, str]:
    """Replace one non-callsign field (chosen by rng) with [garbled] (D18). No-op if none exist."""
    names = [f for f in template_fields(all_templates()[kind][phrasing]) if f not in CALLSIGN_FIELDS]
    if not names:
        return fields
    victim = names[int(rng.integers(len(names)))]
    return {**fields, victim: GARBLED}


def enemy_summary(contacts: list[tuple[str, str, str]]) -> str:
    """'platoon APC moving S and section infantry stationary', or 'nil'."""
    return " and ".join(f"{s} {u} {a}" for s, u, a in contacts) or "nil"
