"""Mission clock (D4): tick -> HH:MM:SS from the scenario start clock."""

from __future__ import annotations


def _start_s(start_clock: str) -> int:
    h, m, s = (int(v) for v in start_clock.split(":"))
    return h * 3600 + m * 60 + s


def clock_str(start_clock: str, tick: int, tick_s: float = 1.0) -> str:
    t = (_start_s(start_clock) + int(tick * tick_s)) % 86400
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def hhmm(start_clock: str, tick: int, tick_s: float = 1.0) -> str:
    return clock_str(start_clock, tick, tick_s).replace(":", "")[:4]
