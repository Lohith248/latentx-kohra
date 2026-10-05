"""Static world context: scenario + terrain + projection + grid references. Never mutated by `step`."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import yaml
from numpy.typing import NDArray
from pyproj import Transformer

from kohra.scenario.load import REPO_ROOT, resolve_path
from kohra.scenario.schema import Scenario
from kohra.sim.move import build_cost_grid
from kohra.sim.terrain import Terrain

XY = tuple[float, float]
GRID_RE = re.compile(r"^(\d{3}) (\d{3})$")


@dataclass
class World:
    scenario: Scenario
    terrain: Terrain
    grading: dict[str, Any]
    templates: dict[str, list[str]]
    order_templates: dict[str, list[str]]
    _fwd: Transformer = field(init=False, repr=False)
    _inv: Transformer = field(init=False, repr=False)
    origin: XY = field(init=False)
    bbox_xy: tuple[float, float, float, float] = field(init=False)
    places_xy: dict[str, XY] = field(init=False)
    routes_xy: dict[str, list[XY]] = field(init=False)
    link_cache: dict[tuple[Any, ...], tuple[float, float]] = field(default_factory=dict, repr=False)
    cost: dict[str, NDArray[np.float64]] = field(init=False, repr=False)
    cost_no_ford: dict[str, NDArray[np.float64]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        crs = self.scenario.terrain.crs_sim
        self._fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        self.origin = self.to_xy(self.scenario.terrain.grid_origin)
        b = self.scenario.terrain.bbox
        xs, ys = self._fwd.transform([b[0], b[2], b[0], b[2]], [b[1], b[1], b[3], b[3]])
        self.bbox_xy = (min(xs), min(ys), max(xs), max(ys))
        self.places_xy = {p.id: self.to_xy(p.lonlat) for p in self.scenario.places}
        self.routes_xy = {r.id: [self.to_xy(p) for p in r.points] for r in self.scenario.routes}
        t = self.terrain
        my, mx = t.shape90
        rr, cc = np.mgrid[0:my, 0:mx]
        lon, lat = self._inv.transform(t.x0 + (cc + 0.5) * t.res90, t.y0 - (rr + 0.5) * t.res90)
        inside = (lon >= b[0]) & (lon <= b[2]) & (lat >= b[1]) & (lat <= b[3])
        mv = self.scenario.movement
        fords = [self.places_xy[p.id] for p in self.scenario.places if p.kind == "ford"]
        self.cost, self.cost_no_ford = {}, {}
        for mob in ("foot", "vehicle"):
            args = (t, mob, mv.slope_impassable_deg[mob], mv.road_cost_factor)
            self.cost[mob] = build_cost_grid(*args, fords, inside)
            self.cost_no_ford[mob] = build_cost_grid(*args, [], inside)

    # ---- projection (edges only, D2) --------------------------------------------------------
    def to_xy(self, lonlat: tuple[float, float] | list[float]) -> XY:
        x, y = self._fwd.transform(float(lonlat[0]), float(lonlat[1]))
        return float(x), float(y)

    def to_lonlat(self, x: float, y: float) -> XY:
        lon, lat = self._inv.transform(x, y)
        return float(lon), float(lat)

    def in_bbox(self, x: float, y: float) -> bool:
        lon, lat = self.to_lonlat(x, y)
        b = self.scenario.terrain.bbox
        return b[0] <= lon <= b[2] and b[1] <= lat <= b[3]

    # ---- local grid references (D3) ---------------------------------------------------------
    def grid_ref(self, x: float, y: float) -> str:
        e = math.floor((x - self.origin[0]) / 100.0) % 1000
        n = math.floor((y - self.origin[1]) / 100.0) % 1000
        return f"{e:03d} {n:03d}"

    def grid_to_xy(self, grid: str) -> XY:
        m = GRID_RE.match(grid.strip())
        if not m:
            raise ValueError(f"bad grid {grid!r}")
        return self.origin[0] + (int(m[1]) + 0.5) * 100.0, self.origin[1] + (int(m[2]) + 0.5) * 100.0

    def place_grid(self, pid: str) -> str:
        return self.grid_ref(*self.places_xy[pid])

    def grid_affine(self) -> dict[str, list[float]]:
        """Least-squares affine lon/lat <-> local grid metres over the bbox, for the client (100 m grid
        squares; the UTM-vs-affine error over a 20 km box is far below that)."""
        b = self.scenario.terrain.bbox
        lons, lats = np.meshgrid(np.linspace(b[0], b[2], 9), np.linspace(b[1], b[3], 9))
        xs, ys = self._fwd.transform(lons.ravel(), lats.ravel())
        gx, gy = np.asarray(xs) - self.origin[0], np.asarray(ys) - self.origin[1]
        a = np.column_stack([lons.ravel(), lats.ravel(), np.ones(lons.size)])
        to_grid = np.linalg.lstsq(a, np.column_stack([gx, gy]), rcond=None)[0]
        g = np.column_stack([gx, gy, np.ones(gx.size)])
        to_ll = np.linalg.lstsq(g, np.column_stack([lons.ravel(), lats.ravel()]), rcond=None)[0]
        return {"lonlat_to_grid_m": to_grid.T.ravel().tolist(), "grid_m_to_lonlat": to_ll.T.ravel().tolist()}

    # ---- lookups ----------------------------------------------------------------------------
    def net(self, net_id: str) -> Any:
        return next(n for n in self.scenario.comms.nets if n.id == net_id)


_TERRAIN_CACHE: dict[str, Terrain] = {}


def build_world(scenario: Scenario, terrain: Terrain | None = None) -> World:
    """Load terrain (cached per path), templates and grading config for a scenario."""
    if terrain is None:
        key = str(resolve_path(scenario.terrain.terrain_file))
        if key not in _TERRAIN_CACHE:
            _TERRAIN_CACHE[key] = Terrain.load(key)
        terrain = _TERRAIN_CACHE[key]
    tdir = REPO_ROOT / "server" / "kohra" / "reports" / "templates"
    return World(
        scenario=scenario,
        terrain=terrain,
        grading=yaml.safe_load((REPO_ROOT / "config" / "grading.yaml").read_text(encoding="utf-8")),
        templates=yaml.safe_load((tdir / "reports.yaml").read_text(encoding="utf-8")),
        order_templates=yaml.safe_load((tdir / "orders.yaml").read_text(encoding="utf-8")),
    )
