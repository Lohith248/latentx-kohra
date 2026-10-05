"""Decision points: logged when their trigger fires (the rubric is M2)."""

from __future__ import annotations

from typing import Any

from kohra.sim.scripts import trigger_fires
from kohra.sim.state import State
from kohra.sim.world import World


def check(state: State, world: World, events: list[tuple[str, dict[str, Any]]]) -> None:
    for dp in world.scenario.decision_points:
        if dp.id not in state.fired_dp and trigger_fires(dp.when, state, world):
            state.fired_dp.append(dp.id)
            events.append(("decision_point", {"id": dp.id, "describes": dp.describes}))
