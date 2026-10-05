"""Airtime, delivery probability and the per-(message, receiver) draw (spec section 6.3)."""

from __future__ import annotations

import math

from kohra.scenario.schema import LinkModel


def airtime_s(text: str, lm: LinkModel, data_rate_bps: float) -> float:
    return lm.preamble_s + (8 * len(text.encode("utf-8")) + lm.overhead_bits) / data_rate_bps


def airtime_ticks(text: str, lm: LinkModel, data_rate_bps: float, tick_s: float) -> int:
    return max(math.ceil(airtime_s(text, lm, data_rate_bps) / tick_s), 1)


def p_deliver(sinr_eff_db: float, lm: LinkModel) -> float:
    x = lm.slope_per_db * (sinr_eff_db - lm.theta_db)
    if x < -700:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def p_final(sinr_eff_db: float, lm: LinkModel, fading_loss: float, net_cut: bool) -> float:
    return 0.0 if net_cut else p_deliver(sinr_eff_db, lm) * (1.0 - fading_loss)


def is_partial(sinr_eff_db: float, lm: LinkModel) -> bool:
    """Delivered but within the partial band: one field may be garbled (D18)."""
    return sinr_eff_db < lm.theta_db + lm.partial_band_db
