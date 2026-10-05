"""D14: orders need an integer confidence 0-100 and a relied_on list; rejections never touch the sim."""

from __future__ import annotations

from pathlib import Path

import pytest
from kohra.log.events import read_events
from kohra.rooms import Runner
from kohra.scenario.schema import Scenario
from kohra.sim.world import World

GOOD = {"type": "order", "to": "TIGER-1", "kind": "MOVE", "grid": "045 020", "speed": "tactical",
        "confidence": 60, "relied_on": []}
BAD = [
    {k: v for k, v in GOOD.items() if k != "confidence"},
    {k: v for k, v in GOOD.items() if k != "relied_on"},
    {**GOOD, "confidence": 50.5},
    {**GOOD, "confidence": "50"},
    {**GOOD, "confidence": 101},
    {**GOOD, "confidence": -1},
    {**GOOD, "confidence": None},
    {**GOOD, "relied_on": "M-1234"},
    {**GOOD, "grid": None},
    {**GOOD, "to": "R-MECH"},
    {**GOOD, "to": "NOBODY"},
    {**GOOD, "kind": "NUKE"},
    {**GOOD, "extra": 1},
]


def _run(ridge: tuple[Scenario, str], world: World, log: Path, orders: list[dict]) -> Runner:  # type: ignore[type-arg]
    r = Runner(ridge[0], ridge[1], world=world, log_path=log, end_tick=120)
    while not r.done:
        if r.state.tick == 10:
            for o in orders:
                r.submit_player(o)
        r.advance()
    r.finish()
    return r


@pytest.mark.parametrize("i", range(len(BAD)))
def test_rejected_and_hash_unchanged(ridge, flat_ridge_world, tmp_path, i) -> None:  # type: ignore[no-untyped-def]
    base = _run(ridge, flat_ridge_world, tmp_path / "base.sqlite", [])
    probe = Runner(ridge[0], ridge[1], world=flat_ridge_world, end_tick=1)
    assert not probe.submit_player(BAD[i]).ok
    bad = _run(ridge, flat_ridge_world, tmp_path / "bad.sqlite", [BAD[i]])
    assert bad.hashes == base.hashes and bad.final_hash == base.final_hash
    kinds = [k for _t, k, _p in read_events(tmp_path / "bad.sqlite")]
    assert "order_rejected" in kinds and "command" not in kinds


def test_rationale_logged_never_transmitted(ridge, flat_ridge_world, tmp_path) -> None:  # type: ignore[no-untyped-def]
    why = "Hold the ford before red recce arrives"
    r = _run(ridge, flat_ridge_world, tmp_path / "why.sqlite", [{**GOOD, "rationale": why}])
    applied = [p for _t, k, p in read_events(tmp_path / "why.sqlite") if k == "order_applied"]
    assert applied and applied[0]["rationale"] == why
    tx = [p for _t, k, p in read_events(tmp_path / "why.sqlite") if k == "message_tx" and p["msg"] == applied[0]["msg"]]
    assert tx and why not in tx[0]["text"] and "rationale" not in r.state.perception.sent[0]


@pytest.mark.parametrize("bad", ["x" * 141, "caf\u00e9"])
def test_rationale_validated(ridge, flat_ridge_world, bad) -> None:  # type: ignore[no-untyped-def]
    probe = Runner(ridge[0], ridge[1], world=flat_ridge_world, end_tick=1)
    assert not probe.submit_player({**GOOD, "rationale": bad}).ok


def test_valid_order_accepted_and_confidence_logged_not_sent(ridge, flat_ridge_world, tmp_path) -> None:  # type: ignore[no-untyped-def]
    r = _run(ridge, flat_ridge_world, tmp_path / "ok.sqlite", [{**GOOD, "confidence": 0, "relied_on": ["M-ABCD"]}])
    applied = [p for _t, k, p in read_events(tmp_path / "ok.sqlite") if k == "order_applied"]
    assert applied and applied[0]["confidence"] == 0 and applied[0]["relied_on"] == ["M-ABCD"]
    tx = [p for _t, k, p in read_events(tmp_path / "ok.sqlite") if k == "message_tx" and p["msg"] == applied[0]["msg"]]
    assert tx and "60" not in tx[0]["text"] and "confidence" not in tx[0]["text"].lower()
    assert "confidence" not in r.state.perception.sent[0]
