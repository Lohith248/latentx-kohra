"""Small deterministic synthetic DEMs (D28). Built in memory so CI never needs a download."""

from __future__ import annotations

import numpy as np
from kohra.sim.terrain import Terrain

RES = 30.0
X0, Y0 = 499_980.0, 1_250_010.0  # west / north edge; multiples of 30 m so cells align with the link-cache snap


def flat(width_m: float = 9000, height_m: float = 3000, z: float = 50.0) -> Terrain:
    ny, nx = int(height_m // RES), int(width_m // RES)
    return Terrain.from_elev(np.full((ny, nx), z, np.float32), X0, Y0, RES)


def ridge(height: float = 150.0, at_x_m: float = 4500.0, width_m: float = 9000, height_m: float = 3000,
          z: float = 50.0, sigma_m: float = 300.0) -> Terrain:
    """Flat ground with a north-south ridge (Gaussian cross-section) of known height at x0 + at_x_m."""
    ny, nx = int(height_m // RES), int(width_m // RES)
    xs = (np.arange(nx) + 0.5) * RES
    prof = z + height * np.exp(-((xs - at_x_m) ** 2) / (2 * sigma_m**2))
    return Terrain.from_elev(np.tile(prof, (ny, 1)).astype(np.float32), X0, Y0, RES)


def cell_centre(x_m: float, y_m: float) -> tuple[float, float]:
    """Fixture-relative metres -> absolute UTM at the nearest 30 m cell centre (keeps link maths exact)."""
    return X0 + (np.floor(x_m / RES) + 0.5) * RES, Y0 - (np.floor(y_m / RES) + 0.5) * RES


def flat_for_bbox(world_bbox_xy: tuple[float, float, float, float], z: float = 40.0) -> Terrain:
    """Flat terrain covering a scenario bbox (+1 km) in its own CRS."""
    x0, y0, x1, y1 = world_bbox_xy
    x0, y1 = np.floor((x0 - 1000) / 90) * 90, np.ceil((y1 + 1000) / 90) * 90
    nx = int(np.ceil((x1 + 1000 - x0) / 90)) * 3
    ny = int(np.ceil((y1 - (y0 - 1000)) / 90)) * 3
    return Terrain.from_elev(np.full((ny, nx), z, np.float32), float(x0), float(y1), RES)
