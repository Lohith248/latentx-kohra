"""Instructor injects (D20). Each is a logged, replayable command applied at its tick."""

from __future__ import annotations

import math
from typing import Any

from kohra.comms.queue import enqueue
from kohra.scenario.schema import (
    GnssZoneAdd,
    JammerAdd,
    JammerMove,
    JammerRemove,
    NetCut,
    NetDelay,
    PlantedReport,
    Strict,
)
from kohra.sim.rng import Rng
from kohra.sim.scripts import resolve_fields
from kohra.sim.state import Jammer, State
from kohra.sim.world import World


class InjectError(ValueError):
    pass


def apply_inject(state: State, world: World, rng: Rng, a: Strict) -> dict[str, Any]:
    """Apply a parsed inject; returns a summary for the log. Raises InjectError if it cannot apply."""
    dt = world.scenario.tick_seconds
    if isinstance(a, JammerAdd):
        x, y = world.to_xy(a.lonlat)
        state.jammers[a.id] = Jammer(
            id=a.id, owner=None, x=x, y=y, power_dbm=a.power_dbm, antenna_m=a.antenna_m, gain_dbi=a.gain_dbi,
            freq_mhz=a.freq_mhz, bandwidth_khz=a.bandwidth_khz, mode=a.mode, ge_p=a.ge.p if a.ge else 0.0,
            ge_r=a.ge.r if a.ge else 1.0, active=True,
            expires=state.tick + math.ceil(a.duration_s / dt) if a.duration_s else None)
    elif isinstance(a, JammerMove):
        j = _jammer(state, a.id)
        j.x, j.y = world.to_xy(a.lonlat)
        j.owner = None
    elif isinstance(a, JammerRemove):
        _jammer(state, a.id)
        del state.jammers[a.id]
    elif isinstance(a, NetCut):
        _net(state, a.net).cut_until = state.tick + math.ceil(a.duration_s / dt)
    elif isinstance(a, NetDelay):
        ns = _net(state, a.net)
        ns.delay_extra, ns.delay_until = a.extra_s, state.tick + math.ceil(a.duration_s / dt)
    elif isinstance(a, PlantedReport):
        _net(state, a.net)
        if state.unit_by_callsign(a.from_callsign) is None or state.unit_by_callsign(a.to_callsign) is None:
            raise InjectError("planted_report: unknown callsign")
        fields = {"callsign": a.from_callsign, **resolve_fields(a.fields, state, world)}
        m = enqueue(state, world, rng, sender=a.from_callsign, to=a.to_callsign, net=a.net, kind=a.template,
                    fields=fields, precedence=a.precedence, grade=a.grade, phrasing=a.phrasing, planted=True)
        return {"msg": m.msg_id}
    elif isinstance(a, GnssZoneAdd):
        x, y = world.to_xy(a.lonlat)
        state.gnss_zones.append({
            "id": a.id, "x": x, "y": y, "radius_m": a.radius_m, "bearing_deg": a.bearing_deg, "rate_mps": a.rate_mps,
            "max_offset_m": a.max_offset_m, "recover_mps": a.recover_mps if a.recover_mps is not None else a.rate_mps,
            "expires": state.tick + math.ceil(a.duration_s / dt) if a.duration_s else None})
    return {}


def _jammer(state: State, jid: str) -> Jammer:
    if jid not in state.jammers:
        raise InjectError(f"unknown jammer {jid}")
    return state.jammers[jid]


def _net(state: State, net: str) -> Any:
    if net not in state.nets:
        raise InjectError(f"unknown net {net}")
    return state.nets[net]
