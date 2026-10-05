"""The pure tick function (D6): step(state, commands, rng, world) -> StepResult.

It mutates `state` in place and reads nothing but its arguments: no clock, env, files or globals.
`world` is static scenario/terrain context; its link cache never changes results (values are snapped).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from kohra.comms.burst import ge_step
from kohra.comms.gnss import step_offset
from kohra.comms.injects import InjectError, apply_inject
from kohra.comms.queue import enqueue, process_nets
from kohra.observe.perception import record_delivery, record_sent
from kohra.scenario.schema import INJECT_ARGS
from kohra.sim import decision_points, detect, outcome, scripts
from kohra.sim.move import advance, on_road, speed_mps
from kohra.sim.rng import Rng
from kohra.sim.state import State
from kohra.sim.world import World

SOURCE_RANK = {"ds": 0, "scenario": 0, "player": 1, "bot": 1}
ORDER_KIND = {"MOVE": "order_move", "HALT": "order_halt", "HOLD": "order_hold", "OBSERVE": "order_observe",
              "WITHDRAW": "order_withdraw", "REQUEST_SITREP": "order_request_sitrep",
              "FIRE_MISSION": "order_fire_mission"}


@dataclass
class StepResult:
    tick: int
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    player_msgs: list[dict[str, Any]] = field(default_factory=list)


def command_key(c: dict[str, Any]) -> tuple[int, int, str, int]:
    return int(c["apply_tick"]), SOURCE_RANK[c["source"]], str(c["source_id"]), int(c["client_seq"])


def step(state: State, commands: list[dict[str, Any]], rng: Rng, world: World) -> StepResult:
    res = StepResult(state.tick)
    ev = res.events
    for c in sorted(commands, key=command_key):
        _apply_command(state, world, rng, c, res)
    _expire(state, ev)
    scripts.run_red_plan(state, world, ev)
    scripts.run_bn_script(state, world, rng, ev)
    _move(state, world)
    _gnss(state, world)
    for jid in sorted(state.jammers):
        j = state.jammers[jid]
        if j.active and j.mode == "intermittent":
            j.bad = ge_step(j.bad, j.ge_p, j.ge_r, rng.burst)
    dets = detect.detect_all(state, world, rng)
    scripts.standing_rules(state, world, rng, dets)
    outcome.attrition(state, world)
    resolved = outcome.fire_missions(state, world, rng)
    for fm in resolved:
        ev.append(("fire_impact", {"grid": fm["grid"], "hit": fm["hit"], "ref": fm["ref"]}))
    scripts.fire_status(state, world, rng, resolved)
    deliveries = process_nets(state, world, rng, ev)
    for dv in deliveries:
        if dv.receiver == state.player:
            res.player_msgs.append(record_delivery(state, dv))
    scripts.react(state, world, rng, deliveries, ev)
    decision_points.check(state, world, ev)
    state.tick += 1
    return res


def _apply_command(state: State, world: World, rng: Rng, c: dict[str, Any], res: StepResult) -> None:
    p = c["payload"]
    if c["type"] == "inject":
        try:
            info = apply_inject(state, world, rng, INJECT_ARGS[p["kind"]].model_validate(p["args"]))
            res.events.append(("inject_fired", {"kind": p["kind"], "args": p["args"], "late": c.get("late", False),
                                                **info}))
        except InjectError as e:
            res.events.append(("inject_failed", {"kind": p["kind"], "error": str(e)}))
        return
    player = state.unit_by_callsign(state.player)
    to = state.unit_by_callsign(p["to"])
    if player is None or to is None:
        res.events.append(("order_rejected", {"reason": "unknown addressee", "seq": c["client_seq"]}))
        return
    net = p.get("net") or scripts.common_net(player, to)
    if net is None or net not in player.nets or net not in to.nets:
        res.events.append(("order_rejected", {"reason": "no common net", "seq": c["client_seq"]}))
        return
    if c["type"] == "text":
        m = enqueue(state, world, rng, sender=player.callsign, to=to.callsign, net=net, kind="free", fields={},
                    precedence=p["precedence"], grade=None, text=p["text"])
    else:
        fields = {"to": to.callsign, "from": player.callsign, "grid": p.get("grid") or "", "speed": p.get("speed")
                  or "tactical"}
        m = enqueue(state, world, rng, sender=player.callsign, to=to.callsign, net=net, kind=ORDER_KIND[p["kind"]],
                    fields=fields, precedence=p["precedence"], grade=None)
    res.player_msgs.append(record_sent(state, m))
    # Confidence, relied_on and rationale are recorded here and never transmitted (D14).
    res.events.append(("order_applied", {"msg": m.msg_id, "kind": p.get("kind", "TEXT"), "to": to.callsign,
                                         "net": net, "confidence": p.get("confidence"),
                                         "relied_on": p.get("relied_on"), "rationale": p.get("rationale"),
                                         "source": c["source"]}))


def _expire(state: State, ev: list[tuple[str, dict[str, Any]]]) -> None:
    for jid in sorted(state.jammers):
        e = state.jammers[jid].expires
        if e is not None and state.tick >= e:
            del state.jammers[jid]
            ev.append(("jammer_expired", {"id": jid}))
    state.gnss_zones = [z for z in state.gnss_zones if z["expires"] is None or state.tick < z["expires"]]


def _move(state: State, world: World) -> None:
    sc = world.scenario
    for uid in sorted(state.units):
        u = state.units[uid]
        if not u.path or u.strength <= 0:
            continue
        v = speed_mps(sc.movement.speed_mps, u.mobility, u.speed, on_road(world.terrain, u.x, u.y))
        u.x, u.y, rest = advance(u.x, u.y, [(p[0], p[1]) for p in u.path], v * sc.tick_seconds)
        u.path = [[x, y] for x, y in rest]
        if not u.path:
            u.arrived_tick = state.tick
            u.status = "in position"
            if u.posture == "moving":
                u.posture = "stationary"
    for jid in sorted(state.jammers):
        j = state.jammers[jid]
        if j.owner and j.owner in state.units:
            j.x, j.y = state.units[j.owner].x, state.units[j.owner].y


def _gnss(state: State, world: World) -> None:
    dt = world.scenario.tick_seconds
    for uid in sorted(state.units):
        u = state.units[uid]
        if u.side != "blue":
            continue
        zone = next((z for z in state.gnss_zones if math.hypot(u.x - z["x"], u.y - z["y"]) <= z["radius_m"]), None)
        if zone is None and u.gnss_offset == [0.0, 0.0]:
            continue
        if zone is not None:
            u.gnss_recover_mps = zone["recover_mps"]
            off = step_offset((u.gnss_offset[0], u.gnss_offset[1]), True, zone["bearing_deg"], zone["rate_mps"],
                              zone["max_offset_m"], zone["recover_mps"], dt)
        else:
            off = step_offset((u.gnss_offset[0], u.gnss_offset[1]), False, 0.0, 0.0, 0.0, u.gnss_recover_mps, dt)
        u.gnss_offset = [off[0], off[1]]
