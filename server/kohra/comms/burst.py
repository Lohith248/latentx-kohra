"""Gilbert-Elliott two-state chain (spec section 6.4). Overlay only: intermittent jammers and fading."""

from __future__ import annotations

import numpy as np


def ge_step(bad: bool, p: float, r: float, rng: np.random.Generator) -> bool:
    """One tick: G->B with probability p, B->G with probability r. Exactly one draw per call."""
    u = float(rng.random())
    return (u >= r) if bad else (u < p)
