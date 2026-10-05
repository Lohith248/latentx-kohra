"""Scripted forces: trigger evaluation, the red plan, Bn HQ traffic, blue standing rules and the scripted
stations' reactions to delivered orders (D15, D16, D25)."""

from __future__ import annotations

import functools
import math
from typing import Any

from kohra.comms.queue import Delivery, enqueue
from kohra.comms.tiers import TEMPLATE_PRECEDENCE
from kohra.reports.build import enemy_summary
from kohra.reports.grade import grade
from kohra.reports.parse import parse
from kohra.scenario.schema import Action, Trigger
from kohra.sim.clock import hhmm
from kohra.sim.detect import UNIT_TYPE_WORD, Detection
from kohra.sim.move import plan_path, route_waypoints
from kohra.sim.rng import Rng
from kohra.sim.state import Message, State, Track, Unit
from kohra.sim.world import World

Events = list[tuple[str, dict[str, Any]]]
GRID_ORDERS = {"order_move", "order_observe", "order_withdraw", "order_fire_mission"}
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(dx: float, dy: float) -> str:
    return COMPASS[int(((math.degrees(math.atan2(dx, dy)) + 360 + 22.5) % 360) // 45)]


def time_now(state: State, world: World) -> str:
    return hhmm(world.scenario.start_clock, state.tick, world.scenario.tick_seconds)


# ---- triggers -----------------------------------------------------------------------------------


def trigger_fires(trig: Trigger, state: State, world: World) -> bool:
    if trig.at_tick is not None:
        return state.tick >= trig.at_tick
    if trig.contact is not None:
        u = state.units[trig.contact.unit]
        if u.strength <= 0:
            return False
        for k in sorted(state.units):
            e = state.units[k]
            if e.side == u.side or e.strength <= 0 or math.hypot(e.x - u.x, e.y - u.y) > trig.contact.within_m:
                continue
            if not trig.contact.los or world.terrain.los(u.x, u.y, 2.0, e.x, e.y, 2.0):
                return True
        return False
    if trig.strength_below is not None:
        return state.units[trig.strength_below.unit].strength < trig.strength_below.pct
    if trig.arrived is not None:
        return state.units[trig.arrived.unit].arrived_tick >= 0
    if trig.observed is not None:
        tgt = trig.observed.unit
        return any(tgt in tr for tr in state.tracks.values())
    return False


# ---- movement orders ----------------------------------------------------------------------------


def set_path(unit: Unit, waypoints: list[tuple[float, float]], speed: str) -> None:
    unit.path = [[float(x), float(y)] for x, y in waypoints]
    unit.speed = speed
    unit.arrived_tick = -1
    if unit.path:
        unit.posture, unit.status = "moving", "moving"


def stop(unit: Unit, status: str = "halted", posture: str = "stationary") -> None:
    unit.path = []
    unit.status, unit.posture = status, posture


def go_to(world: World, unit: Unit, goal: tuple[float, float], speed: str, via_route: str | None = None) -> None:
    if via_route:
        wps = route_waypoints(world.routes_xy[via_route], (unit.x, unit.y), goal)
    else:
        wps = plan_path(world.terrain, world.cost[unit.mobility], (unit.x, unit.y), goal)
    set_path(unit, wps, speed)


def apply_action(a: Action, state: State, world: World) -> None:
    u = state.units[a.unit]
    goal = world.places_xy[a.to_place] if a.to_place else world.to_xy(a.to) if a.to else None
    if a.action in ("move", "withdraw") and goal is not None:
        go_to(world, u, goal, "fast" if a.action == "withdraw" else a.speed, a.via_route)
    elif a.action == "halt":
        stop(u)
    elif a.action == "hold":
        stop(u, "in position", "dug_in")
    elif a.action == "posture" and a.value:
        u.posture = a.value
    elif a.action in ("jammer_on", "jammer_off") and a.jammer in state.jammers:
        state.jammers[a.jammer].active = a.action == "jammer_on"


def run_red_plan(state: State, world: World, events: Events) -> None:
    for i, rule in enumerate(world.scenario.red_plan):
        if i in state.fired_red or not trigger_fires(rule.when, state, world):
            continue
        state.fired_red.append(i)
        for a in rule.do:
            apply_action(a, state, world)
        events.append(("red_rule", {"index": i, "actions": [a.model_dump(exclude_none=True) for a in rule.do]}))


# ---- Bn HQ script -------------------------------------------------------------------------------


def resolve_fields(fields: dict[str, str], state: State, world: World) -> dict[str, str]:
    out = {}
    for k, v in fields.items():
        if k == "grid_from_place":
            out["grid"] = world.place_grid(v)
        elif k == "time" and v == "auto":
            out["time"] = time_now(state, world)
        else:
            out[k] = v
    return out


def common_net(a: Unit, b: Unit) -> str | None:
    return next((n for n in a.nets if n in b.nets), None)


def run_bn_script(state: State, world: World, rng: Rng, events: Events) -> None:
    bn = next((state.units[k] for k in sorted(state.units) if state.units[k].role == "bn_hq"), None)
    player = state.unit_by_callsign(state.player)
    if bn is None or player is None:
        return
    for i, sm in enumerate(world.scenario.blue_script.bn_hq.messages):
        if i in state.fired_bn or not trigger_fires(sm.when, state, world):
            continue
        state.fired_bn.append(i)
        net = common_net(bn, player)
        if net is None:
            continue
        fields = {"callsign": bn.callsign, **resolve_fields(sm.fields, state, world)}
        m = enqueue(state, world, rng, sender=bn.callsign, to=player.callsign, net=net, kind=sm.template,
                    fields=fields, precedence=sm.precedence, grade=sm.grade or world.grading["status_grade"],
                    phrasing=sm.phrasing)
        events.append(("bn_script", {"index": i, "msg": m.msg_id}))


# ---- blue standing rules ------------------------------------------------------------------------


def _scripted_blue(state: State) -> list[Unit]:
    return [state.units[k] for k in sorted(state.units)
            if state.units[k].side == "blue" and state.units[k].role == "platoon" and state.units[k].strength > 0]


def _report(state: State, world: World, rng: Rng, u: Unit, kind: str, fields: dict[str, str],
            grade_: str | None = None, contact_no: str | None = None) -> None:
    player = state.unit_by_callsign(state.player)
    net = common_net(u, player) if player else None
    if net is None or player is None:
        return
    enqueue(state, world, rng, sender=u.callsign, to=player.callsign, net=net, kind=kind,
            fields={"callsign": u.callsign, **fields}, precedence=TEMPLATE_PRECEDENCE.get(kind, "PRIORITY"),
            grade=grade_ or world.grading["status_grade"], contact_no=contact_no)


def activity(t: Unit) -> str:
    if t.engaged:
        return "firing"
    if t.path:
        return f"moving {compass(t.path[0][0] - t.x, t.path[0][1] - t.y)}"
    return "digging in" if t.posture == "dug_in" else "stationary"


def believed_xy(u: Unit) -> tuple[float, float]:
    return u.x + u.gnss_offset[0], u.y + u.gnss_offset[1]


def standing_rules(state: State, world: World, rng: Rng, detections: list[Detection]) -> None:
    sr = world.scenario.blue_script.standing_rules
    for d in detections:
        o, t = d.observer, d.target
        if o.role != "platoon":
            continue
        tracks = state.tracks.setdefault(o.id, {})
        act = activity(t)
        tr = tracks.get(t.id)
        if tr is None:
            n = state.contact_counters.get(o.id, 0) + 1
            state.contact_counters[o.id] = n
            pl = o.callsign.rsplit("-", 1)[-1] if "-" in o.callsign else "0"
            tr = Track(f"C-{pl}-{n:02d}", t.id, state.tick, state.tick, -10**9, act, d.rep_x, d.rep_y, d.q,
                       d.source_type, d.size)
            tracks[t.id] = tr
        else:
            tr.last_seen, tr.rep_x, tr.rep_y, tr.q, tr.source_type = state.tick, d.rep_x, d.rep_y, d.q, d.source_type
        if tr.last_report < 0 or tr.activity != act or state.tick - tr.last_report >= sr.contact_cooldown_s:
            tr.activity, tr.last_report, tr.size = act, state.tick, d.size
            _report(state, world, rng, o, "contact",
                    {"size": d.size, "unit_type": UNIT_TYPE_WORD[t.type], "grid": world.grid_ref(d.rep_x, d.rep_y),
                     "activity": act, "time": time_now(state, world)},
                    grade(world.grading, d.source_type, d.q), tr.contact_no)
    for oid in sorted(state.tracks):
        tracks = state.tracks[oid]
        for tid in sorted(tracks):
            if state.tick - tracks[tid].last_seen > sr.track_drop_s:
                del tracks[tid]
    for u in _scripted_blue(state):
        if u.arrived_tick == state.tick or state.tick - u.last_locstat >= sr.locstat_every_s:
            u.last_locstat = state.tick
            _report(state, world, rng, u, "locstat", {"grid": world.grid_ref(*believed_xy(u)),
                                                      "status": "engaged" if u.engaged else u.status,
                                                      "time": time_now(state, world)})
        if u.strength < sr.sitrep_when_strength_below and not u.sitrep_low_sent:
            u.sitrep_low_sent = True
            send_sitrep(state, world, rng, u)


def send_sitrep(state: State, world: World, rng: Rng, u: Unit) -> None:
    tracks = sorted(state.tracks.get(u.id, {}).values(), key=lambda t: t.contact_no)[:2]
    summary = enemy_summary([(t.size, UNIT_TYPE_WORD[state.units[t.target].type], t.activity) for t in tracks])
    posture = ("withdrawing" if (u.order or {}).get("kind") == "order_withdraw" and u.path else
               "moving" if u.path else "observing" if u.observing else "holding")
    _report(state, world, rng, u, "sitrep", {"grid": world.grid_ref(*believed_xy(u)),
                                             "strength_pct": str(int(round(u.strength))), "posture": posture,
                                             "enemy_summary": summary, "time": time_now(state, world)})


# ---- reactions to delivered messages ------------------------------------------------------------


def _reply(state: State, world: World, rng: Rng, unit: Unit, m: Message, kind: str, fields: dict[str, str]) -> None:
    enqueue(state, world, rng, sender=unit.callsign, to=m.sender, net=m.net, kind=kind,
            fields={"callsign": unit.callsign, **fields}, precedence=TEMPLATE_PRECEDENCE.get(kind, "PRIORITY"),
            grade=world.grading["status_grade"])


def react(state: State, world: World, rng: Rng, deliveries: list[Delivery], events: Events) -> None:
    """Scripted stations act only on what was delivered to them, parsed from the delivered text."""
    for dv in deliveries:
        m = dv.msg
        if dv.receiver != m.to or dv.receiver == state.player:
            continue
        u = state.unit_by_callsign(dv.receiver)
        if u is None or u.strength <= 0:
            continue
        f = parse(dv.text)
        kind = f.get("type") or "free"
        if not kind.startswith("order_"):
            continue

        reply = functools.partial(_reply, state, world, rng, u, m)

        grid = f.get("grid")
        if kind in GRID_ORDERS and grid is None:
            reply("say_again", {"ref": m.msg_id})
            events.append(("order_say_again", {"msg": m.msg_id, "unit": u.id}))
            continue
        if u.role == "bn_hq":
            if kind == "order_fire_mission" and grid:
                x, y = world.grid_to_xy(grid)
                state.fire_missions.append({"impact_tick": state.tick + world.scenario.outcomes.fire_mission.delay_s,
                                            "x": x, "y": y, "grid": grid, "ref": m.msg_id, "requester": m.sender,
                                            "net": m.net, "by": u.callsign})
                reply("ack", {"ref": m.msg_id})
            else:
                reply("fire_status", {"grid": grid or "000 000", "fire_state": "cannot comply",
                                      "time": time_now(state, world)})
            continue
        if u.role != "platoon":
            continue
        u.order = {"kind": kind, "grid": grid, "ref": m.msg_id, "tick": state.tick}
        speed = f.get("speed") or "tactical"
        if kind in ("order_move", "order_withdraw") and grid:
            go_to(world, u, world.grid_to_xy(grid), "fast" if kind == "order_withdraw" else speed)
            u.observing = None
        elif kind == "order_halt":
            stop(u)
        elif kind == "order_hold":
            stop(u, "in position", "dug_in")
        elif kind == "order_observe":
            stop(u, "in position")
            u.observing = grid
        elif kind == "order_request_sitrep":
            send_sitrep(state, world, rng, u)
            continue
        if world.scenario.blue_script.standing_rules.ack_orders:
            reply("ack", {"ref": m.msg_id})
        events.append(("order_acted", {"msg": m.msg_id, "unit": u.id, "kind": kind}))


def fire_status(state: State, world: World, rng: Rng, resolved: list[dict[str, Any]]) -> None:
    for fm in resolved:
        bn = state.unit_by_callsign(fm["by"])
        if bn is None:
            continue
        enqueue(state, world, rng, sender=bn.callsign, to=fm["requester"], net=fm["net"], kind="fire_status",
                fields={"callsign": bn.callsign, "grid": fm["grid"], "fire_state": "rounds complete",
                        "time": time_now(state, world)},
                precedence="PRIORITY", grade=world.grading["status_grade"])
