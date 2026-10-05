from __future__ import annotations

import math

import numpy as np
import pytest
from kohra.sim.move import advance, astar, route_waypoints
from kohra.sim.world import World

from tests.fixtures.dems import cell_centre, flat, ridge


def test_grid_ref_both_ways(flat_ridge_world: World) -> None:
    w = flat_ridge_world
    ox, oy = w.origin
    assert w.grid_ref(ox + 11_550, oy + 7_290) == "115 072"
    x, y = w.grid_to_xy("115 072")
    assert (x, y) == (ox + 11_550, oy + 7_250)
    for gx in range(0, 210, 17):
        for gy in range(0, 160, 13):
            g = f"{gx:03d} {gy:03d}"
            assert w.grid_ref(*w.grid_to_xy(g)) == g
    with pytest.raises(ValueError):
        w.grid_to_xy("11 072")


def test_grid_affine_matches_projection(flat_ridge_world: World) -> None:
    w = flat_ridge_world
    a = w.grid_affine()["lonlat_to_grid_m"]
    for lon, lat in [(76.12, 11.21), (76.29, 11.34), (76.2, 11.27)]:
        gx = a[0] * lon + a[1] * lat + a[2]
        gy = a[3] * lon + a[4] * lat + a[5]
        x, y = w.to_xy((lon, lat))
        assert math.hypot(gx - (x - w.origin[0]), gy - (y - w.origin[1])) < 10.0


def test_los_on_fixtures() -> None:
    a, b = cell_centre(1500, 1500), cell_centre(7500, 1500)
    assert flat().los(*a, 2, *b, 2)
    assert not ridge(150).los(*a, 2, *b, 2)
    crest = cell_centre(4500, 1500)
    assert ridge(150).los(*a, 2, *crest, 2)


def test_astar_deterministic_tiebreak() -> None:
    cost = np.ones((5, 5))
    cost[2, 2] = np.inf  # obstacle: going above (row 1) and below (row 3) cost the same
    p1 = astar(cost, (2, 0), (2, 4))
    p2 = astar(cost, (2, 0), (2, 4))
    assert p1 == p2 and p1 is not None
    assert (2, 2) not in p1
    assert p1[0] == (2, 0) and p1[-1] == (2, 4)
    assert any(r == 1 for r, _ in p1)  # tie broken toward the lower cell index


def test_astar_no_corner_cutting_and_water() -> None:
    cost = np.ones((3, 3))
    cost[0, 1] = cost[1, 0] = np.inf
    assert astar(cost, (0, 0), (2, 2)) is None
    cost = np.ones((4, 6))
    cost[:, 3] = np.inf  # a river
    assert astar(cost, (0, 0), (0, 5)) is None
    cost[2, 3] = 3.0  # a ford
    path = astar(cost, (0, 0), (0, 5))
    assert path is not None and (2, 3) in path


def test_advance_and_route() -> None:
    x, y, rest = advance(0, 0, [(10, 0), (10, 10)], 15)
    assert (x, y) == (10, 5) and rest == [(10, 10)]
    route = [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0), (300.0, 0.0)]
    assert route_waypoints(route, (150, 5), (300, 0)) == [(200.0, 0.0), (300, 0)]
    assert route_waypoints(route, (250, 5), (0, 0)) == [(200.0, 0.0), (100.0, 0.0), (0, 0)]
