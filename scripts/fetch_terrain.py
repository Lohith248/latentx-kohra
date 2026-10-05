"""One-time download of the DEM tile, the OSM basemap extract and the pmtiles CLI.

Run time never touches the network; only this script does.

    uv run python scripts/fetch_terrain.py [--bbox 76.10,11.20,76.30,11.35]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
TILES = ROOT / "data" / "tiles"
TOOLS = ROOT / ".tools"

DEM_NAME = "Copernicus_DSM_COG_10_N11_00_E076_00_DEM"
DEM_URL = f"https://copernicus-dem-30m.s3.amazonaws.com/{DEM_NAME}/{DEM_NAME}.tif"

PMTILES_VERSION = "1.31.2"
PMTILES_ASSETS = {  # sha256 from the GitHub release metadata of protomaps/go-pmtiles v1.31.2
    ("Windows", "x86_64"): ("go-pmtiles_1.31.2_Windows_x86_64.zip",
                            "a658baa4d7e55020aef6ca17bd9ff9faa1582671266b36f58c52db0ac8e785a1"),
    ("Windows", "arm64"): ("go-pmtiles_1.31.2_Windows_arm64.zip",
                           "8780a17453c63af757917a694cbbb50b943db89cc3f1b07e6fd62c1ff8e6963b"),
    ("Linux", "x86_64"): ("go-pmtiles_1.31.2_Linux_x86_64.tar.gz",
                          "3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f"),
    ("Linux", "arm64"): ("go-pmtiles_1.31.2_Linux_arm64.tar.gz",
                         "f8bd47e7ea866863489cad588fbaf2f31f42e5821f7a03f009b3769f05801cb1"),
    ("Darwin", "x86_64"): ("go-pmtiles-1.31.2_Darwin_x86_64.zip",
                           "1f0dc02eee6c58312dd6c509faee1b5c32f0596568af1bf51f1b034e7a88a65b"),
    ("Darwin", "arm64"): ("go-pmtiles-1.31.2_Darwin_arm64.zip",
                          "40528f7f616fcbf91207cd48c8fc023d213f6d86c0cbf1f748732803d1880f3d"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    print(f"GET {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def pmtiles_cli() -> Path:
    on_path = shutil.which("pmtiles")
    if on_path:
        return Path(on_path)
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    name, digest = PMTILES_ASSETS[(platform.system(), arch)]
    exe = TOOLS / ("pmtiles.exe" if os.name == "nt" else "pmtiles")
    if exe.exists():
        return exe
    TOOLS.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/protomaps/go-pmtiles/releases/download/v{PMTILES_VERSION}/{name}"
    print(f"GET {url}")
    blob = urllib.request.urlopen(url, timeout=120).read()
    got = hashlib.sha256(blob).hexdigest()
    if got != digest:
        sys.exit(f"pmtiles checksum mismatch: {got} != {digest}")
    member = exe.name
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            exe.write_bytes(z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(blob)) as t:
            f = t.extractfile(member)
            assert f is not None
            exe.write_bytes(f.read())
    exe.chmod(0o755)
    return exe


def protomaps_sources() -> list[str]:
    env = os.environ.get("KOHRA_PMTILES_SOURCE")
    if env:
        return [env]
    today = dt.date.today()
    return [f"https://build.protomaps.com/{(today - dt.timedelta(days=i)):%Y%m%d}.pmtiles" for i in range(8)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", default="76.10,11.20,76.30,11.35")
    ap.add_argument("--maxzoom", type=int, default=15)
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    TILES.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"synthetic": False, "fetched": dt.datetime.now(dt.UTC).isoformat(), "files": {}}
    files: dict[str, dict[str, str]] = {}

    dem = RAW / f"{DEM_NAME}.tif"
    if not dem.exists():
        download(DEM_URL, dem)
    files["dem"] = {"url": DEM_URL, "path": str(dem.relative_to(ROOT)), "sha256": sha256(dem)}

    cli = pmtiles_cli()
    out = TILES / "basemap.pmtiles"
    used = None
    for src in protomaps_sources():
        print(f"pmtiles extract {src}")
        r = subprocess.run([str(cli), "extract", src, str(out), f"--bbox={args.bbox}", f"--maxzoom={args.maxzoom}"],
                           capture_output=True, text=True)
        if r.returncode == 0 and out.exists():
            used = src
            break
        print(r.stderr.strip()[-400:])
    if used is None:
        sys.exit("could not extract a basemap from any Protomaps build; set KOHRA_PMTILES_SOURCE or use synth_terrain.py")
    files["basemap"] = {"url": used, "path": str(out.relative_to(ROOT)), "sha256": sha256(out)}
    files["pmtiles_cli"] = {"version": PMTILES_VERSION, "path": str(cli)}
    manifest["files"] = files
    manifest["bbox"] = [float(v) for v in args.bbox.split(",")]
    (RAW / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("wrote", RAW / "MANIFEST.json")


if __name__ == "__main__":
    main()
