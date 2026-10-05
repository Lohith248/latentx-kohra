"""K-05: every template x phrasing x 200 random field sets round-trips; [garbled] parses to None."""

from __future__ import annotations

import zlib

import numpy as np
import pytest
from kohra.reports.build import enemy_summary, garble, render
from kohra.reports.grade import detection_quality, grade
from kohra.reports.parse import (
    ACTIVITIES,
    CALLSIGN_FIELDS,
    SIZES,
    UNIT_TYPES,
    VOCAB,
    all_templates,
    matching_templates,
    parse,
    template_fields,
)

CALLSIGNS = ["TIGER", "TIGER-1", "TIGER-2", "TIGER-3", "ANVIL"]
PLACES = ["Ford OSPREY", "KESTREL Ridge", "Pt HERON", "TAMARIND", "WILLOW X"]


def random_value(name: str, g: np.random.Generator) -> str:
    def pick(xs: list[str]) -> str:
        return xs[int(g.integers(len(xs)))]
    if name in VOCAB:
        return pick(VOCAB[name])
    if name in CALLSIGN_FIELDS:
        return pick(CALLSIGNS)
    if name == "grid":
        return f"{int(g.integers(1000)):03d} {int(g.integers(1000)):03d}"
    if name in ("time", "by_time"):
        return f"{int(g.integers(24)):02d}{int(g.integers(60)):02d}"
    if name == "strength_pct":
        return str(int(g.integers(101)))
    if name == "ref":
        return "M-" + "".join(pick(list("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")) for _ in range(4))
    if name == "place_name":
        return pick(PLACES)
    if name == "enemy_summary":
        n = int(g.integers(3))
        return enemy_summary([(pick(SIZES), pick(UNIT_TYPES), pick(ACTIVITIES)) for _ in range(n)])
    raise KeyError(name)


CASES = [(k, i) for k, ph in all_templates().items() for i in range(len(ph))]


def test_nine_report_types_three_phrasings() -> None:
    reports = [k for k in all_templates() if not k.startswith("order_")]
    assert len(reports) == 9
    assert all(len(all_templates()[k]) == 3 for k in all_templates())


@pytest.mark.parametrize("kind,phrasing", CASES)
def test_roundtrip(kind: str, phrasing: int) -> None:
    g = np.random.default_rng(zlib.crc32(f"{kind}/{phrasing}".encode()))
    names = template_fields(all_templates()[kind][phrasing])
    for _ in range(200):
        fields = {n: random_value(n, g) for n in names}
        text, _ = render(kind, fields, phrasing, g)
        assert matching_templates(text) == [(kind, phrasing)], text
        assert parse(text) == {"type": kind, **fields}


@pytest.mark.parametrize("kind,phrasing", CASES)
def test_garbled_parses_to_none(kind: str, phrasing: int) -> None:
    g = np.random.default_rng(5)
    names = template_fields(all_templates()[kind][phrasing])
    fields = {n: random_value(n, g) for n in names}
    bad = garble(kind, phrasing, fields, g)
    text, _ = render(kind, bad, phrasing, g)
    got = parse(text)
    assert got["type"] == kind
    for n in names:
        assert got[n] == (None if bad[n] == "[garbled]" else fields[n])
    assert all(got[c] is not None for c in names if c in CALLSIGN_FIELDS)


def test_free_text() -> None:
    assert parse("TIGER. SITREP follows. All platoons in position. Over.") == {"type": "free"}


def test_grading() -> None:
    cfg = {"reliability_by_source": {"own_patrol": "B", "unknown": "F"}, "unknown_credibility": 6,
           "credibility_by_quality": [{"min_q": 0.8, "grade": 2}, {"min_q": 0.6, "grade": 3}, {"min_q": 0.4, "grade": 4},
                                      {"min_q": 0.0, "grade": 5}]}
    assert grade(cfg, "own_patrol", 0.9) == "B2"
    assert grade(cfg, "own_patrol", 0.65) == "B3"
    assert grade(cfg, "own_patrol", 0.1) == "B5"
    assert grade(cfg, "martian", None) == "F6"
    assert detection_quality(500, 2500, "moving") == pytest.approx(0.8)
    assert detection_quality(500, 2500, "dug_in") == pytest.approx(0.48)
    assert detection_quality(3000, 2500, "moving") == 0
