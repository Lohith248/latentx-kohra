"""Shared offline helpers for the terrain builders: tile math, a minimal MVT decoder, terrarium
PNG encoding and PMTiles writing. Offline pipeline only (needs the `[terrain]` extra)."""

from __future__ import annotations

import gzip
import io
import math
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
from PIL import Image
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

RES = 30.0
MARGIN = 1000.0


def utm_grid(bbox: tuple[float, float, float, float], crs: str = "EPSG:32643") -> tuple[float, float, int, int]:
    """West edge, north edge and shape of a 30 m grid covering bbox + 1 km (shape divisible by 3)."""
    from pyproj import Transformer

    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = fwd.transform([bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]])
    step = RES * 3
    x0 = math.floor((min(xs) - MARGIN) / step) * step
    x1 = math.ceil((max(xs) + MARGIN) / step) * step
    y0 = math.floor((min(ys) - MARGIN) / step) * step
    y1 = math.ceil((max(ys) + MARGIN) / step) * step
    return float(x0), float(y1), int(round((y1 - y0) / RES)), int(round((x1 - x0) / RES))


# ---- web mercator tile math -------------------------------------------------------------------


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def tiles_for_bbox(bbox: tuple[float, float, float, float], z: int) -> Iterator[tuple[int, int]]:
    x0, y0 = lonlat_to_tile(bbox[0], bbox[3], z)
    x1, y1 = lonlat_to_tile(bbox[2], bbox[1], z)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            yield x, y


def tile_pixel_lonlat(z: int, x: int, y: int, size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    """Lon/lat of the centre of every pixel of a tile, as [size, size] arrays."""
    n = 2**z
    px = (x + (np.arange(size) + 0.5) / size) / n
    py = (y + (np.arange(size) + 0.5) / size) / n
    lon = px * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * py))))
    return np.meshgrid(lon, lat)


def tile_coord_to_lonlat(z: int, x: int, y: int, tx: np.ndarray, ty: np.ndarray, extent: int) -> tuple[
        np.ndarray, np.ndarray]:
    n = 2**z
    px = (x + tx / extent) / n
    py = (y + ty / extent) / n
    return px * 360.0 - 180.0, np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * py))))


# ---- terrarium ------------------------------------------------------------------------------


def terrarium_png(elev: np.ndarray) -> bytes:
    v = np.clip(elev.astype(np.float64) + 32768.0, 0, 65535.99)
    r = np.floor(v / 256)
    g = np.floor(v - r * 256)
    b = np.floor((v - np.floor(v)) * 256)
    img = np.stack([r, g, b], axis=-1).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(img, "RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def write_pmtiles(path: Path, tiles: dict[tuple[int, int, int], bytes], bbox: tuple[float, float, float, float],
                  tile_type: TileType, compression: Compression, metadata: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        w = Writer(f)
        for (z, x, y) in sorted(tiles, key=lambda k: zxy_to_tileid(*k)):
            w.write_tile(zxy_to_tileid(z, x, y), tiles[(z, x, y)])
        zs = [k[0] for k in tiles]
        w.finalize(
            {
                "tile_type": tile_type, "tile_compression": compression,
                "min_lon_e7": int(bbox[0] * 1e7), "min_lat_e7": int(bbox[1] * 1e7),
                "max_lon_e7": int(bbox[2] * 1e7), "max_lat_e7": int(bbox[3] * 1e7),
                "center_zoom": max(zs) - 2,
                "center_lon_e7": int((bbox[0] + bbox[2]) / 2 * 1e7),
                "center_lat_e7": int((bbox[1] + bbox[3]) / 2 * 1e7),
            },
            metadata,
        )


def build_dem_tiles(sample: Callable[[np.ndarray, np.ndarray], np.ndarray], bbox: tuple[float, float, float, float],
                    zooms: range) -> dict[tuple[int, int, int], bytes]:
    tiles = {}
    for z in zooms:
        for x, y in tiles_for_bbox(bbox, z):
            lon, lat = tile_pixel_lonlat(z, x, y)
            tiles[(z, x, y)] = terrarium_png(sample(lon, lat))
    return tiles


# ---- minimal Mapbox Vector Tile decoder ------------------------------------------------------


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def _fields(buf: bytes) -> Iterator[tuple[int, int, object]]:
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(buf, i)
            yield num, wt, v
        elif wt == 2:
            ln, i = _varint(buf, i)
            yield num, wt, buf[i : i + ln]
            i += ln
        elif wt == 1:
            yield num, wt, buf[i : i + 8]
            i += 8
        elif wt == 5:
            yield num, wt, buf[i : i + 4]
            i += 4
        else:
            raise ValueError(f"wire type {wt}")


def _packed(b: bytes) -> list[int]:
    out, i = [], 0
    while i < len(b):
        v, i = _varint(b, i)
        out.append(v)
    return out


def _value(b: bytes) -> object:
    for num, _wt, v in _fields(b):
        if num == 1:
            return bytes(v).decode()  # type: ignore[arg-type]
        if num in (4, 5):
            return v
        if num == 7:
            return bool(v)
    return None


def _geometry(cmds: list[int]) -> list[list[tuple[int, int]]]:
    """Decode to a list of parts (rings or line strings) in tile coordinates."""
    parts: list[list[tuple[int, int]]] = []
    x = y = 0
    i = 0
    cur: list[tuple[int, int]] = []
    while i < len(cmds):
        cmd, count = cmds[i] & 7, cmds[i] >> 3
        i += 1
        if cmd in (1, 2):
            for _ in range(count):
                dx, dy = cmds[i], cmds[i + 1]
                i += 2
                x += (dx >> 1) ^ -(dx & 1)
                y += (dy >> 1) ^ -(dy & 1)
                if cmd == 1:
                    if cur:
                        parts.append(cur)
                    cur = [(x, y)]
                else:
                    cur.append((x, y))
        elif cmd == 7 and cur:
            cur.append(cur[0])
    if cur:
        parts.append(cur)
    return parts


def decode_mvt(data: bytes) -> dict[str, tuple[int, list[tuple[int, dict[str, object], list[list[tuple[int, int]]]]]]]:
    """{layer: (extent, [(geom_type, props, parts), ...])}. geom_type: 1 point, 2 line, 3 polygon."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    layers = {}
    for num, _wt, lbuf in _fields(data):
        if num != 3:
            continue
        name, extent, keys, values, feats = "", 4096, [], [], []
        raw_feats = []
        for n, _w, v in _fields(lbuf):  # type: ignore[arg-type]
            if n == 1:
                name = bytes(v).decode()  # type: ignore[arg-type]
            elif n == 2:
                raw_feats.append(v)
            elif n == 3:
                keys.append(bytes(v).decode())  # type: ignore[arg-type]
            elif n == 4:
                values.append(_value(v))  # type: ignore[arg-type]
            elif n == 5:
                extent = int(v)  # type: ignore[call-overload]
        for fb in raw_feats:
            gtype, tags, geom = 0, [], []
            for n, _w, v in _fields(fb):
                if n == 2:
                    tags = _packed(v)  # type: ignore[arg-type]
                elif n == 3:
                    gtype = int(v)  # type: ignore[call-overload]
                elif n == 4:
                    geom = _packed(v)  # type: ignore[arg-type]
            props = {keys[tags[k]]: values[tags[k + 1]] for k in range(0, len(tags), 2)}
            feats.append((gtype, props, _geometry(geom)))
        layers[name] = (extent, feats)
    return layers
