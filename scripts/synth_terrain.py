"""Seeded synthetic terrain with the same files and interface as the real pipeline (fallback and CI).

    uv run --extra terrain python scripts/synth_terrain.py [--scenario scenarios/ridge.yaml] [--seed 7]

Fractal noise plus explicit features that match the scenario intents: a river through the ford
(OSPREY) separating the red and blue banks, a ridge at KESTREL across the OSPREY-JUNIPER line, a hill at
HERON and a road along every scenario route. Writes terrain.npz, basemap.pmtiles (raster), dem.pmtiles
and data/raw/MANIFEST.json with "synthetic": true.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw
from pmtiles.tile import Compression, TileType
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "server"), str(ROOT / "scripts")]

from kohra.sim.terrain import LC_BUILT, LC_FOREST, LC_ROAD, LC_WATER, Terrain, derive_90m  # noqa: E402
from tilekit import (  # noqa: E402
    RES,
    build_dem_tiles,
    tile_pixel_lonlat,
    tiles_for_bbox,
    utm_grid,
    write_pmtiles,
)

COLOURS = {0: (214, 222, 196), LC_WATER: (120, 160, 210), LC_ROAD: (240, 236, 220), LC_BUILT: (200, 190, 180),
           LC_FOREST: (170, 196, 150)}


def fractal(shape: tuple[int, int], rng: np.random.Generator, octaves: int = 5) -> np.ndarray:
    out = np.zeros(shape)
    for o in range(octaves):
        k = 2 ** (o + 2)
        coarse = rng.standard_normal((shape[0] // k + 2, shape[1] // k + 2))
        img = Image.fromarray(coarse.astype(np.float32), "F").resize((shape[1], shape[0]), Image.BICUBIC)
        out += np.asarray(img, np.float64) / (o + 1)
    return out / np.abs(out).max()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=str(ROOT / "scenarios" / "ridge.yaml"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--maxzoom", type=int, default=14)
    args = ap.parse_args()
    t0 = time.time()
    scen = yaml.safe_load(Path(args.scenario).read_text(encoding="utf-8"))
    bbox = tuple(scen["terrain"]["bbox"])
    crs = scen["terrain"].get("crs_sim", "EPSG:32643")
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    places = {p["id"]: np.array(fwd.transform(*p["lonlat"])) for p in scen["places"]}
    rng = np.random.default_rng(args.seed)

    x0, y1, ny, nx = utm_grid(bbox, crs)
    xs = x0 + (np.arange(nx) + 0.5) * RES
    ys = y1 - (np.arange(ny) + 0.5) * RES
    X, Y = np.meshgrid(xs, ys)
    elev = 45.0 + 12.0 * fractal((ny, nx), rng)

    ford, kes, jun, her = places["OSPREY"], places["KESTREL"], places["JUNIPER"], places["HERON"]
    axis = (jun - ford) / np.linalg.norm(jun - ford)  # ford -> red assembly
    perp = np.array([axis[1], -axis[0]])
    # river: a gently meandering line through the ford, perpendicular to the ford->JUNIPER axis
    along = (X - ford[0]) * perp[0] + (Y - ford[1]) * perp[1]
    across = (X - ford[0]) * axis[0] + (Y - ford[1]) * axis[1]
    centre = 250.0 * np.sin(along / 1800.0) * np.clip(np.abs(along) / 1500.0, 0, 1)
    dist_r = np.abs(across - centre)
    elev -= 25.0 * np.exp(-((dist_r / 600.0) ** 2))
    water = dist_r < 70.0
    elev[water] = np.minimum(elev[water], 12.0)
    # KESTREL ridge across the ford->JUNIPER line; HERON hill
    ka = (X - kes[0]) * axis[0] + (Y - kes[1]) * axis[1]
    kp = (X - kes[0]) * perp[0] + (Y - kes[1]) * perp[1]
    elev += 260.0 * np.exp(-((ka / 350.0) ** 2) - ((kp / 2200.0) ** 4))
    elev += 160.0 * np.exp(-(((X - her[0]) ** 2 + (Y - her[1]) ** 2) / (2 * 320.0**2)))

    forest = fractal((ny, nx), np.random.default_rng(args.seed + 1), 3) > 0.35
    lc = np.where(forest, LC_FOREST, 0).astype(np.uint8)
    img = Image.fromarray(lc, "L")
    draw = ImageDraw.Draw(img)
    for p in scen["places"]:
        if p["kind"] == "village":
            px = (places[p["id"]][0] - x0) / RES
            py = (y1 - places[p["id"]][1]) / RES
            draw.ellipse([px - 12, py - 12, px + 12, py + 12], fill=LC_BUILT)
    for r in scen.get("routes", []):
        pts = [((fwd.transform(*q)[0] - x0) / RES, (y1 - fwd.transform(*q)[1]) / RES) for q in r["points"]]
        draw.line(pts, fill=LC_ROAD, width=2)
    lc = np.asarray(img, np.uint8).copy()
    lc[water] = LC_WATER
    elev = elev.astype(np.float32)

    slope90, lc90 = derive_90m(elev, lc, RES)
    terrain = Terrain(elev, lc, x0, y1, RES, slope90, lc90, 90.0, True)
    out = ROOT / "data" / "terrain"
    out.mkdir(parents=True, exist_ok=True)
    terrain.save(out / "terrain.npz", (1.0 + slope90 / 10.0).astype(np.float32))

    def sample_xy(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ux, uy = fwd.transform(lon, lat)
        return np.asarray(ux), np.asarray(uy)

    def dem_sample(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        ux, uy = sample_xy(lon, lat)
        return terrain.elev_at(ux.ravel(), uy.ravel()).reshape(lon.shape)

    tiles_dir = ROOT / "data" / "tiles"
    write_pmtiles(tiles_dir / "dem.pmtiles", build_dem_tiles(dem_sample, bbox, range(8, 14)), bbox, TileType.PNG,
                  Compression.NONE, {"name": "kohra-dem-synthetic", "encoding": "terrarium"})
    base = {}
    pal = np.zeros((256, 3), np.uint8)
    for k, c in COLOURS.items():
        pal[k] = c
    for z in range(8, args.maxzoom + 1):
        for tx, ty in tiles_for_bbox(bbox, z):
            lon, lat = tile_pixel_lonlat(z, tx, ty)
            ux, uy = sample_xy(lon, lat)
            c = np.clip(((ux - x0) // RES).astype(int), 0, nx - 1)
            r = np.clip(((y1 - uy) // RES).astype(int), 0, ny - 1)
            rgb = pal[lc[r, c]]
            buf = io.BytesIO()
            Image.fromarray(rgb, "RGB").save(buf, "PNG", optimize=True)
            base[(z, tx, ty)] = buf.getvalue()
    write_pmtiles(tiles_dir / "basemap.pmtiles", base, bbox, TileType.PNG, Compression.NONE,
                  {"name": "kohra-basemap-synthetic"})
    manifest = json.dumps({"synthetic": True, "seed": args.seed, "generated": dt.datetime.now(dt.UTC).isoformat(),
                           "bbox": list(bbox), "grid": [nx, ny], "x0": x0, "y0": y1}, indent=2) + "\n"
    (out / "MANIFEST.json").write_text(manifest, encoding="utf-8")  # describes what is currently built
    raw = ROOT / "data" / "raw"
    if not (raw / "MANIFEST.json").exists():  # never clobber a real download's manifest
        raw.mkdir(parents=True, exist_ok=True)
        (raw / "MANIFEST.json").write_text(manifest, encoding="utf-8")
    print(f"synthetic terrain written ({nx}x{ny}, {len(base)} basemap tiles) in {time.time() - t0:.1f} s")
    print("SYNTHETIC TERRAIN: the client will show a banner.")


if __name__ == "__main__":
    main()
