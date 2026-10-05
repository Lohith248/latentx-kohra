"""K-04: terrain and jammer geometry change the link as expected (synthetic fixtures)."""

from __future__ import annotations

import math

import pytest
from kohra.comms.delivery import p_deliver
from kohra.comms.sinr import Emitter, JammerSignal, knife_edge_db, path_loss_db, sinr_db
from kohra.scenario.schema import LinkModel

from tests.fixtures.dems import cell_centre, flat, ridge

LM = LinkModel()
F = 50.0
BW = 25.0


def em(x_m: float, y_m: float = 1500, h: float = 2.0, p: float = 37.0) -> Emitter:
    x, y = cell_centre(x_m, y_m)
    return Emitter(x, y, h, p)


def test_ridge_adds_loss_and_lowers_delivery() -> None:
    tx, rx = em(1500), em(7500)  # 6 km path, ridge (150 m) midway at 4500
    pl_flat, d0 = path_loss_db(flat(), LM, (tx.x, tx.y, 2), (rx.x, rx.y, 2), F)
    pl_ridge, dl = path_loss_db(ridge(150), LM, (tx.x, tx.y, 2), (rx.x, rx.y, 2), F)
    assert d0 == 0
    assert pl_ridge - pl_flat >= 15
    assert pl_ridge - pl_flat == pytest.approx(20, abs=3)
    s_flat = sinr_db(flat(), LM, tx, rx, F, BW, [])
    s_ridge = sinr_db(ridge(150), LM, tx, rx, F, BW, [])
    assert p_deliver(s_ridge, LM) < p_deliver(s_flat, LM)


def test_receiver_on_crest_no_diffraction() -> None:
    tx, rx = em(1500), em(4500)
    _, ldiff = path_loss_db(ridge(150), LM, (tx.x, tx.y, 2), (rx.x, rx.y, 2), F)
    assert ldiff == 0


def test_doubling_jammer_distance_on_flat_gains_12db() -> None:
    t = flat()
    tx, rx = em(3000), em(4500)
    j1 = JammerSignal(Emitter(*cell_centre(4500 + 1500, 1500), 6, 47), 45.25, 25)
    j2 = JammerSignal(Emitter(*cell_centre(4500 + 3000, 1500), 6, 47), 45.25, 25)
    s1 = sinr_db(t, LM, tx, rx, 45.25, BW, [j1])
    s2 = sinr_db(t, LM, tx, rx, 45.25, BW, [j2])
    assert s2 - s1 == pytest.approx(12.04, abs=0.1)


def test_jammer_behind_ridge_gains_its_diffraction_loss() -> None:
    rx, tx = em(3000), em(2000)
    jam_front = JammerSignal(Emitter(*cell_centre(0, 1500), 6, 47), 45.25, 25)  # 3 km W, open flat ground
    jam_behind = JammerSignal(Emitter(*cell_centre(6000, 1500), 6, 47), 45.25, 25)  # 3 km E, ridge between
    t = ridge(150)
    s_front = sinr_db(t, LM, tx, rx, 45.25, BW, [jam_front])
    s_behind = sinr_db(t, LM, tx, rx, 45.25, BW, [jam_behind])
    _, ldiff = path_loss_db(t, LM, (jam_behind.emitter.x, jam_behind.emitter.y, 6), (rx.x, rx.y, 2), 45.25)
    assert ldiff > 10
    assert s_behind - s_front == pytest.approx(ldiff, abs=0.5)


def test_p_deliver_monotonic_as_jammer_approaches() -> None:
    t = flat()
    tx, rx = em(1000), em(3000)
    ps = []
    for d in range(6000, 90, -300):
        j = JammerSignal(Emitter(*cell_centre(3000 + d, 1500), 6, 30), 45.25, 25)
        ps.append(p_deliver(sinr_db(t, LM, tx, rx, 45.25, BW, [j]), LM))
    assert all(a >= b for a, b in zip(ps, ps[1:], strict=False))
    assert ps[0] > 0.9 > 0.1 > ps[-1]


def test_frequency_overlap() -> None:
    t = flat()
    tx, rx = em(3000), em(4500)
    s_none = sinr_db(t, LM, tx, rx, 45.25, BW, [])
    off = JammerSignal(Emitter(*cell_centre(6000, 1500), 6, 47), 46.0, 25)
    assert sinr_db(t, LM, tx, rx, 45.25, BW, [off]) == s_none
    spot = JammerSignal(Emitter(*cell_centre(6000, 1500), 6, 47), 45.25, 25)
    barrage = JammerSignal(Emitter(*cell_centre(6000, 1500), 6, 47), 45.25, 2000)
    # J >> N, so the SINR difference is the per-channel jammer power difference
    diff = sinr_db(t, LM, tx, rx, 45.25, BW, [barrage]) - sinr_db(t, LM, tx, rx, 45.25, BW, [spot])
    assert diff == pytest.approx(19.0, abs=0.1)
    assert 10 * math.log10(2000 / 25) == pytest.approx(19.03, abs=0.01)


def test_knife_edge_reference_values() -> None:
    assert knife_edge_db(-1.0) == 0
    assert knife_edge_db(0.0) == pytest.approx(6.0, abs=0.1)
    assert knife_edge_db(2.4) == pytest.approx(20.5, abs=0.5)
