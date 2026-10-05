"""Cost grids, deterministic A* on the 90 m grid (D23) and per-tick movement along waypoints."""

from __future__ import annotations

import heapq
import math

import numpy as np
from numpy.typing import NDArray

from kohra.sim.terrain import LC_BUILT, LC_FOREST, LC_ROAD, LC_STREAM, LC_WATER, Terrain

XY = tuple[float, float]
SQRT2 = math.sqrt(2.0)
NEIGHBOURS = ((-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
              (-1, -1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (1, 1, SQRT2))
FORD_RADIUS_M = 150.0


def build_cost_grid(terrain: Terrain, mobility: str, slope_limit_deg: float, road_factor: float,
                    fords_xy: list[XY], inside: NDArray[np.bool_] | None = None) -> NDArray[np.float64]:
    """Per-cell cost multiplier (1.0 = open flat ground); inf = impassable."""
    slope = terrain.slope90.astype(np.float64)
    lc = terrain.lc90
    veh = mobility == "vehicle"
    cost = 1.0 + slope / (8.0 if veh else 15.0)
    cost = np.where(lc == LC_FOREST, cost * (2.5 if veh else 1.5), cost)
    cost = np.where(lc == LC_BUILT, cost * 1.2, cost)
    cost = np.where(lc == LC_STREAM, cost * (3.0 if veh else 2.0), cost)
    road = lc == LC_ROAD
    cost = np.where(road, road_factor * (1.0 + slope / 30.0), cost)
    cost = np.where((slope > slope_limit_deg) & ~road, np.inf, cost)
    cost = np.where(lc == LC_WATER, np.inf, cost)
    my, mx = terrain.shape90
    rr, cc = np.mgrid[0:my, 0:mx]
    cx = terrain.x0 + (cc + 0.5) * terrain.res90
    cy = terrain.y0 - (rr + 0.5) * terrain.res90
    for fx, fy in fords_xy:
        cost = np.where(np.hypot(cx - fx, cy - fy) <= FORD_RADIUS_M, 3.0, cost)
    if inside is not None:
        cost = np.where(inside, cost, np.inf)
    return np.asarray(cost, np.float64)


def _nearest_passable(cost: NDArray[np.float64], r: int, c: int, max_ring: int = 30) -> tuple[int, int] | None:
    my, mx = cost.shape
    for k in range(max_ring + 1):
        ring = [(r + dr, c + dc) for dr in range(-k, k + 1) for dc in range(-k, k + 1) if max(abs(dr), abs(dc)) == k]
        ok = [(a, b) for a, b in ring if 0 <= a < my and 0 <= b < mx and math.isfinite(cost[a, b])]
        if ok:
            return min(ok, key=lambda p: ((p[0] - r) ** 2 + (p[1] - c) ** 2, p[0] * mx + p[1]))
    return None


def astar(cost: NDArray[np.float64], start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]] | None:
    """8-connected A* with no corner cutting. Ties break on (f, g, cell index): fully deterministic."""
    my, mx = cost.shape
    g_goal = _nearest_passable(cost, *goal)
    if g_goal is None:
        return None
    goal = g_goal
    hmin = float(np.nanmin(np.where(np.isfinite(cost), cost, np.nan)))
    gr, gc = goal
    sidx = start[0] * mx + start[1]
    gidx = gr * mx + gc
    best: dict[int, float] = {sidx: 0.0}
    parent: dict[int, int] = {}
    heap: list[tuple[float, float, int]] = [(math.hypot(start[0] - gr, start[1] - gc) * hmin, 0.0, sidx)]
    closed: set[int] = set()
    while heap:
        _f, g, idx = heapq.heappop(heap)
        if idx in closed:
            continue
        if idx == gidx:
            path = [idx]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            return [(i // mx, i % mx) for i in reversed(path)]
        closed.add(idx)
        r, c = divmod(idx, mx)
        here = cost[r, c] if math.isfinite(cost[r, c]) else 3.0  # leaving an impassable start cell is allowed
        for dr, dc, step in NEIGHBOURS:
            a, b = r + dr, c + dc
            if not (0 <= a < my and 0 <= b < mx):
                continue
            ca = cost[a, b]
            if not math.isfinite(ca):
                continue
            if dr and dc and not (math.isfinite(cost[r + dr, c]) and math.isfinite(cost[r, c + dc])):
                continue
            nidx = a * mx + b
            ng = g + step * 0.5 * (here + ca)
            if ng < best.get(nidx, math.inf):
                best[nidx] = ng
                parent[nidx] = idx
                heapq.heappush(heap, (ng + math.hypot(a - gr, b - gc) * hmin, ng, nidx))
    return None


def plan_path(terrain: Terrain, cost: NDArray[np.float64], start: XY, goal: XY) -> list[XY]:
    """Waypoints from start to goal (exclusive of start). Empty if no path exists."""
    cells = astar(cost, terrain.cell90(*start), terrain.cell90(*goal))
    if cells is None:
        return []
    pts = [terrain.center90(r, c) for r, c in cells[1:]]
    pts = _simplify(pts)
    if cells[-1] == terrain.cell90(*goal):
        if pts:
            pts[-1] = goal
        else:
            pts = [goal]
    return pts


def _simplify(pts: list[XY]) -> list[XY]:
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = out[-1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-6:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def _nearest_segment(route: list[XY], p: XY) -> int:
    def dist(k: int) -> float:
        (ax, ay), (bx, by) = route[k], route[k + 1]
        L2 = (bx - ax) ** 2 + (by - ay) ** 2
        t = 0.0 if L2 == 0 else min(max(((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L2, 0.0), 1.0)
        return math.hypot(ax + t * (bx - ax) - p[0], ay + t * (by - ay) - p[1])
    return min(range(len(route) - 1), key=lambda k: (dist(k), k))


def route_waypoints(route: list[XY], start: XY, goal: XY) -> list[XY]:
    """Join the route on the segment nearest `start`, follow it to the segment nearest `goal`, then `goal`."""
    if len(route) < 2:
        return [goal]
    ks, kg = _nearest_segment(route, start), _nearest_segment(route, goal)
    if ks < kg:
        seq = route[ks + 1 : kg + 1]
    elif ks > kg:
        seq = route[kg + 1 : ks + 1][::-1]
    else:
        seq = []
    return [*seq, goal]


def speed_mps(speeds: dict[str, float], mobility: str, speed: str, on_road: bool) -> float:
    if mobility == "foot":
        return speeds["foot_fast"] if speed == "fast" else speeds["foot"]
    # Scenario speeds are the tactical pace; "fast" is 25 % quicker (the schema only defines foot_fast).
    base = speeds["vehicle_road"] if on_road else speeds["vehicle_offroad"]
    return base * 1.25 if speed == "fast" else base


def advance(x: float, y: float, path: list[XY], dist: float) -> tuple[float, float, list[XY]]:
    """Move up to `dist` metres along the waypoint list; returns new position and remaining waypoints."""
    while path and dist > 0:
        tx, ty = path[0]
        d = math.hypot(tx - x, ty - y)
        if d <= dist:
            x, y, dist = tx, ty, dist - d
            path = path[1:]
        else:
            x += (tx - x) * dist / d
            y += (ty - y) * dist / d
            dist = 0
    return x, y, path


def on_road(terrain: Terrain, x: float, y: float) -> bool:
    r, c = terrain.cell90(x, y)
    return bool(terrain.lc90[r, c] == LC_ROAD)
