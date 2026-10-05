"""view_for(): the ONLY path from simulation state to a player socket. It reads the perception store
(what reached the player) and the player's own GNSS fix, never truth about other units."""

from __future__ import annotations

from typing import Any

from kohra.comms.queue import jammer_signals, link_sinr, receivers
from kohra.comms.sinr import Emitter, JammerSignal, jammer_noise_radius_m
from kohra.sim.clock import clock_str
from kohra.sim.state import State
from kohra.sim.world import World
from kohra.wire import (
    DsEvent,
    DsHello,
    DsJammer,
    DsLink,
    DsState,
    DsUnit,
    PHello,
    PHistory,
    PNet,
    PPlace,
    PRadio,
    PRoute,
    PStation,
    PStatus,
)


def _clock(world: World, tick: int) -> str:
    return clock_str(world.scenario.start_clock, tick, world.scenario.tick_seconds)


def _places(world: World) -> tuple[list[PPlace], list[PRoute]]:
    sc = world.scenario
    return ([PPlace(name=p.name, kind=p.kind, lonlat=p.lonlat) for p in sc.places],
            [PRoute(name=r.name, points=list(r.points)) for r in sc.routes])


def hello_for(state: State, world: World, basemap_kind: str) -> PHello:
    sc = world.scenario
    me = sc.player_unit()
    places, routes = _places(world)
    stations = [PStation(callsign=u.callsign or "", nets=list(u.radio.nets))
                for u in sc.sides["blue"].units if u.radio and u.callsign and u.id != me.id]
    return PHello(
        title=sc.title, classification=sc.classification_label, callsign=me.callsign or "", stations=stations,
        nets=[PNet(id=n.id, name=n.name) for n in sc.comms.nets if me.radio and n.id in me.radio.nets],
        places=places, routes=routes, bbox=sc.terrain.bbox, grid_affine=world.grid_affine(),
        start_clock=sc.start_clock, duration_ticks=sc.duration_ticks, tick_seconds=sc.tick_seconds,
        synthetic=world.terrain.synthetic, basemap_kind=basemap_kind,  # type: ignore[arg-type]
        labels=dict(sc.labels), own_sidc=me.sidc)


def radio_msg(world: World, e: dict[str, Any]) -> PRadio:
    return PRadio(msg_id=e["msg_id"], tick=e["tick"], clock=_clock(world, e["tick"]), net=e["net"], sender=e["from"],
                  to=e["to"], precedence=e["precedence"], text=e["text"], fields=e["fields"], grade=e["grade"],
                  partial=e["partial"], contact_no=e["contact_no"], direction=e["direction"])


def history_for(state: State, world: World) -> PHistory:
    allmsgs = sorted(state.perception.inbox + state.perception.sent, key=lambda e: (e["tick"], e["msg_id"]))
    return PHistory(messages=[radio_msg(world, e) for e in allmsgs])


def status_for(state: State, world: World, speed: float, paused: bool, endex: bool, final_hash: str | None
               ) -> PStatus:
    me = state.unit_by_callsign(state.player)
    assert me is not None
    hq = world.to_lonlat(me.x + me.gnss_offset[0], me.y + me.gnss_offset[1])  # own GNSS fix, may be spoofed
    return PStatus(tick=state.tick, clock=_clock(world, state.tick), hq_lonlat=(round(hq[0], 6), round(hq[1], 6)),
                   last_heard=dict(sorted(state.perception.last_heard.items())), speed=speed, paused=paused,
                   endex=endex, final_hash=final_hash)


def view_for(player: str, state: State, world: World, new_msgs: list[dict[str, Any]], speed: float,
             paused: bool, endex: bool, final_hash: str | None) -> list[dict[str, Any]]:
    """Frames for one player after a tick: new radio traffic, then status. Returns JSON-ready dicts."""
    assert player == state.player
    frames: list[dict[str, Any]] = [radio_msg(world, e).model_dump() for e in new_msgs]
    frames.append(status_for(state, world, speed, paused, endex, final_hash).model_dump())
    return frames


# ================================ DS truth view ================================================


def ds_hello(world: World, basemap_kind: str) -> DsHello:
    sc = world.scenario
    places, routes = _places(world)
    return DsHello(title=sc.title, classification=sc.classification_label, places=places, routes=routes,
                   bbox=sc.terrain.bbox, synthetic=world.terrain.synthetic,
                   basemap_kind=basemap_kind,  # type: ignore[arg-type]
                   start_clock=sc.start_clock, duration_ticks=sc.duration_ticks)


def ds_state(state: State, world: World, events: list[dict[str, Any]], endex: bool, final_hash: str | None) -> DsState:
    lm = world.scenario.comms.link_model
    units = [DsUnit(id=u.id, side=u.side, callsign=u.callsign, sidc=u.sidc, lonlat=world.to_lonlat(u.x, u.y),
                    strength=round(u.strength, 1), posture=u.posture, status=u.status)
             for _k, u in sorted(state.units.items())]
    coy = world.scenario.comms.nets[0]
    jammers = []
    for jid, j in sorted(state.jammers.items()):
        sig = JammerSignal(Emitter(j.x, j.y, j.antenna_m, j.power_dbm, j.gain_dbi), j.freq_mhz, j.bandwidth_khz)
        jammers.append(DsJammer(id=jid, lonlat=world.to_lonlat(j.x, j.y), active=j.active, emitting=j.emitting,
                                radius_m=round(jammer_noise_radius_m(lm, sig, 2.0, coy.freq_mhz, coy.bandwidth_khz))))
    jams = jammer_signals(state)
    links = []
    hq = state.unit_by_callsign(state.player)
    if hq is not None:
        for net in sorted(hq.nets):
            for rx in receivers(state, net, hq.callsign):
                s = link_sinr(state, world, net, hq, rx, jams)
                links.append(DsLink(net=net, a=hq.callsign, b=rx.callsign, a_lonlat=world.to_lonlat(hq.x, hq.y),
                                    b_lonlat=world.to_lonlat(rx.x, rx.y), sinr_db=round(s, 1)))
    return DsState(tick=state.tick, clock=_clock(world, state.tick), theta_db=lm.theta_db, units=units,
                   jammers=jammers, links=links,
                   events=[DsEvent(tick=e["tick"], clock=_clock(world, e["tick"]), kind=e["kind"], detail=e["detail"])
                           for e in events],
                   endex=endex, final_hash=final_hash)
