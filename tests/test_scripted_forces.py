"""K-03: scripted red follows its plan; scripted blue ACKs, reports and keeps its last order without comms."""

from __future__ import annotations

import math

from kohra.rooms import Runner
from kohra.scenario.schema import Inject, Scenario
from kohra.sim.world import World

FAR_SW = (76.101, 11.201)


def make(ridge: tuple[Scenario, str], world: World, blue_at: tuple[float, float] | None = FAR_SW) -> Runner:
    r = Runner(ridge[0], ridge[1], world=world, end_tick=3000)
    if blue_at:
        for u in r.state.units.values():
            if u.side == "blue":
                u.x, u.y = world.to_xy(blue_at)
    return r


def run_until(r: Runner, cond, limit: int = 2000) -> None:  # type: ignore[no-untyped-def]
    while not cond() and r.state.tick < limit:
        r.advance()


def dist(r: Runner, uid: str, place: str) -> float:
    u = r.state.units[uid]
    px, py = r.world.places_xy[place]
    return math.hypot(u.x - px, u.y - py)


def test_red_no_contact_reaches_ford(ridge, flat_ridge_world) -> None:  # type: ignore[no-untyped-def]
    r = make(ridge, flat_ridge_world)
    run_until(r, lambda: r.state.units["R-RECCE"].arrived_tick >= 0)
    assert 0 in r.state.fired_red and 1 not in r.state.fired_red
    assert dist(r, "R-RECCE", "OSPREY") < 1.0


def test_red_contact_triggers_halt(ridge, flat_ridge_world) -> None:  # type: ignore[no-untyped-def]
    r = make(ridge, flat_ridge_world)
    ox, oy = r.world.places_xy["OSPREY"]
    r.state.units["B-1PL"].x, r.state.units["B-1PL"].y = ox, oy - 1200
    run_until(r, lambda: 1 in r.state.fired_red, 1500)
    recce = r.state.units["R-RECCE"]
    assert 1 in r.state.fired_red
    assert recce.path == [] and recce.posture == "stationary"
    assert dist(r, "R-RECCE", "OSPREY") > 200  # halted short of the ford
    tick = r.state.tick
    for _ in range(30):
        r.advance()
    assert dist(r, "R-RECCE", "OSPREY") > 200 and r.state.tick == tick + 30


def test_red_strength_trigger_withdraws(ridge, flat_ridge_world) -> None:  # type: ignore[no-untyped-def]
    r = make(ridge, flat_ridge_world)
    for _ in range(5):
        r.advance()
    r.state.units["R-RECCE"].strength = 40.0
    r.advance()
    recce = r.state.units["R-RECCE"]
    assert 2 in r.state.fired_red
    assert recce.speed == "fast" and recce.path
    jx, jy = r.world.places_xy["JUNIPER"]
    assert math.hypot(recce.path[-1][0] - jx, recce.path[-1][1] - jy) < 1.0


def _inbox(r: Runner, kind: str, sender: str | None = None) -> list[dict]:  # type: ignore[type-arg]
    return [e for e in r.state.perception.inbox if e["fields"].get("type") == kind and (sender is None or e["from"] == sender)]


def test_blue_acks_and_locstats(ridge, flat_ridge_world) -> None:  # type: ignore[no-untyped-def]
    r = make(ridge, flat_ridge_world, blue_at=None)
    grid = r.world.grid_ref(*r.world.places_xy["TAMARIND"])
    res = r.submit_player({"type": "order", "to": "TIGER-1", "kind": "MOVE", "grid": grid, "speed": "tactical",
                           "confidence": 60, "relied_on": []})
    assert res.ok
    run_until(r, lambda: bool(_inbox(r, "ack", "TIGER-1")), 120)
    sent = r.state.perception.sent[-1]
    acks = _inbox(r, "ack", "TIGER-1")
    assert acks and acks[0]["fields"]["ref"] == sent["msg_id"]
    assert r.state.units["B-1PL"].order and r.state.units["B-1PL"].order["grid"] == grid
    run_until(r, lambda: r.state.tick >= 260, 300)
    for cs in ("TIGER-1", "TIGER-2", "TIGER-3"):
        assert _inbox(r, "locstat", cs), cs


def test_blue_keeps_last_order_when_comms_lost(ridge, flat_ridge_world) -> None:  # type: ignore[no-untyped-def]
    r = make(ridge, flat_ridge_world, blue_at=None)
    grid = r.world.grid_ref(*r.world.places_xy["HERON"])
    r.submit_player({"type": "order", "to": "TIGER-2", "kind": "MOVE", "grid": grid, "speed": "fast",
                     "confidence": 50, "relied_on": []})
    run_until(r, lambda: bool(_inbox(r, "ack", "TIGER-2")), 120)
    r.schedule_inject(Inject(kind="net_cut", args={"net": "COY", "duration_s": 5000}))
    heard = len(r.state.perception.inbox)
    u = r.state.units["B-2PL"]
    assert u.path
    run_until(r, lambda: u.arrived_tick >= 0, 3000)
    assert u.path == [] and u.status == "in position"
    hx, hy = r.world.grid_to_xy(grid)
    assert math.hypot(u.x - hx, u.y - hy) < 1.0
    for _ in range(200):
        r.advance()
    assert u.path == [] and math.hypot(u.x - hx, u.y - hy) < 1.0  # holds after finishing
    assert not [e for e in r.state.perception.inbox[heard:] if e["net"] == "COY"]


def test_say_again_when_grid_garbled(ridge, flat_ridge_world) -> None:  # type: ignore[no-untyped-def]
    from kohra.comms.queue import Delivery
    from kohra.sim.scripts import react

    r = make(ridge, flat_ridge_world, blue_at=None)
    r.submit_player({"type": "order", "to": "TIGER-1", "kind": "MOVE", "grid": "050 040", "speed": "tactical",
                     "confidence": 50, "relied_on": []})
    r.advance()
    m = next(iter(r.state.messages.values()))
    garbled = m.text.replace("050 040", "[garbled]")
    ev: list = []  # type: ignore[type-arg]
    react(r.state, r.world, r.rng, [Delivery(m, "TIGER-1", garbled, True)], ev)
    assert ev[0][0] == "order_say_again"
    assert r.state.units["B-1PL"].order is None and not r.state.units["B-1PL"].path
    queued = [x for x in r.state.messages.values() if x.kind == "say_again"]
    assert queued and queued[0].fields["ref"] == m.msg_id
