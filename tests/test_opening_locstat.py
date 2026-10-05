"""An opening LOCSTAT round gives the commander a picture in the first minute."""

from __future__ import annotations

from kohra.rooms import Runner

from tests.conftest import flat_world


def test_every_platoon_reports_position_in_the_first_minute(ridge, flat_ridge_world) -> None:  # type: ignore[no-untyped-def]
    assert ridge[0].blue_script.standing_rules.initial_locstat_s == 8
    r = Runner(ridge[0], ridge[1], world=flat_ridge_world, end_tick=60)
    r.run_to_end()
    senders = {e["from"] for e in r.state.perception.inbox if e["fields"].get("type") == "locstat"}
    assert {"TIGER-1", "TIGER-2", "TIGER-3"} <= senders


def test_default_keeps_the_first_round_at_the_interval(ridge) -> None:  # type: ignore[no-untyped-def]
    rules = ridge[0].blue_script.standing_rules.model_copy(update={"initial_locstat_s": None})
    scen = ridge[0].model_copy(update={"blue_script": ridge[0].blue_script.model_copy(update={"standing_rules": rules})})
    r = Runner(scen, ridge[1], world=flat_world(scen), end_tick=60)
    r.run_to_end()
    assert not [e for e in r.state.perception.inbox if e["fields"].get("type") == "locstat"]
