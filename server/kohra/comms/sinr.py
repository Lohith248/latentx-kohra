"""Terrain-aware VHF link budget at the receiver (spec section 6.1-6.2). dB, dBm, metres, MHz."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from kohra.scenario.schema import LinkModel
from kohra.sim.terrain import F64, Terrain

EARTH_R_M = 6371000.0
CACHE_GRID_M = 30.0


@dataclass(frozen=True)
class Emitter:
    x: float
    y: float
    antenna_m: float
    power_dbm: float
    gain_dbi: float = 0.0


def fspl_db(d_m: float, f_mhz: float) -> float:
    return 20 * math.log10(d_m / 1000.0) + 20 * math.log10(f_mhz) + 32.44


def plane_earth_db(d_m: float, h_t: float, h_r: float) -> float:
    return 40 * math.log10(d_m) - 20 * math.log10(h_t) - 20 * math.log10(h_r)


def knife_edge_db(v: float) -> float:
    if v <= -0.78:
        return 0.0
    return 6.9 + 20 * math.log10(math.sqrt((v - 0.1) ** 2 + 1) + v - 0.1)


def _max_v(dist: F64, z: F64, za: float, zb: float, lam: float, k: float) -> tuple[float, int]:
    """Largest Fresnel-Kirchhoff v over interior samples (with earth bulge) and its index."""
    if len(z) <= 2:
        return -math.inf, -1
    d = float(dist[-1])
    x = dist[1:-1]
    z_eff = z[1:-1] + x * (d - x) / (2 * k * EARTH_R_M)
    h = z_eff - (za + (zb - za) * x / d)
    v = h * np.sqrt(2 * d / (lam * x * (d - x)))
    i = int(np.argmax(v))
    return float(v[i]), i + 1


def diffraction_db(dist: F64, z: F64, h_t: float, h_r: float, f_mhz: float, k: float,
                   method: str) -> float:
    lam = 299.792458 / f_mhz
    za, zb = float(z[0]) + h_t, float(z[-1]) + h_r
    v, i = _max_v(dist, z, za, zb, lam, k)
    if v <= 0:
        return 0.0
    loss = knife_edge_db(v)
    if method == "deygout3":  # principal edge plus the strongest edge on each side
        zi = float(z[i]) + float(dist[i]) * (float(dist[-1]) - float(dist[i])) / (2 * k * EARTH_R_M)
        for sl in (slice(0, i + 1), slice(i, len(z))):
            dd, zz = dist[sl] - dist[sl][0], z[sl].copy()
            a = za if sl.start == 0 else zi
            b = zi if sl.start == 0 else zb
            vs, _ = _max_v(dd, zz, a, b, lam, k)
            if vs > 0:
                loss += knife_edge_db(vs)
    return loss


def _snap(v: float) -> float:
    return (math.floor(v / CACHE_GRID_M) + 0.5) * CACHE_GRID_M


def path_loss_db(terrain: Terrain, lm: LinkModel, tx: tuple[float, float, float], rx: tuple[float, float, float],
                 f_mhz: float, cache: dict[tuple[float, ...], tuple[float, float]] | None = None) -> tuple[float, float]:
    """(PL, L_diff). Ends are snapped to 30 m cell centres first, so caching never changes results."""
    ax, ay, bx, by = _snap(tx[0]), _snap(tx[1]), _snap(rx[0]), _snap(rx[1])
    key = (ax, ay, bx, by, tx[2], rx[2], f_mhz, lm.k_factor, lm.profile_step_m, lm.extra_loss_db)
    if cache is not None and key in cache:
        return cache[key]
    d = max(math.hypot(bx - ax, by - ay), 10.0)
    dist, z = terrain.profile(ax, ay, bx, by, lm.profile_step_m)
    ldiff = diffraction_db(dist, z, tx[2], rx[2], f_mhz, lm.k_factor, lm.diffraction) if d > 10.0 else 0.0
    pl = max(fspl_db(d, f_mhz), plane_earth_db(d, tx[2], rx[2])) + ldiff + lm.extra_loss_db
    if cache is not None:
        if len(cache) > 200_000:
            cache.clear()
        cache[key] = (pl, ldiff)
    return pl, ldiff


def noise_dbm(bandwidth_khz: float, nf_db: float) -> float:
    return -174 + 10 * math.log10(bandwidth_khz * 1000.0) + nf_db


def overlap_fraction(f_j: float, bw_j_khz: float, f_net: float, bw_net_khz: float) -> float:
    """Share of the jammer's power that lands inside the net channel."""
    bj, bn = bw_j_khz / 1000.0, bw_net_khz / 1000.0
    lo = max(f_j - bj / 2, f_net - bn / 2)
    hi = min(f_j + bj / 2, f_net + bn / 2)
    return max(hi - lo, 0.0) / bj


@dataclass(frozen=True)
class JammerSignal:
    emitter: Emitter
    freq_mhz: float
    bandwidth_khz: float


def jammer_dbm_at_rx(terrain: Terrain, lm: LinkModel, j: JammerSignal, rx: Emitter, f_net: float, bw_net: float,
                     cache: dict[tuple[float, ...], tuple[float, float]] | None = None) -> float | None:
    ov = overlap_fraction(j.freq_mhz, j.bandwidth_khz, f_net, bw_net)
    if ov <= 0:
        return None
    pl, _ = path_loss_db(terrain, lm, (j.emitter.x, j.emitter.y, j.emitter.antenna_m), (rx.x, rx.y, rx.antenna_m),
                         j.freq_mhz, cache)
    return j.emitter.power_dbm + j.emitter.gain_dbi + rx.gain_dbi - pl + 10 * math.log10(ov)


def sinr_db(terrain: Terrain, lm: LinkModel, tx: Emitter, rx: Emitter, f_net: float, bw_net: float,
            jammers: Iterable[JammerSignal], cache: dict[tuple[float, ...], tuple[float, float]] | None = None) -> float:
    pl, _ = path_loss_db(terrain, lm, (tx.x, tx.y, tx.antenna_m), (rx.x, rx.y, rx.antenna_m), f_net, cache)
    p_rx = tx.power_dbm + tx.gain_dbi + rx.gain_dbi - pl
    lin = 10 ** (noise_dbm(bw_net, lm.noise_figure_db) / 10)
    for j in jammers:
        jd = jammer_dbm_at_rx(terrain, lm, j, rx, f_net, bw_net, cache)
        if jd is not None:
            lin += 10 ** (jd / 10)
    return p_rx - 10 * math.log10(lin)


def jammer_noise_radius_m(lm: LinkModel, j: JammerSignal, rx_antenna_m: float, f_net: float, bw_net: float,
                          rx_gain_dbi: float = 0.0) -> float:
    """Flat-earth distance at which the jammer's in-channel power equals receiver noise (for /ds rings)."""
    ov = overlap_fraction(j.freq_mhz, j.bandwidth_khz, f_net, bw_net)
    if ov <= 0:
        return 0.0
    budget = j.emitter.power_dbm + j.emitter.gain_dbi + rx_gain_dbi + 10 * math.log10(ov) \
        - noise_dbm(bw_net, lm.noise_figure_db) - lm.extra_loss_db
    lo, hi = 10.0, 500_000.0
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        pl = max(fspl_db(mid, j.freq_mhz), plane_earth_db(mid, j.emitter.antenna_m, rx_antenna_m))
        lo, hi = (mid, hi) if pl < budget else (lo, mid)
    return lo
