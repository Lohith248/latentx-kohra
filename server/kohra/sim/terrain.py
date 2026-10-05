"""Preprocessed terrain: elevation sampling, line of sight and the 90 m movement grid.

`terrain.npz` layout (written by scripts/build_terrain.py or scripts/synth_terrain.py):
  elev      float32 [ny, nx]  surface elevation, metres; row 0 is the northern edge
  landcover uint8   [ny, nx]  LC_* codes below, same grid as elev
  x0, y0    float64           UTM easting of the west edge / northing of the north edge
  res       float64           elev cell size (30 m)
  slope90   float32 [my, mx]  slope in degrees on the 90 m grid (same x0/y0 origin)
  lc90      uint8   [my, mx]  dominant land cover on the 90 m grid (water > road > stream > built > forest)
  cost      float32 [my, mx]  default foot cost factor (informational; run time rebuilds per mobility)
  synthetic bool
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

LC_OPEN, LC_WATER, LC_ROAD, LC_BUILT, LC_FOREST, LC_STREAM = 0, 1, 2, 3, 4, 5
F64 = NDArray[np.float64]


@dataclass(frozen=True)
class Terrain:
    elev: NDArray[np.float32]
    landcover: NDArray[np.uint8]
    x0: float
    y0: float
    res: float
    slope90: NDArray[np.float32]
    lc90: NDArray[np.uint8]
    res90: float = 90.0
    synthetic: bool = False

    # ---- construction ----------------------------------------------------------------------
    @staticmethod
    def load(path: str | Path) -> Terrain:
        with np.load(path) as d:
            return Terrain(
                elev=d["elev"].astype(np.float32),
                landcover=d["landcover"].astype(np.uint8),
                x0=float(d["x0"]),
                y0=float(d["y0"]),
                res=float(d["res"]),
                slope90=d["slope90"].astype(np.float32),
                lc90=d["lc90"].astype(np.uint8),
                res90=float(d["res90"]) if "res90" in d else 90.0,
                synthetic=bool(d["synthetic"]) if "synthetic" in d else False,
            )

    @staticmethod
    def from_elev(elev: NDArray[np.float32], x0: float, y0: float, res: float = 30.0,
                  landcover: NDArray[np.uint8] | None = None, synthetic: bool = True) -> Terrain:
        lc = np.zeros(elev.shape, np.uint8) if landcover is None else landcover
        slope90, lc90 = derive_90m(elev, lc, res)
        return Terrain(elev.astype(np.float32), lc, x0, y0, res, slope90, lc90, 90.0, synthetic)

    def save(self, path: str | Path, cost: NDArray[np.float32] | None = None) -> None:
        np.savez_compressed(
            path, elev=self.elev, landcover=self.landcover, x0=self.x0, y0=self.y0, res=self.res,
            slope90=self.slope90, lc90=self.lc90, res90=self.res90, synthetic=self.synthetic,
            cost=cost if cost is not None else np.ones(self.slope90.shape, np.float32),
        )

    # ---- sampling --------------------------------------------------------------------------
    @property
    def bounds(self) -> tuple[float, float, float, float]:
        ny, nx = self.elev.shape
        return self.x0, self.y0 - ny * self.res, self.x0 + nx * self.res, self.y0

    def elev_at(self, xs: F64, ys: F64) -> F64:
        """Bilinear elevation at UTM points (clamped to the grid)."""
        ny, nx = self.elev.shape
        c = (np.asarray(xs, np.float64) - self.x0) / self.res - 0.5
        r = (self.y0 - np.asarray(ys, np.float64)) / self.res - 0.5
        c = np.clip(c, 0, nx - 1.000001)
        r = np.clip(r, 0, ny - 1.000001)
        c0 = np.floor(c).astype(np.int64)
        r0 = np.floor(r).astype(np.int64)
        fc, fr = c - c0, r - r0
        e = self.elev
        z = (e[r0, c0] * (1 - fc) * (1 - fr) + e[r0, c0 + 1] * fc * (1 - fr)
             + e[r0 + 1, c0] * (1 - fc) * fr + e[r0 + 1, c0 + 1] * fc * fr)
        return np.asarray(z, np.float64)

    def elev_pt(self, x: float, y: float) -> float:
        return float(self.elev_at(np.array([x]), np.array([y]))[0])

    def landcover_at(self, x: float, y: float) -> int:
        ny, nx = self.landcover.shape
        c = min(max(int((x - self.x0) // self.res), 0), nx - 1)
        r = min(max(int((self.y0 - y) // self.res), 0), ny - 1)
        return int(self.landcover[r, c])

    def profile(self, ax: float, ay: float, bx: float, by: float, step: float) -> tuple[F64, F64]:
        """Distances from A and terrain elevations sampled every `step` metres, endpoints included."""
        d = float(np.hypot(bx - ax, by - ay))
        n = max(int(np.ceil(d / step)), 1)
        t = np.linspace(0.0, 1.0, n + 1)
        return t * d, self.elev_at(ax + t * (bx - ax), ay + t * (by - ay))

    def los(self, ax: float, ay: float, ha: float, bx: float, by: float, hb: float, step: float = 30.0) -> bool:
        """Geometric line of sight between points `ha`/`hb` metres above ground."""
        dist, z = self.profile(ax, ay, bx, by, step)
        if len(z) <= 2:
            return True
        za, zb = z[0] + ha, z[-1] + hb
        line = za + (zb - za) * dist / dist[-1]
        return bool(np.all(z[1:-1] <= line[1:-1]))

    # ---- 90 m grid -------------------------------------------------------------------------
    @property
    def shape90(self) -> tuple[int, int]:
        return int(self.slope90.shape[0]), int(self.slope90.shape[1])

    def cell90(self, x: float, y: float) -> tuple[int, int]:
        my, mx = self.shape90
        c = min(max(int((x - self.x0) // self.res90), 0), mx - 1)
        r = min(max(int((self.y0 - y) // self.res90), 0), my - 1)
        return r, c

    def center90(self, r: int, c: int) -> tuple[float, float]:
        return self.x0 + (c + 0.5) * self.res90, self.y0 - (r + 0.5) * self.res90


def derive_90m(elev: NDArray[np.float32], lc: NDArray[np.uint8], res: float) -> tuple[
        NDArray[np.float32], NDArray[np.uint8]]:
    """Slope (degrees, max over 30 m sub-cells) and dominant land cover on a 3x coarser grid."""
    gy, gx = np.gradient(elev.astype(np.float64), res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    k = 3
    my, mx = elev.shape[0] // k, elev.shape[1] // k
    s = slope[: my * k, : mx * k].reshape(my, k, mx, k)
    slope90 = s.mean(axis=(1, 3)).astype(np.float32)
    blk = lc[: my * k, : mx * k].reshape(my, k, mx, k)
    water = (blk == LC_WATER).sum(axis=(1, 3))
    road = (blk == LC_ROAD).any(axis=(1, 3))
    built = (blk == LC_BUILT).sum(axis=(1, 3))
    forest = (blk == LC_FOREST).sum(axis=(1, 3))
    stream = (blk == LC_STREAM).any(axis=(1, 3))
    lc90 = np.full((my, mx), LC_OPEN, np.uint8)
    lc90[forest >= 5] = LC_FOREST
    lc90[built >= 5] = LC_BUILT
    lc90[stream] = LC_STREAM
    lc90[road] = LC_ROAD
    # Water beats road: crossings of major water exist only at scenario fords (D23). A third of the
    # block is enough so a river stays a continuous barrier on the coarse grid.
    lc90[water >= 3] = LC_WATER
    return slope90, lc90
