"""Pydantic models for scenario YAML, injects and scripted triggers/actions (spec section 5.1)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LonLat = tuple[float, float]
Precedence = Literal["FLASH", "IMMEDIATE", "PRIORITY", "ROUTINE"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TerrainCfg(Strict):
    bbox: tuple[float, float, float, float]
    crs_sim: str = "EPSG:32643"
    terrain_file: str
    grid_origin: LonLat


class Place(Strict):
    id: str
    kind: Literal["ford", "ridge", "hill", "village", "crossroads", "area"]
    name: str
    lonlat: LonLat
    intent: str | None = None


class Route(Strict):
    id: str
    name: str
    kind: Literal["road", "track"]
    points: list[LonLat]


class Sensor(Strict):
    max_range_m: float
    base_p_per_s: float
    eye_height_m: float
    source_type: str
    sigma_base_m: float
    sigma_per_km_m: float


class Movement(Strict):
    speed_mps: dict[str, float]
    slope_impassable_deg: dict[str, float]
    road_cost_factor: float = 0.5
    pathfinding_grid_m: float = 90


class FireMission(Strict):
    delay_s: int = 120
    cep_m: float = 100
    radius_m: float = 150
    damage_pct: float = 15


class Outcomes(Strict):
    engage_range_m: dict[str, float]
    attrition_per_min: dict[str, dict[str, float]]
    combat_ineffective_below: float = 30
    fire_mission: FireMission = FireMission()


class Net(Strict):
    id: str
    name: str
    freq_mhz: float
    bandwidth_khz: float = 25
    data_rate_bps: float = 1200


class LinkModel(Strict):
    noise_figure_db: float = 8
    theta_db: float = 6.0
    slope_per_db: float = 0.7
    extra_loss_db: float = 6
    k_factor: float = 1.3333
    diffraction: Literal["single_knife_edge", "deygout3"] = "single_knife_edge"
    profile_step_m: float = 30
    partial_band_db: float = 3.0
    partial_field_drop_p: float = 0.5
    overhead_bits: int = 400
    preamble_s: float = 0.5


class FadingOverlay(Strict):
    enabled: bool = False
    p: float = 0.02
    r: float = 0.3
    loss_bad: float = 0.5


class Comms(Strict):
    nets: list[Net]
    link_model: LinkModel = LinkModel()
    handling_delay_s: dict[str, float] = Field(
        default_factory=lambda: {"FLASH": 0.0, "IMMEDIATE": 2.0, "PRIORITY": 10.0, "ROUTINE": 30.0}
    )
    fading_overlay: FadingOverlay = FadingOverlay()


class Radio(Strict):
    power_dbm: float
    antenna_m: float
    gain_dbi: float = 0
    nets: list[str]


class GE(Strict):
    p: float
    r: float


class JammerCfg(Strict):
    id: str
    power_dbm: float
    antenna_m: float
    gain_dbi: float = 0
    freq_mhz: float
    bandwidth_khz: float
    mode: Literal["continuous", "intermittent"] = "continuous"
    ge: GE | None = None
    active: bool = True


class UnitCfg(Strict):
    id: str
    callsign: str | None = None
    role: Literal["coy_hq", "platoon", "bn_hq", "section", "ew"]
    player_role: str | None = None
    type: Literal["infantry", "apc", "tank", "recce", "hq", "ew"]
    echelon: Literal["section", "platoon", "company", "battalion"]
    mobility: Literal["foot", "vehicle"]
    sidc: str
    lonlat: LonLat
    strength: float = 100
    posture: Literal["moving", "stationary", "dug_in"] = "stationary"
    radio: Radio | None = None
    sensors: list[str] = []
    jammer: JammerCfg | None = None


class Side(Strict):
    units: list[UnitCfg]


class ContactTrig(Strict):
    unit: str
    within_m: float
    los: bool = False


class UnitPct(Strict):
    unit: str
    pct: float


class UnitRef(Strict):
    unit: str


class Trigger(Strict):
    at_tick: int | None = None
    contact: ContactTrig | None = None
    strength_below: UnitPct | None = None
    arrived: UnitRef | None = None
    observed: UnitRef | None = None

    @model_validator(mode="after")
    def _one_key(self) -> Trigger:
        if sum(v is not None for v in self.__dict__.values()) != 1:
            raise ValueError("trigger needs exactly one key")
        return self


class Action(Strict):
    unit: str
    action: Literal["move", "halt", "hold", "posture", "withdraw", "jammer_on", "jammer_off"]
    to: LonLat | None = None
    to_place: str | None = None
    via_route: str | None = None
    speed: Literal["tactical", "fast"] = "tactical"
    value: Literal["moving", "stationary", "dug_in"] | None = None
    jammer: str | None = None


class PlanRule(Strict):
    when: Trigger
    do: list[Action]


class ScriptMsg(Strict):
    when: Trigger
    template: str
    phrasing: int | None = None
    fields: dict[str, str] = {}
    grade: str | None = None
    precedence: Precedence = "PRIORITY"


class BnScript(Strict):
    messages: list[ScriptMsg] = []


class StandingRules(Strict):
    locstat_every_s: int = 180
    initial_locstat_s: int | None = None  # an opening LOCSTAT round at this tick, so the picture is not empty
    contact_cooldown_s: int = 120
    track_drop_s: int = 300
    ack_orders: bool = True
    sitrep_when_strength_below: float = 50
    lost_comms_continue_last_order: bool = True


class BlueScript(Strict):
    bn_hq: BnScript = BnScript()
    standing_rules: StandingRules = StandingRules()


class DecisionPoint(Strict):
    id: str
    when: Trigger
    describes: str


# ---- injects ---------------------------------------------------------------------------------


class JammerAdd(Strict):
    id: str
    lonlat: LonLat
    power_dbm: float
    antenna_m: float
    gain_dbi: float = 0
    freq_mhz: float
    bandwidth_khz: float
    mode: Literal["continuous", "intermittent"] = "continuous"
    ge: GE | None = None
    duration_s: int | None = None


class JammerMove(Strict):
    id: str
    lonlat: LonLat


class JammerRemove(Strict):
    id: str


class NetCut(Strict):
    net: str
    duration_s: int


class NetDelay(Strict):
    net: str
    extra_s: float
    duration_s: int


class PlantedReport(Strict):
    net: str
    from_callsign: str
    to_callsign: str
    template: str
    phrasing: int | None = None
    fields: dict[str, str]
    grade: str
    precedence: Precedence = "PRIORITY"


class GnssZoneAdd(Strict):
    id: str
    lonlat: LonLat
    radius_m: float
    bearing_deg: float
    rate_mps: float
    max_offset_m: float
    recover_mps: float | None = None
    duration_s: int | None = None


INJECT_ARGS: dict[str, type[Strict]] = {
    "jammer_add": JammerAdd,
    "jammer_move": JammerMove,
    "jammer_remove": JammerRemove,
    "net_cut": NetCut,
    "net_delay": NetDelay,
    "planted_report": PlantedReport,
    "gnss_zone_add": GnssZoneAdd,
}

InjectKind = Literal[
    "jammer_add", "jammer_move", "jammer_remove", "net_cut", "net_delay", "planted_report", "gnss_zone_add"
]


class Inject(Strict):
    at_tick: int | None = None
    kind: InjectKind
    args: dict[str, Any]

    @model_validator(mode="after")
    def _check_args(self) -> Inject:
        INJECT_ARGS[self.kind].model_validate(self.args)
        return self

    def parsed(self) -> Strict:
        return INJECT_ARGS[self.kind].model_validate(self.args)


class Scenario(Strict):
    schema_version: int = 1
    id: str
    title: str
    classification_label: str = "ILLUSTRATIVE · UNCLASSIFIED · FICTIONAL NAMES"
    seed: int
    tick_seconds: float = 1.0
    duration_ticks: int
    start_clock: str
    terrain: TerrainCfg
    labels: dict[str, str] = {}
    places: list[Place] = []
    routes: list[Route] = []
    sensors: dict[str, Sensor] = {}
    movement: Movement
    outcomes: Outcomes
    comms: Comms
    sides: dict[str, Side]
    red_plan: list[PlanRule] = []
    blue_script: BlueScript = BlueScript()
    decision_points: list[DecisionPoint] = []
    injects: list[Inject] = []

    @field_validator("start_clock")
    @classmethod
    def _clock(cls, v: str) -> str:
        if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", v):
            raise ValueError("start_clock must be HH:MM:SS")
        return v

    @model_validator(mode="after")
    def _refs(self) -> Scenario:
        if not set(self.sides) <= {"blue", "red"} or "blue" not in self.sides:
            raise ValueError("sides must be 'blue' (required) and 'red'")
        if set(self.comms.handling_delay_s) != {"FLASH", "IMMEDIATE", "PRIORITY", "ROUTINE"}:
            raise ValueError("handling_delay_s needs FLASH, IMMEDIATE, PRIORITY and ROUTINE")
        units = [u for s in self.sides.values() for u in s.units]
        ids = [u.id for u in units]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate unit ids")
        players = [u for u in self.sides["blue"].units if u.player_role]
        if len(players) != 1:
            raise ValueError("exactly one blue unit must have player_role in M1")
        nets = {n.id for n in self.comms.nets}
        for u in units:
            if u.radio and not set(u.radio.nets) <= nets:
                raise ValueError(f"{u.id}: unknown net")
            for s in u.sensors:
                if s not in self.sensors:
                    raise ValueError(f"{u.id}: unknown sensor {s}")
        places = {p.id for p in self.places}
        routes = {r.id for r in self.routes}
        for rule in self.red_plan:
            for a in rule.do:
                if a.unit not in ids:
                    raise ValueError(f"red_plan: unknown unit {a.unit}")
                if a.to_place and a.to_place not in places:
                    raise ValueError(f"red_plan: unknown place {a.to_place}")
                if a.via_route and a.via_route not in routes:
                    raise ValueError(f"red_plan: unknown route {a.via_route}")
        return self

    def all_units(self) -> list[UnitCfg]:
        return [u for side in ("blue", "red") if side in self.sides for u in self.sides[side].units]

    def place(self, pid: str) -> Place:
        return next(p for p in self.places if p.id == pid)

    def route(self, rid: str) -> Route:
        return next(r for r in self.routes if r.id == rid)

    def player_unit(self) -> UnitCfg:
        return next(u for u in self.sides["blue"].units if u.player_role)
