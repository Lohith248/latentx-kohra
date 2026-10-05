"""GNSS spoofing as a slow walk-off (spec section 6.6)."""

from __future__ import annotations

import math


def step_offset(offset: tuple[float, float], in_zone: bool, bearing_deg: float, rate_mps: float,
                max_offset_m: float, recover_mps: float, dt: float) -> tuple[float, float]:
    ox, oy = offset
    if in_zone:
        b = math.radians(bearing_deg)
        ox += rate_mps * dt * math.sin(b)
        oy += rate_mps * dt * math.cos(b)
        mag = math.hypot(ox, oy)
        if mag > max_offset_m:
            ox, oy = ox * max_offset_m / mag, oy * max_offset_m / mag
        return ox, oy
    mag = math.hypot(ox, oy)
    if mag <= recover_mps * dt:
        return 0.0, 0.0
    k = (mag - recover_mps * dt) / mag
    return ox * k, oy * k
