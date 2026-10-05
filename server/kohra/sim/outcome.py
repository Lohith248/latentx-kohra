"""Deterministic attrition from tables (D24); RNG only for fire-mission impact scatter."""

from __future__ import annotations

import math
from typing import Any

from kohra.sim.rng import Rng
from kohra.sim.state import State
from kohra.sim.world import World

CEP_TO_SIGMA = 1.0 / 1.1774  # CEP = 1.1774 sigma for a circular normal


def attrition(state: State, world: World) -> None:
    """Every pair of opposing units within the attacker's engage range with LOS trades fire this tick."""
    oc = world.scenario.outcomes
    tick_min = world.scenario.tick_seconds / 60.0
    ids = sorted(state.units)
    losses = dict.fromkeys(ids, 0.0)
    engaged = dict.fromkeys(ids, False)
    for a_id in ids:
        a = state.units[a_id]
        rng_m = oc.engage_range_m.get(a.type, 0.0)
        if a.strength < oc.combat_ineffective_below or rng_m <= 0:
            continue
        for t_id in ids:
            t = state.units[t_id]
            if t.side == a.side or t.strength <= 0:
                continue
            if math.hypot(t.x - a.x, t.y - a.y) > rng_m:
                continue
            if not world.terrain.los(a.x, a.y, 2.0, t.x, t.y, 2.0):
                continue
            rate = oc.attrition_per_min[a.type][t.posture]
            losses[t_id] += rate * 100.0 * tick_min * a.strength / 100.0
            engaged[a_id] = engaged[t_id] = True
    for uid in ids:
        u = state.units[uid]
        u.strength = max(u.strength - losses[uid], 0.0)
        u.engaged = engaged[uid]


def fire_missions(state: State, world: World, rng: Rng) -> list[dict[str, Any]]:
    """Resolve missions whose impact tick has come. Returns the resolved missions."""
    fm = world.scenario.outcomes.fire_mission
    done, keep = [], []
    for m in state.fire_missions:
        if m["impact_tick"] > state.tick:
            keep.append(m)
            continue
        dx, dy = (float(v) for v in rng.outcome.normal(0.0, fm.cep_m * CEP_TO_SIGMA, size=2))
        ix, iy = m["x"] + dx, m["y"] + dy
        hit = []
        for uid in sorted(state.units):
            u = state.units[uid]
            if u.strength > 0 and math.hypot(u.x - ix, u.y - iy) <= fm.radius_m:
                u.strength = max(u.strength - fm.damage_pct, 0.0)
                hit.append(uid)
        done.append({**m, "impact_x": ix, "impact_y": iy, "hit": hit})
    state.fire_missions = keep
    return done
