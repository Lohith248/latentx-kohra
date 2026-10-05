"""Build data/terrain/terrain.npz and data/tiles/dem.pmtiles from the fetched DEM and basemap.

    uv run --extra terrain python scripts/build_terrain.py [--scenario scenarios/ridge.yaml]

Steps: reproject GLO-30 to EPSG:32643 at 30 m (bbox + 1 km), rasterise water/roads/buildings/forest
from the OSM basemap tiles, derive the 90 m slope/cost grid, then encode terrarium raster-dem tiles
(z8-z13). Finishes with an elevation cross-check against the source GeoTIFF at 5 scenario places.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import yaml
from PIL import Image, ImageDraw
from pmtiles.reader import MmapSource, Reader
from pmtiles.tile import Compression, TileType
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "server"), str(ROOT / "scripts")]

from kohra.sim.terrain import (  # noqa: E402
    LC_BUILT,
    LC_FOREST,
    LC_ROAD,
    LC_STREAM,
    LC_WATER,
    Terrain,
    derive_90m,
)
from tilekit import (  # noqa: E402
    RES,
    build_dem_tiles,
    decode_mvt,
    tile_coord_to_lonlat,
    tiles_for_bbox,
    utm_grid,
    write_pmtiles,
)

ROAD_KINDS = {"highway", "major_road", "minor_road"}
BUILT_LANDUSE = {"residential", "commercial", "industrial", "retail"}
FOREST_LANDUSE = {"forest", "wood", "nature_reserve"}


def reproject_dem(src_path: Path, x0: float, y1: float, ny: int, nx: int) -> np.ndarray:
    out = np.zeros((ny, nx), np.float32)
    with rasterio.open(src_path) as src:
        reproject(source=rasterio.band(src, 1), destination=out, dst_transform=from_origin(x0, y1, RES, RES),
                  dst_crs="EPSG:32643", resampling=Resampling.bilinear)
    return out


def rasterise_landcover(basemap: Path, bbox: tuple[float, float, float, float], x0: float, y1: float,
                        ny: int, nx: int) -> np.ndarray:
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    img = Image.new("L", (nx, ny), 0)
    draw = ImageDraw.Draw(img)
    with basemap.open("rb") as f:
        reader = Reader(MmapSource(f))
        z = int(reader.header()["max_zoom"])
        layers_by_pass: dict[int, list[tuple[int, list[tuple[float, float]], int]]] = {i: [] for i in range(5)}
        for tx, ty in tiles_for_bbox(bbox, z):
            data = reader.get(z, tx, ty)
            if not data:
                continue
            for lname, (extent, feats) in decode_mvt(data).items():
                for gtype, props, parts in feats:
                    kind = str(props.get("kind", ""))
                    if lname == "landuse" and gtype == 3 and kind in FOREST_LANDUSE:
                        code, pas, w = LC_FOREST, 0, 0
                    elif lname == "landuse" and gtype == 3 and kind in BUILT_LANDUSE:
                        code, pas, w = LC_BUILT, 1, 0
                    elif lname == "buildings" and gtype == 3:
                        code, pas, w = LC_BUILT, 1, 0
                    elif lname == "roads" and gtype == 2 and kind in ROAD_KINDS:
                        code, pas, w = LC_ROAD, 2, 1
                    elif lname == "water" and gtype == 3:
                        code, pas, w = LC_WATER, 3, 0
                    elif lname == "water" and gtype == 2 and kind in ("river", "canal", "stream"):
                        code, pas, w = LC_STREAM, 0, 1  # fordable on foot and by vehicle, slowly
                    else:
                        continue
                    for part in parts:
                        a = np.asarray(part, np.float64)
                        lon, lat = tile_coord_to_lonlat(z, tx, ty, a[:, 0], a[:, 1], extent)
                        ux, uy = fwd.transform(lon, lat)
                        px = (np.asarray(ux) - x0) / RES
                        py = (y1 - np.asarray(uy)) / RES
                        layers_by_pass[pas].append((code, list(zip(px.tolist(), py.tolist(), strict=True)), w))
    for pas in range(5):  # later passes overwrite earlier ones: water beats roads beats buildings
        for code, pts, w in layers_by_pass[pas]:
            if len(pts) < 2:
                continue
            if w == 0 and len(pts) >= 3:
                draw.polygon(pts, fill=code)
            else:
                draw.line(pts, fill=code, width=max(w, 1))
    return np.asarray(img, np.uint8)


def source_bilinear(src_path: Path) -> tuple[np.ndarray, rasterio.Affine]:
    with rasterio.open(src_path) as src:
        return src.read(1).astype(np.float64), src.transform


def make_sampler(arr: np.ndarray, tr: rasterio.Affine):
    def sample(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        c = np.clip((lon - tr.c) / tr.a - 0.5, 0, arr.shape[1] - 1.000001)
        r = np.clip((lat - tr.f) / tr.e - 0.5, 0, arr.shape[0] - 1.000001)
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        fc, fr = c - c0, r - r0
        return (arr[r0, c0] * (1 - fc) * (1 - fr) + arr[r0, c0 + 1] * fc * (1 - fr)
                + arr[r0 + 1, c0] * (1 - fc) * fr + arr[r0 + 1, c0 + 1] * fc * fr)
    return sample


def elevation_check(terrain: Terrain, src_path: Path, places: list[dict[str, object]]) -> list[dict[str, object]]:
    """Compare terrain.npz with the source GeoTIFF at each place, snapped to the nearest 30 m cell centre
    (so the check sees the reprojected value itself, not a second interpolation of it)."""
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    inv = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    arr, tr = source_bilinear(src_path)
    sample = make_sampler(arr, tr)
    rows = []
    with rasterio.open(src_path) as src:
        for p in places:
            x, y = fwd.transform(*p["lonlat"])  # type: ignore[misc]
            x = terrain.x0 + (np.floor((x - terrain.x0) / RES) + 0.5) * RES
            y = terrain.y0 - (np.floor((terrain.y0 - y) / RES) + 0.5) * RES
            lon, lat = (round(float(v), 6) for v in inv.transform(x, y))
            ours = terrain.elev_pt(x, y)
            src_bil = float(sample(np.array([lon]), np.array([lat]))[0])
            src_near = float(next(src.sample([(lon, lat)]))[0])
            rows.append({"place": p["id"], "lon": lon, "lat": lat, "terrain_npz": round(ours, 2),
                         "source_bilinear": round(src_bil, 2), "source_nearest": round(src_near, 2),
                         "diff_bilinear": round(ours - src_bil, 2), "diff_nearest": round(ours - src_near, 2)})
    rng = np.random.default_rng(0)
    lon = rng.uniform(76.12, 76.28, 3000)
    lat = rng.uniform(11.22, 11.33, 3000)
    ux, uy = fwd.transform(lon, lat)
    d = terrain.elev_at(np.asarray(ux), np.asarray(uy)) - sample(lon, lat)
    print(f"3000 random points (any position): mean diff {d.mean():+.2f} m, mean |diff| {np.abs(d).mean():.2f} m")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=str(ROOT / "scenarios" / "ridge.yaml"))
    args = ap.parse_args()
    t0 = time.time()
    scen = yaml.safe_load(Path(args.scenario).read_text(encoding="utf-8"))
    bbox = tuple(scen["terrain"]["bbox"])
    manifest = json.loads((ROOT / "data" / "raw" / "MANIFEST.json").read_text(encoding="utf-8"))
    dem_path = ROOT / manifest["files"]["dem"]["path"]
    basemap = ROOT / manifest["files"]["basemap"]["path"]

    x0, y1, ny, nx = utm_grid(bbox)
    print(f"grid {nx}x{ny} @ {RES} m, origin ({x0}, {y1})")
    elev = reproject_dem(dem_path, x0, y1, ny, nx)
    lc = rasterise_landcover(basemap, bbox, x0, y1, ny, nx)
    print("landcover share:", {k: round(float((lc == v).mean()), 4) for k, v in
                               {"water": LC_WATER, "road": LC_ROAD, "built": LC_BUILT, "forest": LC_FOREST}.items()})
    slope90, lc90 = derive_90m(elev, lc, RES)
    terrain = Terrain(elev, lc, x0, y1, RES, slope90, lc90, 90.0, False)
    out = ROOT / "data" / "terrain"
    out.mkdir(parents=True, exist_ok=True)
    cost = (1.0 + slope90 / 10.0).astype(np.float32)
    cost[lc90 == LC_WATER] = np.inf
    terrain.save(out / "terrain.npz", cost)
    print("wrote", out / "terrain.npz")

    arr, tr = source_bilinear(dem_path)
    tiles = build_dem_tiles(make_sampler(arr, tr), bbox, range(8, 14))
    write_pmtiles(ROOT / "data" / "tiles" / "dem.pmtiles", tiles, bbox, TileType.PNG, Compression.NONE,
                  {"name": "kohra-dem", "encoding": "terrarium", "attribution": "Copernicus DEM GLO-30"})
    print(f"wrote dem.pmtiles ({len(tiles)} tiles)")

    rows = elevation_check(terrain, dem_path, [p for p in scen["places"]][:5])
    for r in rows:
        print(r)
    (out / "elevation_check.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    manifest["terrain_built"] = {"seconds": round(time.time() - t0, 1), "grid": [nx, ny], "x0": x0, "y0": y1}
    (ROOT / "data" / "raw" / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "MANIFEST.json").write_text(json.dumps({**manifest, "synthetic": False}, indent=2) + "\n",
                                       encoding="utf-8")
    print(f"done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
