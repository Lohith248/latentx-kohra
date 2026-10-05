# KOHRA: M1 "solo slice"

Team LatentX (IIIT Bangalore), Smart India Hackathon 2026, problem statement SIH26248 (Ministry of Defence,
DSSC): train small-team commanders to decide under deliberately incomplete, delayed and contradictory
information.

**ILLUSTRATIVE · UNCLASSIFIED · FICTIONAL NAMES.** Not a validated RF model.

## What M1 is

One person plays a 12-minute vignette (RIDGE, Ford OSPREY) in a browser, as company commander TIGER, with
scripted platoons (TIGER-1/2/3), a scripted battalion HQ (ANVIL) and a scripted enemy.

- **Truth.** A seeded, deterministic simulation (`step(state, commands, rng, world)`, 1 tick = 1 s)
  runs on real terrain: Copernicus GLO-30 plus OpenStreetMap, in a box in peninsular India. All
  place names are fictional codenames.
- **Sensing.** Platoon sensors detect the enemy imperfectly. Detections become templated text reports
  (CONTACT, LOCSTAT, SITREP, …) graded A–F × 1–6.
- **Comms.** Reports and orders travel over simulated VHF nets: terrain-aware path loss with
  knife-edge diffraction, jammers, SINR, delivery odds, partial (garbled) messages and a
  precedence queue.
- **The player sees only what arrives.** Contacts come from received reports, with age and grade. Own
  platoons appear only from their LOCSTATs. "Last heard" timers run per station. Every order needs a
  confidence (0–100) and the reports it relied on, which are logged and never transmitted.
- **Instructor.** A command-line inject drops or moves a jammer, cuts or delays a net, plants a false
  report, or adds a GNSS-spoofing zone. A read-only truth view at `/ds` shows the truth, the jammers and
  the link SINR.
- **Replay.** Every command goes into a hash-chained SQLite log. Replaying it reproduces the same state
  hashes, including the final one.

Out of scope for M1: voice, multiplayer, AAR, scoring, any LLM, 3D.

## Prerequisites

- Python 3.12 via [uv](https://docs.astral.sh/uv/) (uv installs 3.12 for you).
- Node.js 20 LTS or newer, to build the client.
- About 50 MB of downloads for real terrain (one time), or none with synthetic terrain.

Windows (PowerShell):

```powershell
py -3.12 -m pip install uv        # or: winget install astral-sh.uv
uv sync --extra terrain
cd client; npm ci; npm run build; cd ..
```

Linux:

```bash
pipx install uv                    # or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --extra terrain
(cd client && npm ci && npm run build)
```

`requirements.lock` is a hashed export of `uv.lock` for pip users:
`pip install -r requirements.lock`, then run everything with `PYTHONPATH=server`.

## Terrain (fetch once; nothing touches the network at run time)

```bash
uv run python scripts/fetch_terrain.py     # GLO-30 tile, Protomaps extract, pinned pmtiles CLI (SHA-256 checked)
uv run python scripts/build_terrain.py     # terrain.npz + dem.pmtiles (~5 s) + elevation cross-check
uv run python scripts/check_scenario.py    # verifies every scenario intent on the built terrain
```

Windows: the same commands with `scripts\...`. The Protomaps source defaults to the newest daily build in
the last 8 days; override it with `KOHRA_PMTILES_SOURCE=<url or path>`.

**Synthetic fallback.** If downloads are blocked, `uv run python scripts/synth_terrain.py` writes the
same files from seeded noise, with a river and ford at OSPREY, a ridge at KESTREL, a hill at HERON and a
road along BLUEJAY. The client then shows a red **SYNTHETIC TERRAIN** banner. CI always uses synthetic.

`data/` and `.tools/` are gitignored; never commit tiles, the DEM or binaries.

**DEM caveat.** GLO-30 is a surface model: tree canopy and buildings are part of the "ground", so line
of sight and diffraction see them.

### Elevation cross-check (K-01)

`build_terrain.py` compares `terrain.npz` with the source GeoTIFF at the five scenario places, each
snapped to the nearest 30 m cell centre (results in `data/terrain/elevation_check.json`):

| Place | lon, lat (cell centre) | terrain.npz | source, bilinear | diff | source, nearest pixel |
| --- | --- | --- | --- | --- | --- |
| OSPREY | 76.148435, 11.239218 | 4.95 | 5.14 | −0.19 | 4.50 |
| KESTREL | 76.153765, 11.266595 | 297.18 | 297.22 | −0.04 | 296.11 |
| HERON | 76.152482, 11.220485 | 204.93 | 204.65 | +0.28 | 203.67 |
| TAMARIND | 76.140092, 11.214022 | 21.53 | 21.61 | −0.08 | 19.63 |
| JUNIPER | 76.158535, 11.291262 | 71.25 | 71.57 | −0.32 | 73.02 |

All five are within 0.35 m of bilinear source sampling. Over 3,000
random points the mean difference is −0.03 m and the mean |difference| is 0.45 m; offsetting the grid
by ±15 m makes it worse, so registration is correct. Nearest-pixel values differ by up to 1.9 m on
slopes and built-up cells because the UTM 30 m grid and the 1″ source grid are different grids (see
DEVIATIONS.md).

## Run the demo

```bash
uv run python scripts/demo.py               # Windows: uv run python scripts\demo.py
uv run python scripts/demo.py --speed 4     # 1x to 4x wall-clock
uv run python scripts/demo.py --headless --speed max   # bot player, prints tick timing, final hash, REPLAY OK
```

The demo checks the tools, makes sure terrain and the client build exist, starts the server with
`PYTHONHASHSEED=0`, opens the player page, prints the DS truth-view URL, and schedules
`scenarios/demo_injects.yaml` through the inject CLI:

- 06:04:00: jammer among the company (the COY net goes dark);
- 06:05:30: a planted INTSUM graded C3 (a tank platoon at TAMARIND);
- 06:08:00: the jammer moves behind KESTREL (the net recovers).

At ENDEX (06:12:00) inputs lock, the final hash shows in the browser, and the demo replays the log and
prints `REPLAY OK <hash>`.

Server only: `uv run python -m kohra.cli run --speed 1 [--host 0.0.0.0] [--port 8765]`. It prints a
fresh player URL (`/play?t=…`) and DS URL (`/ds?t=…`) and writes the tokens to the gitignored
`.kohra/tokens.json`. It binds 127.0.0.1 unless you pass `--host 0.0.0.0` for LAN use.

## Run as an instructor (inject CLI)

With the server running, from the repo root (the CLI reads the DS token from `.kohra/tokens.json`).
Lists are `a,b`; mappings are YAML; `at_tick=N` schedules an inject at an absolute tick, and one whose
tick has passed fires now, logged `late: true`.

```bash
python -m kohra.cli inject jammer_add id=J-1 lonlat=76.1467,11.2213 power_dbm=47 antenna_m=6 freq_mhz=45.25 bandwidth_khz=25 mode=continuous
python -m kohra.cli inject jammer_add id=J-2 lonlat=76.15,11.22 power_dbm=40 antenna_m=4 freq_mhz=45.25 bandwidth_khz=25 mode=intermittent "ge={p: 0.05, r: 0.2}" duration_s=300
python -m kohra.cli inject jammer_move id=J-1 lonlat=76.150,11.275
python -m kohra.cli inject jammer_remove id=J-1
python -m kohra.cli inject net_cut net=COY duration_s=60
python -m kohra.cli inject net_delay net=BN extra_s=20 duration_s=120
python -m kohra.cli inject planted_report net=BN from_callsign=ANVIL to_callsign=TIGER template=intsum "fields={size: platoon, unit_type: tank, grid_from_place: TAMARIND, direction: SW, time: auto}" grade=C3 precedence=IMMEDIATE
python -m kohra.cli inject gnss_zone_add id=G-1 lonlat=76.137,11.209 radius_m=800 bearing_deg=45 rate_mps=2 max_offset_m=400 duration_s=300
python -m kohra.cli inject-file scenarios/demo_injects.yaml
```

Prefix each with `uv run` (Windows and Linux alike). Each call POSTs to `/api/ds/inject` with the DS
token; a player token is refused.

Logs: `python -m kohra.cli replay runs/<log>.sqlite` prints `REPLAY OK <hash>` or the first mismatching
tick. `python -m kohra.cli verify-chain runs/<log>.sqlite` checks the SHA-256 chain.

## Run the tests

```bash
uv run pytest -q
uv run mypy --strict -p kohra.sim -p kohra.comms -p kohra.reports -p kohra.observe -p kohra.log
uv run ruff check .
cd client && npm test && npm run build && npx playwright install chromium && npx playwright test
```

The Python tests need a built `data/terrain/terrain.npz` (real or synthetic). Playwright starts its own
server on port 8799.

## Determinism (D8)

- Identical hashes are promised on **the same build and the same platform** only, not across platforms.
- Every launcher sets `PYTHONHASHSEED=0`, and the server warns if it is unset.
- Randomness comes only from nine named PCG64 streams (`move, detect, reports, comms, burst, outcome,
  gnss, ids, scripts`), with stream *i* = `PCG64(SeedSequence(seed, spawn_key=(i,)))`. NumPy is pinned
  (2.2.5).
- The state hash is SHA-256 of canonical JSON (sorted keys, `repr` floats, RNG bit-generator states),
  taken every 60 ticks and at the end.
- Commands are applied at `apply_tick`, in order `(apply_tick, source_rank, source_id, client_seq)`.
  Replay uses the logged `apply_tick` and never the wall clock.
- No set iteration and no unordered dict order anywhere in the sim. The link cache snaps positions to
  30 m cells, so a cache hit and a miss give identical values.

## Layout

```
server/kohra/   app.py rooms.py views.py wire.py auth.py cli.py
                scenario/ sim/ comms/ reports/ observe/ log/
client/         React + Vite + MapLibre + PMTiles + milsymbol + zustand; e2e/ (Playwright)
scenarios/      ridge.yaml ridge.bot.yaml demo_injects.yaml scenario.schema.json
config/         grading.yaml
scripts/        fetch_terrain.py build_terrain.py synth_terrain.py check_scenario.py demo.py tilekit.py
tests/          pytest suite; fixtures/ has synthetic DEMs built in memory
```

`views.view_for()` is the only path from simulation state to a player socket. Truth IDs, SINR, jammer
positions and planted flags never leave the server on `/ws/play`; `tests/test_no_truth_leak.py`
enforces this with canaries.

## Data credits

- © OpenStreetMap contributors (ODbL)
- Basemap: Protomaps
- Contains modified Copernicus DEM GLO-30 data, © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH
  2014–2018, provided under COPERNICUS by the European Union and ESA
- MapLibre GL JS, milsymbol

Software licences are listed in [THIRD_PARTY.md](THIRD_PARTY.md); departures from the brief are in
[DEVIATIONS.md](DEVIATIONS.md).

## Limits

- Illustrative and unclassified, with fictional names. Not a validated RF or combat model.
- Path loss is max(free-space, plane-earth) plus single knife-edge diffraction over a DSM. No
  clutter model, no ground constants, no antenna patterns. The optional ITM cross-check was not run.
- Replay identity holds on the same build and platform only.
- Windows steps were developed and tested on Windows 11. The Linux steps are exercised by CI
  (ubuntu-24.04).
