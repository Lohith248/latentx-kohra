"""Parse delivered message text back into structured fields (D17: the player only ever gets parse(text)).

Every template phrasing is compiled into one regex whose field groups accept either the field
vocabulary or the literal `[garbled]` (which parses to None).
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import yaml

GARBLED = "[garbled]"
DIRECTIONS = ["NE", "NW", "SE", "SW", "N", "E", "S", "W"]  # two-letter first: regex alternation is ordered
SIZES = ["single", "pair", "section", "platoon", "company"]
UNIT_TYPES = ["EW detachment", "infantry", "APC", "tank", "recce", "vehicle", "unknown"]
ACTIVITIES = [f"moving {d}" for d in DIRECTIONS] + ["stationary", "digging in", "firing"]

VOCAB: dict[str, list[str]] = {
    "size": SIZES,
    "unit_type": UNIT_TYPES,
    "activity": ACTIVITIES,
    "direction": DIRECTIONS,
    "posture": ["moving", "holding", "observing", "withdrawing"],
    "status": ["in position", "moving", "halted", "engaged"],
    "fire_state": ["rounds complete", "cannot comply", "shot"],
    "speed": ["tactical", "fast"],
    "task": ["SECURE", "OCCUPY", "SCREEN", "DEFEND", "CLEAR"],
}

_ALT = {k: "|".join(re.escape(v) for v in vals) for k, vals in VOCAB.items()}
_SUMMARY_ONE = rf"(?:{_ALT['size']}) (?:{_ALT['unit_type']}) (?:{_ALT['activity']})"
PATTERNS: dict[str, str] = {
    **_ALT,
    "callsign": r"[A-Z]+(?:-\d)?",
    "to": r"[A-Z]+(?:-\d)?",
    "from": r"[A-Z]+(?:-\d)?",
    "grid": r"\d{3} \d{3}",
    "time": r"\d{4}",
    "by_time": r"\d{4}",
    "strength_pct": r"100|[1-9]?\d",
    "ref": r"M-[0-9A-Z]{4}",
    "place_name": r"[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*)*",
    "enemy_summary": rf"nil|{_SUMMARY_ONE}(?: and {_SUMMARY_ONE})*",
}
CALLSIGN_FIELDS = frozenset({"callsign", "to", "from"})
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@cache
def all_templates() -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for name in ("reports.yaml", "orders.yaml"):
        data = yaml.safe_load((TEMPLATE_DIR / name).read_text(encoding="utf-8"))
        out.update({k: tuple(v) for k, v in data.items()})
    return out


def template_fields(tpl: str) -> list[str]:
    return re.findall(r"\{(\w+)\}", tpl)


@cache
def _compiled() -> tuple[tuple[str, int, re.Pattern[str]], ...]:
    out = []
    for kind, phrasings in all_templates().items():
        for i, tpl in enumerate(phrasings):
            rx, pos = "", 0
            for m in re.finditer(r"\{(\w+)\}", tpl):
                rx += re.escape(tpl[pos : m.start()])
                name = m[1]
                alt = PATTERNS[name] if name in CALLSIGN_FIELDS else f"{PATTERNS[name]}|{re.escape(GARBLED)}"
                rx += f"(?P<{name}>{alt})"
                pos = m.end()
            rx += re.escape(tpl[pos:])
            out.append((kind, i, re.compile(rx)))
    return tuple(out)


def parse(text: str) -> dict[str, str | None]:
    """Structured fields recovered from text. `type` is the template kind, or "free" if nothing matches."""
    for kind, _i, rx in _compiled():
        m = rx.fullmatch(text)
        if m:
            fields: dict[str, str | None] = {"type": kind}
            fields.update({k: (None if v == GARBLED else v) for k, v in m.groupdict().items()})
            return fields
    return {"type": "free"}


def matching_templates(text: str) -> list[tuple[str, int]]:
    """All (kind, phrasing) whose regex matches; used by the ambiguity test."""
    return [(k, i) for k, i, rx in _compiled() if rx.fullmatch(text)]
