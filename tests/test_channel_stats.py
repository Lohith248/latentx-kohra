"""K-04: delivered share over 10,000 messages matches configured odds; Gilbert-Elliott statistics."""

from __future__ import annotations

import math

import numpy as np
import pytest
from kohra.comms.burst import ge_step
from kohra.comms.delivery import p_deliver
from kohra.comms.queue import _finish
from kohra.scenario.schema import LinkModel
from kohra.sim.rng import Rng
from kohra.sim.state import Message, NetState, State


class _W:  # the slice of World that _finish needs
    class scenario:  # noqa: N801
        class comms:  # noqa: N801
            link_model = LinkModel()


@pytest.mark.parametrize("p", [0.2, 0.5, 0.8, 0.95])
def test_delivered_share_matches_p(p: float) -> None:
    lm = LinkModel()
    sinr = lm.theta_db + math.log(p / (1 - p)) / lm.slope_per_db
    assert p_deliver(sinr, lm) == pytest.approx(p, abs=1e-9)
    state = State(tick=0, seed=1, units={}, jammers={}, nets={"COY": NetState("COY")})
    rng = Rng(1000 + int(p * 100))
    delivered = 0
    n = 10_000
    for i in range(n):
        m = Message(seq=i, msg_id=f"M-{i:04d}", net="COY", sender="TIGER", to="TIGER-1", kind="free", phrasing=-1,
                    fields={}, text="x", precedence="PRIORITY", grade=None, enqueue_tick=0, eligible_tick=0,
                    sinr_min={"TIGER-1": sinr})
        delivered += len(_finish(state, _W(), rng, m, []))  # type: ignore[arg-type]
    assert abs(delivered / n - p) / p < 0.05


def test_net_cut_delivers_nothing() -> None:
    state = State(tick=5, seed=1, units={}, jammers={}, nets={"COY": NetState("COY", cut_until=10)})
    m = Message(seq=1, msg_id="M-0001", net="COY", sender="A", to="B", kind="free", phrasing=-1, fields={}, text="x",
                precedence="PRIORITY", grade=None, enqueue_tick=0, eligible_tick=0, sinr_min={"B": 60.0})
    assert _finish(state, _W(), Rng(1), m, []) == []  # type: ignore[arg-type]


def test_gilbert_elliott_statistics() -> None:
    p, r, n = 0.05, 0.2, 100_000
    g = np.random.Generator(np.random.PCG64(7))
    bad = False
    states = []
    for _ in range(n):
        bad = ge_step(bad, p, r, g)
        states.append(bad)
    share = sum(states) / n
    assert abs(share - p / (p + r)) / (p / (p + r)) < 0.05
    spells, cur = [], 0
    for s in states:
        if s:
            cur += 1
        elif cur:
            spells.append(cur)
            cur = 0
    assert abs(np.mean(spells) - 1 / r) / (1 / r) < 0.10
