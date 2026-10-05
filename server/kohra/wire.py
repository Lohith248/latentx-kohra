"""Pydantic models for every socket message. The PLAYER half and the DS half are kept separate;
tests/test_no_truth_leak.py statically checks the player half against TRUTH_ONLY_KEYS."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

Precedence = Literal["FLASH", "IMMEDIATE", "PRIORITY", "ROUTINE"]
OrderKind = Literal["MOVE", "HALT", "HOLD", "OBSERVE", "WITHDRAW", "REQUEST_SITREP", "FIRE_MISSION"]
GRID_KINDS = {"MOVE", "OBSERVE", "WITHDRAW", "FIRE_MISSION"}
LonLat = tuple[float, float]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ================================ PLAYER: client -> server ======================================


class ClientOrder(_M):
    type: Literal["order"] = "order"
    to: str = Field(pattern=r"^[A-Z]+(-\d)?$")
    kind: OrderKind
    grid: str | None = Field(default=None, pattern=r"^\d{3} \d{3}$")
    speed: Literal["tactical", "fast"] | None = None
    precedence: Precedence = "PRIORITY"
    confidence: StrictInt = Field(ge=0, le=100)  # required: no default (D14)
    relied_on: list[str] = Field(max_length=50)  # required, may be empty
    client_seq: int = 0

    @model_validator(mode="after")
    def _grid(self) -> ClientOrder:
        if self.kind in GRID_KINDS and self.grid is None:
            raise ValueError(f"{self.kind} needs a grid")
        if any(not isinstance(r, str) or len(r) > 16 for r in self.relied_on):
            raise ValueError("bad relied_on id")
        return self


class ClientText(_M):
    type: Literal["text"] = "text"
    to: str = Field(pattern=r"^[A-Z]+(-\d)?$")
    net: str = Field(pattern=r"^[A-Z0-9_]{1,16}$")
    text: str = Field(min_length=1, max_length=200, pattern=r"^[\x20-\x7E]+$")
    precedence: Precedence = "PRIORITY"
    client_seq: int = 0


# ================================ PLAYER: server -> client ======================================


class PStation(_M):
    callsign: str
    nets: list[str]


class PNet(_M):
    id: str
    name: str


class PPlace(_M):
    name: str
    kind: str
    lonlat: LonLat


class PRoute(_M):
    name: str
    points: list[LonLat]


class PHello(_M):
    type: Literal["hello"] = "hello"
    role: Literal["player"] = "player"
    title: str
    classification: str
    callsign: str
    stations: list[PStation]
    nets: list[PNet]
    places: list[PPlace]
    routes: list[PRoute]
    bbox: tuple[float, float, float, float]
    grid_affine: dict[str, list[float]]
    start_clock: str
    duration_ticks: int
    tick_seconds: float
    synthetic: bool
    basemap_kind: Literal["vector", "raster"]
    labels: dict[str, str]
    own_sidc: str


class PRadio(_M):
    type: Literal["radio"] = "radio"
    msg_id: str
    tick: int
    clock: str
    net: str
    sender: str
    to: str
    precedence: Precedence
    text: str
    fields: dict[str, str | None]
    grade: str | None
    partial: bool
    contact_no: str | None
    direction: Literal["in", "out"]


class PStatus(_M):
    type: Literal["status"] = "status"
    tick: int
    clock: str
    hq_lonlat: LonLat
    last_heard: dict[str, int]
    speed: float
    paused: bool
    endex: bool
    final_hash: str | None = None


class POrderResult(_M):
    type: Literal["order_result"] = "order_result"
    ok: bool
    client_seq: int
    reason: str | None = None


class PHistory(_M):
    type: Literal["history"] = "history"
    messages: list[PRadio]


PLAYER_MODELS: tuple[type[BaseModel], ...] = (
    ClientOrder, ClientText, PStation, PNet, PPlace, PRoute, PHello, PRadio, PStatus, POrderResult, PHistory)


# ================================ DS (truth view, read-only) ===================================


class DsUnit(_M):
    id: str
    side: str
    callsign: str
    sidc: str
    lonlat: LonLat
    strength: float
    posture: str
    status: str


class DsJammer(_M):
    id: str
    lonlat: LonLat
    active: bool
    emitting: bool
    radius_m: float


class DsLink(_M):
    net: str
    a: str
    b: str
    a_lonlat: LonLat
    b_lonlat: LonLat
    sinr_db: float


class DsEvent(_M):
    tick: int
    clock: str
    kind: str
    detail: dict[str, Any]


class DsState(_M):
    type: Literal["ds_state"] = "ds_state"
    tick: int
    clock: str
    theta_db: float
    units: list[DsUnit]
    jammers: list[DsJammer]
    links: list[DsLink]
    events: list[DsEvent]
    endex: bool
    final_hash: str | None = None


class DsHello(_M):
    type: Literal["hello"] = "hello"
    role: Literal["ds"] = "ds"
    title: str
    classification: str
    places: list[PPlace]
    routes: list[PRoute]
    bbox: tuple[float, float, float, float]
    synthetic: bool
    basemap_kind: Literal["vector", "raster"]
    start_clock: str
    duration_ticks: int
