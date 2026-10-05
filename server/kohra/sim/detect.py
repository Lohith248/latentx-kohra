"""Sensor detection (spec 8.2): per-tick probability, LOS gate, quality, position error, size misjudgement."""

from __future__ import annotations

import math
from dataclasses import dataclass

from kohra.reports.grade import detection_quality
from kohra.reports.parse import SIZES
from kohra.scenario.schema import Sensor
from kohra.sim.rng import Rng
from kohra.sim.state import State, Unit
from kohra.sim.world import World

TYPE_FACTOR = {"apc": 1.5, "tank": 1.5, "hq": 1.5, "infantry": 1.0, "recce": 0.7, "ew": 0.8}
POSTURE_DETECT = {"moving": 1.5, "stationary": 1.0, "dug_in": 0.5}
TRUE_SIZE = {"section": "section", "platoon": "platoon", "company": "company", "battalion": "company"}
UNIT_TYPE_WORD = {"apc": "APC", "tank": "tank", "infantry": "infantry", "recce": "recce", "ew": "EW detachment",
                  "hq": "vehicle"}


def target_height(u: Unit) -> float:
    return 2.0 if u.mobility == "foot" else 2.5


def p_detect(sensor: Sensor, r: float, tick_s: float, target: Unit) -> float:
    if r >= sensor.max_range_m:
        return 0.0
    p = (sensor.base_p_per_s * tick_s * (1 - (r / sensor.max_range_m) ** 2)
         * TYPE_FACTOR.get(target.type, 1.0) * POSTURE_DETECT[target.posture])
    return min(p, 0.95)


@dataclass
class Detection:
    observer: Unit
    target: Unit
    q: float
    source_type: str
    rep_x: float
    rep_y: float
    size: str


def detect_all(state: State, world: World, rng: Rng) -> list[Detection]:
    """Blue observers (sorted id) x red targets (sorted id). One `detect` draw per pair in range with LOS."""
    sc = world.scenario
    out = []
    observers = [state.units[k] for k in sorted(state.units)
                 if state.units[k].side == "blue" and state.units[k].sensors and state.units[k].strength > 0]
    targets = [state.units[k] for k in sorted(state.units) if state.units[k].side == "red" and state.units[k].strength > 0]
    for o in observers:
        for t in targets:
            r = math.hypot(t.x - o.x, t.y - o.y)
            sensors = [sc.sensors[s] for s in o.sensors]
            best = max(sensors, key=lambda s: p_detect(s, r, sc.tick_seconds, t))
            p = p_detect(best, r, sc.tick_seconds, t)
            if p <= 0 or not world.terrain.los(o.x, o.y, best.eye_height_m, t.x, t.y, target_height(t)):
                continue
            if float(rng.detect.random()) >= p:
                continue
            sigma = best.sigma_base_m + best.sigma_per_km_m * r / 1000.0
            ex, ey = (float(v) for v in rng.detect.normal(0.0, sigma, size=2))
            # GNSS walk-off moves the origin of what the observer reports (6.6)
            rep_x = o.x + o.gnss_offset[0] + (t.x - o.x) + ex
            rep_y = o.y + o.gnss_offset[1] + (t.y - o.y) + ey
            size = TRUE_SIZE.get(_echelon(world, t), "section")
            if float(rng.detect.random()) < 0.2:
                i = SIZES.index(size) + (1 if float(rng.detect.random()) < 0.5 else -1)
                size = SIZES[min(max(i, 0), len(SIZES) - 1)]
            out.append(Detection(o, t, detection_quality(r, best.max_range_m, t.posture), best.source_type,
                                 rep_x, rep_y, size))
    return out


def _echelon(world: World, u: Unit) -> str:
    return next(c.echelon for c in world.scenario.all_units() if c.id == u.id)
