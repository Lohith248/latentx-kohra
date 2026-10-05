"""Mutable simulation state (the truth) and its canonical hash (D7).

Plain dataclasses of Python scalars, lists and str-keyed dicts only: no sets, no NumPy values.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from kohra.scenario.schema import Scenario
from kohra.sim.rng import Rng
from kohra.sim.world import World


@dataclass
class Unit:
    id: str
    side: str
    callsign: str
    role: str
    type: str
    mobility: str
    sidc: str
    x: float
    y: float
    strength: float
    posture: str
    nets: list[str]
    power_dbm: float
    antenna_m: float
    gain_dbi: float
    sensors: list[str]
    jammer: str | None = None
    path: list[list[float]] = field(default_factory=list)
    speed: str = "tactical"
    status: str = "in position"
    order: dict[str, Any] | None = None
    observing: str | None = None
    engaged: bool = False
    gnss_offset: list[float] = field(default_factory=lambda: [0.0, 0.0])
    gnss_recover_mps: float = 1.0
    last_locstat: int = 0
    arrived_tick: int = -1
    sitrep_low_sent: bool = False
    canary: str = ""


@dataclass
class Jammer:
    id: str
    owner: str | None
    x: float
    y: float
    power_dbm: float
    antenna_m: float
    gain_dbi: float
    freq_mhz: float
    bandwidth_khz: float
    mode: str
    ge_p: float
    ge_r: float
    active: bool
    bad: bool = False
    expires: int | None = None

    @property
    def emitting(self) -> bool:
        return self.active and (self.mode == "continuous" or self.bad)


@dataclass
class Message:
    seq: int
    msg_id: str
    net: str
    sender: str
    to: str
    kind: str
    phrasing: int
    fields: dict[str, str]
    text: str
    precedence: str
    grade: str | None
    enqueue_tick: int
    eligible_tick: int
    tx_start: int | None = None
    tx_end: int | None = None
    sinr_min: dict[str, float] = field(default_factory=dict)
    is_planted: bool = False
    contact_no: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class NetState:
    id: str
    current: int | None = None
    queue: list[int] = field(default_factory=list)
    cut_until: int = -1
    delay_extra: float = 0.0
    delay_until: int = -1


@dataclass
class Track:
    contact_no: str
    target: str
    first_tick: int
    last_seen: int
    last_report: int
    activity: str
    rep_x: float
    rep_y: float
    q: float
    source_type: str
    size: str


@dataclass
class Perception:
    """What has reached the player: the only source for player views."""
    inbox: list[dict[str, Any]] = field(default_factory=list)
    sent: list[dict[str, Any]] = field(default_factory=list)
    last_heard: dict[str, int] = field(default_factory=dict)


@dataclass
class State:
    tick: int
    seed: int
    units: dict[str, Unit]
    jammers: dict[str, Jammer]
    nets: dict[str, NetState]
    messages: dict[str, Message] = field(default_factory=dict)  # keyed by str(seq) while in flight
    tracks: dict[str, dict[str, Track]] = field(default_factory=dict)  # observer id -> target id -> track
    perception: Perception = field(default_factory=Perception)
    gnss_zones: list[dict[str, Any]] = field(default_factory=list)
    fire_missions: list[dict[str, Any]] = field(default_factory=list)
    fired_red: list[int] = field(default_factory=list)
    fired_bn: list[int] = field(default_factory=list)
    fired_dp: list[str] = field(default_factory=list)
    contact_counters: dict[str, int] = field(default_factory=dict)
    used_ids: dict[str, int] = field(default_factory=dict)
    msg_seq: int = 0
    player: str = ""

    def unit_by_callsign(self, cs: str) -> Unit | None:
        for uid in sorted(self.units):
            if self.units[uid].callsign == cs:
                return self.units[uid]
        return None


def initial_state(scenario: Scenario, world: World) -> State:
    units: dict[str, Unit] = {}
    jammers: dict[str, Jammer] = {}
    for side in ("blue", "red"):
        for u in scenario.sides[side].units if side in scenario.sides else []:
            x, y = world.to_xy(u.lonlat)
            r = u.radio
            units[u.id] = Unit(
                id=u.id, side=side, callsign=u.callsign or "", role=u.role, type=u.type, mobility=u.mobility,
                sidc=u.sidc, x=x, y=y, strength=float(u.strength), posture=u.posture,
                nets=list(r.nets) if r else [], power_dbm=r.power_dbm if r else 0.0,
                antenna_m=r.antenna_m if r else 2.0, gain_dbi=r.gain_dbi if r else 0.0,
                sensors=list(u.sensors), jammer=u.jammer.id if u.jammer else None,
            )
            if u.jammer:
                j = u.jammer
                jammers[j.id] = Jammer(
                    id=j.id, owner=u.id, x=x, y=y, power_dbm=j.power_dbm, antenna_m=j.antenna_m, gain_dbi=j.gain_dbi,
                    freq_mhz=j.freq_mhz, bandwidth_khz=j.bandwidth_khz, mode=j.mode,
                    ge_p=j.ge.p if j.ge else 0.0, ge_r=j.ge.r if j.ge else 1.0, active=j.active,
                )
    return State(
        tick=0, seed=scenario.seed, units=units, jammers=jammers,
        nets={n.id: NetState(n.id) for n in scenario.comms.nets},
        player=scenario.player_unit().callsign or "",
    )


def _plain(o: Any) -> Any:
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: _plain(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, (set, frozenset)):
        return sorted(_plain(v) for v in o)
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):  # NumPy scalar
        return o.item()
    return o


def canonical_json(obj: Any) -> str:
    return json.dumps(_plain(obj), sort_keys=True, separators=(",", ":"), allow_nan=False)


def state_hash(state: State, rng: Rng) -> str:
    """SHA-256 over canonical JSON of the state plus every RNG stream's bit_generator state (D7)."""
    payload = canonical_json({"state": state, "rng": rng.state()})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
