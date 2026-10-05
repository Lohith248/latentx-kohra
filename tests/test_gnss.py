from __future__ import annotations

import math

import pytest
from kohra.comms.gnss import step_offset
from kohra.sim.detect import detect_all
from kohra.sim.rng import Rng
from kohra.sim.state import initial_state
from kohra.sim.world import World


def test_offset_growth_clamp_recovery() -> None:
    off = (0.0, 0.0)
    for _ in range(10):
        off = step_offset(off, True, 90.0, 2.0, 100.0, 1.0, 1.0)
    assert off == pytest.approx((20.0, 0.0))
    for _ in range(100):
        off = step_offset(off, True, 0.0, 2.0, 50.0, 1.0, 1.0)
    assert math.hypot(*off) == pytest.approx(50.0)
    for _ in range(10):
        off = step_offset(off, False, 0.0, 0.0, 0.0, 1.0, 1.0)
    assert math.hypot(*off) == pytest.approx(40.0)
    for _ in range(100):
        off = step_offset(off, False, 0.0, 0.0, 0.0, 1.0, 1.0)
    assert off == (0.0, 0.0)


def test_contact_grid_shifts_with_observer_offset(flat_ridge_world: World) -> None:
    w = flat_ridge_world
    sc = w.scenario

    def detections(offset: tuple[float, float]) -> list[tuple[str, float, float]]:
        s = initial_state(sc, w)
        obs = s.units["B-3PL"]
        recce = s.units["R-RECCE"]
        obs.x, obs.y = recce.x - 800, recce.y
        obs.gnss_offset = [offset[0], offset[1]]
        rng = Rng(3)
        out = []
        for _ in range(200):
            out += [(d.target.id, d.rep_x - d.observer.x, d.rep_y - d.observer.y) for d in detect_all(s, w, rng)]
        return out

    base, shifted = detections((0, 0)), detections((300.0, -120.0))
    assert base and len(base) == len(shifted)
    for (i0, x0, y0), (i1, x1, y1) in zip(base, shifted, strict=True):
        assert i0 == i1
        assert x1 - x0 == pytest.approx(300.0)
        assert y1 - y0 == pytest.approx(-120.0)
