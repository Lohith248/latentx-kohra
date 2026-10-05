"""Half-duplex nets with a precedence queue (6.5), per-tick SINR sampling and delivery draws (6.3)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from kohra.comms.delivery import airtime_ticks, is_partial, p_final
from kohra.comms.sinr import Emitter, JammerSignal, sinr_db
from kohra.comms.tiers import PRECEDENCE_RANK
from kohra.reports.build import garble, render
from kohra.sim.rng import Rng
from kohra.sim.state import Message, State, Unit
from kohra.sim.world import World

ID_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


@dataclass
class Delivery:
    msg: Message
    receiver: str
    text: str
    partial: bool


def new_msg_id(state: State, rng: Rng) -> str:
    while True:
        mid = "M-" + "".join(ID_ALPHABET[int(i)] for i in rng.ids.integers(len(ID_ALPHABET), size=4))
        if mid not in state.used_ids:
            state.used_ids[mid] = state.tick
            return mid


def enqueue(state: State, world: World, rng: Rng, *, sender: str, to: str, net: str, kind: str,
            fields: dict[str, str], precedence: str, grade: str | None, phrasing: int | None = None,
            text: str | None = None, planted: bool = False, contact_no: str | None = None,
            meta: dict[str, Any] | None = None) -> Message:
    """Render (unless free text), assign an opaque ID and queue on the net."""
    if text is None:
        text, phrasing = render(kind, fields, phrasing, rng.reports)
    ns = state.nets[net]
    extra = ns.delay_extra if state.tick < ns.delay_until else 0.0
    handling = world.scenario.comms.handling_delay_s[precedence]
    state.msg_seq += 1
    m = Message(
        seq=state.msg_seq, msg_id=new_msg_id(state, rng), net=net, sender=sender, to=to, kind=kind,
        phrasing=phrasing if phrasing is not None else -1, fields=dict(fields), text=text, precedence=precedence,
        grade=grade, enqueue_tick=state.tick,
        eligible_tick=state.tick + math.ceil((handling + extra) / world.scenario.tick_seconds),
        is_planted=planted, contact_no=contact_no, meta=dict(meta or {}),
    )
    state.messages[str(m.seq)] = m
    ns.queue.append(m.seq)
    return m


def emitter(u: Unit) -> Emitter:
    return Emitter(u.x, u.y, u.antenna_m, u.power_dbm, u.gain_dbi)


def jammer_signals(state: State) -> list[JammerSignal]:
    return [JammerSignal(Emitter(j.x, j.y, j.antenna_m, j.power_dbm, j.gain_dbi), j.freq_mhz, j.bandwidth_khz)
            for _k, j in sorted(state.jammers.items()) if j.emitting]


def receivers(state: State, net: str, sender: str) -> list[Unit]:
    out = [u for u in state.units.values() if net in u.nets and u.callsign != sender and u.strength > 0]
    return sorted(out, key=lambda u: u.callsign)


def link_sinr(state: State, world: World, net_id: str, tx: Unit, rx: Unit, jams: list[JammerSignal]) -> float:
    n = world.net(net_id)
    return sinr_db(world.terrain, world.scenario.comms.link_model, emitter(tx), emitter(rx), n.freq_mhz,
                   n.bandwidth_khz, jams, world.link_cache)


def _sample(state: State, world: World, m: Message, jams: list[JammerSignal]) -> None:
    tx = state.unit_by_callsign(m.sender)
    for rx in receivers(state, m.net, m.sender):
        s = link_sinr(state, world, m.net, tx, rx, jams) if tx else -math.inf
        m.sinr_min[rx.callsign] = min(m.sinr_min.get(rx.callsign, math.inf), s)


def _finish(state: State, world: World, rng: Rng, m: Message, events: list[tuple[str, dict[str, Any]]]
            ) -> list[Delivery]:
    lm = world.scenario.comms.link_model
    cut = state.tick < state.nets[m.net].cut_until
    out = []
    for cs in sorted(m.sinr_min):
        s = m.sinr_min[cs]
        p = p_final(s, lm, 0.0, cut) if math.isfinite(s) else 0.0
        u = float(rng.comms.random())
        ok = u < p
        partial = bool(ok and is_partial(s, lm))
        text = m.text
        if partial and m.phrasing >= 0 and float(rng.comms.random()) < lm.partial_field_drop_p:
            text, _ = render(m.kind, garble(m.kind, m.phrasing, m.fields, rng.comms), m.phrasing, rng.reports)
        events.append(("message_rx", {"msg": m.msg_id, "rx": cs, "delivered": ok, "partial": partial,
                                      "sinr_eff": round(s, 3) if math.isfinite(s) else None, "p": round(p, 4),
                                      "cut": cut}))
        if ok:
            out.append(Delivery(m, cs, text, partial))
    return out


def process_nets(state: State, world: World, rng: Rng, events: list[tuple[str, dict[str, Any]]]) -> list[Delivery]:
    """Advance every net one tick. Order: nets by id; receivers by callsign (deterministic draws)."""
    jams = jammer_signals(state)
    deliveries: list[Delivery] = []
    for net_id in sorted(state.nets):
        ns = state.nets[net_id]
        if ns.current is None:
            eligible = [state.messages[str(s)] for s in ns.queue if state.messages[str(s)].eligible_tick <= state.tick]
            if eligible:
                m = min(eligible, key=lambda x: (PRECEDENCE_RANK[x.precedence], x.eligible_tick, x.seq))
                ns.queue.remove(m.seq)
                n = world.net(net_id)
                m.tx_start = state.tick
                m.tx_end = state.tick + airtime_ticks(m.text, world.scenario.comms.link_model, n.data_rate_bps,
                                                      world.scenario.tick_seconds) - 1
                ns.current = m.seq
                events.append(("message_tx", {"msg": m.msg_id, "net": net_id, "from": m.sender, "to": m.to,
                                              "kind": m.kind, "text": m.text, "precedence": m.precedence,
                                              "grade": m.grade, "planted": m.is_planted, "end": m.tx_end}))
        if ns.current is None:
            continue
        m = state.messages[str(ns.current)]
        _sample(state, world, m, jams)
        if state.tick >= (m.tx_end or 0):
            deliveries += _finish(state, world, rng, m, events)
            ns.current = None
            del state.messages[str(m.seq)]
    return deliveries
