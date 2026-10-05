"""Check a scenario's `intent:` notes against the built terrain (D30).

    uv run python scripts/check_scenario.py [scenarios/ridge.yaml]

Checks: OSPREY is on major water and is the crossing between two land regions; KESTREL blocks LOS from
OSPREY to JUNIPER; HERON sees OSPREY; every unit starts on passable ground; every red-plan move has a path.
Exit code 1 if any check fails.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from kohra.scenario.load import load_scenario  # noqa: E402
from kohra.sim.move import plan_path, route_waypoints  # noqa: E402
from kohra.sim.terrain import LC_WATER  # noqa: E402
from kohra.sim.world import build_world  # noqa: E402


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "scenarios" / "ridge.yaml")
    scen, _ = load_scenario(path)
    world = build_world(scen)
    t = world.terrain
    p = world.places_xy
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= cond
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")

    fx, fy = p["OSPREY"]
    r, c = t.cell90(fx, fy)
    check("OSPREY on major water", bool(t.lc90[max(r - 2, 0):r + 3, max(c - 2, 0):c + 3].__eq__(LC_WATER).any()))
    veh = world.cost["vehicle"]
    no_ford = world.cost_no_ford["vehicle"]
    north, south = p["JUNIPER"], p["WILLOW"]  # red bank, blue bank
    check("OSPREY: crossing exists via the ford", bool(plan_path(t, veh, north, south)))
    check("OSPREY: no crossing without the ford", not plan_path(t, no_ford, north, south))
    kx, ky = p["KESTREL"]
    jx, jy = p["JUNIPER"]
    check("KESTREL blocks LOS OSPREY->JUNIPER", not t.los(fx, fy, 2, jx, jy, 2))
    check("KESTREL above OSPREY", t.elev_pt(kx, ky) > t.elev_pt(fx, fy) + 30,
          f"({t.elev_pt(kx, ky):.0f} m vs {t.elev_pt(fx, fy):.0f} m)")
    hx, hy = p["HERON"]
    check("HERON sees OSPREY", t.los(hx, hy, 2, fx, fy, 2), f"({math.hypot(hx - fx, hy - fy):.0f} m)")
    for u in scen.all_units():
        x, y = world.to_xy(u.lonlat)
        rr, cc = t.cell90(x, y)
        check(f"{u.id} on passable ground", math.isfinite(world.cost[u.mobility][rr, cc]))
    units = {u.id: u for u in scen.all_units()}
    for rule in scen.red_plan:
        for a in rule.do:
            if a.action not in ("move", "withdraw"):
                continue
            u = units[a.unit]
            start = world.to_xy(u.lonlat)
            goal = p[a.to_place] if a.to_place else world.to_xy(a.to) if a.to else None
            if goal is None:
                continue
            if a.via_route:
                wps = route_waypoints(world.routes_xy[a.via_route], start, goal)
                check(f"{a.unit} {a.action} via {a.via_route}", len(wps) > 0, f"({len(wps)} waypoints)")
            else:
                wps = plan_path(t, world.cost[u.mobility], start, goal)
                check(f"{a.unit} {a.action} to {a.to_place or a.to}", len(wps) > 0)
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
