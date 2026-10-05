"""One-command KOHRA M1 demo (Windows and Linux).

    uv run python scripts/demo.py [--speed 1|2|4] [--no-browser]
    uv run python scripts/demo.py --headless --speed max

Interactive: ensures terrain and the client build, starts the server (PYTHONHASHSEED=0), opens the player
page, prints the DS URL, schedules scenarios/demo_injects.yaml through the inject CLI, and at ENDEX prints
the final hash and replays the run log (REPLAY OK <hash>).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
SCEN = ROOT / "scenarios" / "ridge.yaml"
BOT = ROOT / "scenarios" / "ridge.bot.yaml"
INJECTS = ROOT / "scenarios" / "demo_injects.yaml"


def env() -> dict[str, str]:
    return {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(ROOT / "server"), "PYTHONUNBUFFERED": "1"}


def run(cmd: list[str], cwd: Path = ROOT) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, env=env()).returncode


def check_tools(need_node: bool) -> None:
    if sys.version_info[:2] != (3, 12):
        print(f"WARNING: Python 3.12 expected, running {sys.version.split()[0]}")
    if need_node:
        node = shutil.which("node")
        if not node:
            sys.exit("Node.js 20+ is needed to build the client (https://nodejs.org).")
        ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        if int(ver.lstrip("v").split(".")[0]) < 20:
            sys.exit(f"Node.js 20+ needed, found {ver}")
    if not (ROOT / ".venv").exists() and shutil.which("uv"):
        run(["uv", "sync", "--extra", "terrain"])


def ensure_terrain(interactive: bool) -> None:
    if (ROOT / "data" / "terrain" / "terrain.npz").exists():
        return
    raw = ROOT / "data" / "raw" / "MANIFEST.json"
    if raw.exists() and not json.loads(raw.read_text(encoding="utf-8")).get("synthetic"):
        if run([PY, "scripts/build_terrain.py"]) == 0:
            return
    want = True
    if interactive:
        want = input("No terrain yet. Download real DEM + OSM basemap (~50 MB)? [Y/n] ").strip().lower() in ("", "y", "yes")
    if want and run([PY, "scripts/fetch_terrain.py"]) == 0 and run([PY, "scripts/build_terrain.py"]) == 0:
        return
    print("Falling back to SYNTHETIC terrain (the client will show a banner).")
    if run([PY, "scripts/synth_terrain.py"]) != 0:
        sys.exit("terrain generation failed")


def ensure_client() -> None:
    if (ROOT / "client" / "dist" / "index.html").exists():
        return
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm not found")
    if run([npm, "ci", "--no-fund", "--no-audit"], ROOT / "client") != 0:
        sys.exit("npm ci failed")
    if run([npm, "run", "build"], ROOT / "client") != 0:
        sys.exit("client build failed")


def headless(speed: str) -> int:
    log = ROOT / "runs" / f"demo-headless-{dt.datetime.now():%Y%m%d-%H%M%S}.sqlite"
    if speed != "max":
        print("headless runs as fast as possible; --speed ignored")
    return run([PY, "-m", "kohra.cli", "headless", "--scenario", str(SCEN), "--bot", str(BOT), "--injects",
                str(INJECTS), "--log", str(log), "--replay"])


def interactive(speed: str, port: int, browser: bool) -> int:
    log = ROOT / "runs" / f"demo-{dt.datetime.now():%Y%m%d-%H%M%S}.sqlite"
    cmd = [PY, "-u", "-m", "kohra.cli", "run", "--scenario", str(SCEN), "--speed", speed, "--port", str(port),
           "--log", str(log), "--replay"]
    print("$", " ".join(cmd), flush=True)
    srv = subprocess.Popen(cmd, cwd=ROOT, env=env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert srv.stdout is not None
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"{url}/api/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.5)
        else:
            sys.exit("server did not start")
        tokens = json.loads((ROOT / ".kohra" / "tokens.json").read_text(encoding="utf-8"))
        play, ds = f"{url}/play?t={tokens['player']}", f"{url}/ds?t={tokens['ds']}"
        print(f"\nPLAYER: {play}\nDS (truth view): {ds}\n", flush=True)
        if browser:
            webbrowser.open(play)
        run([PY, "-m", "kohra.cli", "inject-file", str(INJECTS), "--url", url])
        code = 1
        for line in srv.stdout:
            print(line, end="", flush=True)
            if line.startswith("REPLAY OK"):
                code = 0
                break
            if line.startswith("REPLAY MISMATCH"):
                break
        return code
    except KeyboardInterrupt:
        return 130
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--speed", default="1", help="1..4, or max (headless)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    check_tools(need_node=not a.headless)
    ensure_terrain(interactive=not a.headless and sys.stdin.isatty())
    if a.headless:
        sys.exit(headless(a.speed))
    ensure_client()
    sys.exit(interactive(a.speed, a.port, not a.no_browser))


if __name__ == "__main__":
    main()
