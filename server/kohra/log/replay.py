"""Replay a run log: re-run step() from the embedded scenario with the logged commands (by apply_tick,
ignoring wall-clock time) and compare every logged state hash."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kohra.log.events import read_events
from kohra.scenario.load import parse_scenario
from kohra.sim.rng import Rng
from kohra.sim.state import initial_state, state_hash
from kohra.sim.step import step
from kohra.sim.world import build_world


@dataclass
class ReplayResult:
    ok: bool
    final_hash: str | None
    first_mismatch_tick: int | None
    hashes: list[tuple[int, str]] = field(default_factory=list)


def replay(path: str | Path) -> ReplayResult:
    start: dict[str, Any] | None = None
    cmds: dict[int, list[dict[str, Any]]] = {}
    expected: dict[int, str] = {}
    end_tick: int | None = None
    for _tick, kind, p in read_events(path, ("run_start", "command", "state_hash", "endex")):
        if kind == "run_start" and start is None:
            start = p
        elif kind == "command":
            cmds.setdefault(int(p["apply_tick"]), []).append(p)
        elif kind == "state_hash":
            expected[int(p["tick"])] = p["hash"]
        elif kind == "endex":
            end_tick = int(p["tick"])
    if start is None:
        raise ValueError("log has no run_start")
    scenario = parse_scenario(start["scenario_text"]).model_copy(update={"seed": start["seed"]})
    world = build_world(scenario)
    state = initial_state(scenario, world)
    rng = Rng(scenario.seed)
    end = end_tick if end_tick is not None else max(expected, default=0)
    got: list[tuple[int, str]] = []
    while state.tick < end:
        step(state, cmds.get(state.tick, []), rng, world)
        if state.tick in expected:
            h = state_hash(state, rng)
            got.append((state.tick, h))
            if h != expected[state.tick]:
                return ReplayResult(False, h, state.tick, got)
    return ReplayResult(True, got[-1][1] if got else None, None, got)
