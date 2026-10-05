"""The after-action review is built from the run log alone."""

from __future__ import annotations

from kohra.cli import main as cli
from kohra.reports.aar import build_aar
from kohra.rooms import Bot, Runner
from kohra.scenario.load import load_bot, load_injects
from kohra.scenario.schema import Inject

from tests.conftest import BOT, DEMO_INJECTS

PLANTED_INTSUM = Inject.model_validate({"at_tick": 5, "kind": "planted_report", "args": {
    "net": "BN", "from_callsign": "ANVIL", "to_callsign": "TIGER", "template": "intsum", "phrasing": 1,
    "fields": {"size": "platoon", "unit_type": "tank", "grid_from_place": "TAMARIND", "direction": "SW", "time": "auto"},
    "grade": "C3", "precedence": "IMMEDIATE"}})


def test_flags_an_order_based_on_a_planted_report(ridge, flat_ridge_world, tmp_path) -> None:  # type: ignore[no-untyped-def]
    log = tmp_path / "planted.sqlite"
    r = Runner(ridge[0], ridge[1], world=flat_ridge_world, log_path=log, end_tick=240)
    r.schedule_inject(PLANTED_INTSUM, source="ds", source_id="test")
    planted = None
    while not r.done:
        if planted is None:
            planted = next((e["msg_id"] for e in r.state.perception.inbox if e["fields"].get("type") == "intsum"), None)
            if planted:
                res = r.submit_player({"type": "order", "to": "ANVIL", "kind": "FIRE_MISSION",
                                       "grid": flat_ridge_world.place_grid("TAMARIND"), "confidence": 75,
                                       "relied_on": [planted], "rationale": "Tank platoon reported in TAMARIND"})
                assert res.ok, res.reason
        r.advance()
    r.finish()
    assert planted, "the planted INTSUM never reached the player"
    page = build_aar(log, verify=False)
    assert "After-action review" in page and "Decision log" in page
    assert "DS deception inject" in page and "No other report was cited." in page
    assert "Tank platoon reported in TAMARIND" in page
    assert "(planted)" in page


def test_verifies_chain_and_replay_and_cli_writes_file(ridge, terrain_available, tmp_path) -> None:  # type: ignore[no-untyped-def]
    log = tmp_path / "run.sqlite"
    r = Runner(ridge[0], ridge[1], log_path=log, end_tick=300)
    for inj in load_injects(DEMO_INJECTS):
        r.schedule_inject(inj, source="ds", source_id="file")
    r.run_to_end(Bot(load_bot(BOT)))
    page = build_aar(log)
    assert "hash chain intact" in page and "replay reproduces the final state" in page
    assert "06:00:30" in page and "06:01:30" in page  # the bot's two orders before tick 300
    out = tmp_path / "out.aar.html"
    assert cli(["aar", str(log), "-o", str(out), "--no-verify"]) == 0
    assert "Debrief points" in out.read_text(encoding="utf-8")
