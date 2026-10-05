"""KOHRA command line: run, headless, inject, inject-file, replay, verify-chain, aar.

    python -m kohra.cli run --scenario scenarios/ridge.yaml --speed 1 [--host 0.0.0.0] [--port 8765] [--start-paused]
    python -m kohra.cli headless --scenario scenarios/ridge.yaml --bot scenarios/ridge.bot.yaml \
        --injects scenarios/demo_injects.yaml --ticks 1800 --log runs/x.sqlite
    python -m kohra.cli inject jammer_add id=J-1 lonlat=76.15,11.22 power_dbm=47 antenna_m=6 \
        freq_mhz=45.25 bandwidth_khz=25 mode=continuous
    python -m kohra.cli inject-file scenarios/demo_injects.yaml
    python -m kohra.cli replay runs/x.sqlite
    python -m kohra.cli verify-chain runs/x.sqlite
    python -m kohra.cli aar runs/x.sqlite [-o runs/x.aar.html]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from kohra.scenario.load import REPO_ROOT, load_bot, load_injects, load_scenario
from kohra.scenario.schema import INJECT_ARGS, Inject

TOKENS = REPO_ROOT / ".kohra" / "tokens.json"


def default_log_path(tag: str) -> Path:
    return REPO_ROOT / "runs" / f"{tag}-{dt.datetime.now():%Y%m%d-%H%M%S}.sqlite"


def warn_hashseed() -> None:
    if os.environ.get("PYTHONHASHSEED") != "0":
        print("WARNING: PYTHONHASHSEED is not 0; set it for reproducible runs (D8).", file=sys.stderr)


def cmd_headless(a: argparse.Namespace) -> int:
    from kohra.rooms import Bot, Runner

    warn_hashseed()
    scen, text = load_scenario(a.scenario)
    log = Path(a.log) if a.log else default_log_path("headless")
    runner = Runner(scen, text, seed=a.seed, log_path=log, end_tick=a.ticks)
    for inj in load_injects(a.injects) if a.injects else []:
        runner.schedule_inject(inj, source="ds", source_id="file")
    bot = Bot(load_bot(a.bot)) if a.bot else None
    final = runner.run_to_end(bot)
    out = {"ticks": runner.state.tick, "seed": runner.scenario.seed, "final_hash": final, "log": str(log),
           "tick_ms_median": round(statistics.median(runner.step_ms), 3),
           "tick_ms_p95": round(sorted(runner.step_ms)[int(len(runner.step_ms) * 0.95)], 3),
           "hashes": runner.hashes if a.json else len(runner.hashes)}
    if a.json:
        print(json.dumps(out))
    else:
        for k, v in out.items():
            print(f"{k}: {v}")
    if a.replay:
        return cmd_replay(argparse.Namespace(log=str(log)))
    return 0


def cmd_replay(a: argparse.Namespace) -> int:
    from kohra.log.replay import replay

    r = replay(a.log)
    if r.ok:
        print(f"REPLAY OK {r.final_hash}")
        return 0
    print(f"REPLAY MISMATCH at tick {r.first_mismatch_tick}")
    return 1


def cmd_verify(a: argparse.Namespace) -> int:
    from kohra.log.chain import verify_chain

    ok, bad, n = verify_chain(a.log)
    print(f"CHAIN OK ({n} rows)" if ok else f"CHAIN BROKEN at seq {bad}")
    return 0 if ok else 1


def cmd_aar(a: argparse.Namespace) -> int:
    from kohra.reports.aar import build_aar

    out = Path(a.out) if a.out else Path(a.log).with_suffix(".aar.html")
    out.write_text(build_aar(a.log, verify=not a.no_verify), encoding="utf-8")
    print(f"AAR {out}")
    return 0


def parse_kv(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in pairs:
        k, _, v = p.partition("=")
        if not _:
            raise SystemExit(f"expected key=value, got {p!r}")
        if "," in v and not v.lstrip().startswith(("[", "{")):
            v = f"[{v}]"
        val = yaml.safe_load(v)
        if k in ("fields", "ge") and isinstance(val, str):
            val = yaml.safe_load(val)
        out[k] = val
    return out


def post_inject(body: dict[str, Any], url: str) -> dict[str, Any]:
    tok = json.loads(TOKENS.read_text(encoding="utf-8"))["ds"]
    req = urllib.request.Request(url.rstrip("/") + "/api/ds/inject", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return dict(json.loads(r.read()))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"inject refused: {e.code} {e.read().decode()[:300]}") from e


def server_url() -> str:
    try:
        return str(json.loads(TOKENS.read_text(encoding="utf-8")).get("url", "http://127.0.0.1:8765"))
    except FileNotFoundError as e:
        raise SystemExit("no .kohra/tokens.json: start the server first (python -m kohra.cli run)") from e


def cmd_inject(a: argparse.Namespace) -> int:
    if a.kind not in INJECT_ARGS:
        raise SystemExit(f"unknown inject kind {a.kind}; one of {sorted(INJECT_ARGS)}")
    args = parse_kv(a.args)
    at = args.pop("at_tick", None)
    inj = Inject.model_validate({"kind": a.kind, "args": args, "at_tick": at})
    print(json.dumps(post_inject(inj.model_dump(), a.url or server_url())))
    return 0


def cmd_inject_file(a: argparse.Namespace) -> int:
    url = a.url or server_url()
    for inj in load_injects(a.file):
        print(json.dumps(post_inject(inj.model_dump(), url)))
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    import uvicorn

    from kohra.app import create_app

    warn_hashseed()
    speed = None if a.speed == "max" else float(a.speed)
    app = create_app(a.scenario, speed=speed, host=a.host, port=a.port, log_path=a.log,
                     bot=a.bot, injects=a.injects, seed=a.seed, ticks=a.ticks, replay_at_endex=a.replay,
                     tokens_path=Path(a.tokens) if a.tokens else TOKENS, start_paused=a.start_paused)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kohra")
    sub = ap.add_subparsers(dest="cmd", required=True)
    default_scen = str(REPO_ROOT / "scenarios" / "ridge.yaml")

    r = sub.add_parser("run", help="serve the exercise")
    r.add_argument("--scenario", default=default_scen)
    r.add_argument("--speed", default="1", help="1..4 or max")
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=8765)
    r.add_argument("--log")
    r.add_argument("--bot")
    r.add_argument("--injects")
    r.add_argument("--seed", type=int)
    r.add_argument("--ticks", type=int)
    r.add_argument("--replay", action="store_true", help="replay the log at ENDEX and print REPLAY OK")
    r.add_argument("--tokens", help="where to write the run-time tokens (default .kohra/tokens.json)")
    r.add_argument("--start-paused", action="store_true", help="hold the clock at 06:00 until the DS presses Start")
    r.set_defaults(func=cmd_run)

    h = sub.add_parser("headless", help="run as fast as possible without a browser")
    h.add_argument("--scenario", default=default_scen)
    h.add_argument("--bot")
    h.add_argument("--injects")
    h.add_argument("--ticks", type=int)
    h.add_argument("--seed", type=int)
    h.add_argument("--log")
    h.add_argument("--json", action="store_true")
    h.add_argument("--replay", action="store_true")
    h.set_defaults(func=cmd_headless)

    i = sub.add_parser("inject", help="send one inject to the running server")
    i.add_argument("kind")
    i.add_argument("args", nargs="*", help="key=value (lists as a,b; at_tick=N to schedule)")
    i.add_argument("--url")
    i.set_defaults(func=cmd_inject)

    f = sub.add_parser("inject-file", help="send every inject in a YAML file (ticks are absolute)")
    f.add_argument("file")
    f.add_argument("--url")
    f.set_defaults(func=cmd_inject_file)

    rp = sub.add_parser("replay")
    rp.add_argument("log")
    rp.set_defaults(func=cmd_replay)

    v = sub.add_parser("verify-chain")
    v.add_argument("log")
    v.set_defaults(func=cmd_verify)

    aa = sub.add_parser("aar", help="write the after-action review for a run log")
    aa.add_argument("log")
    aa.add_argument("-o", "--out", help="output HTML (default: next to the log, .aar.html)")
    aa.add_argument("--no-verify", action="store_true", help="skip the chain check and replay")
    aa.set_defaults(func=cmd_aar)

    a = ap.parse_args(argv)
    return int(a.func(a))


if __name__ == "__main__":
    sys.exit(main())
