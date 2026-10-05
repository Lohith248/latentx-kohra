"""K-02: headless run with bot + injects replays to identical hashes; cross-process identity; chain."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from kohra.log.chain import verify_chain
from kohra.log.replay import replay
from kohra.rooms import Bot, Runner
from kohra.scenario.load import load_bot, load_injects

from tests.conftest import ALL_INJECTS, BOT, DEMO_INJECTS, RIDGE, ROOT

TICKS = 1800


def headless(ridge, log: Path, seed: int | None = None, ticks: int = TICKS) -> Runner:  # type: ignore[no-untyped-def]
    scen, text = ridge
    r = Runner(scen, text, seed=seed, log_path=log, end_tick=ticks)
    for inj in load_injects(DEMO_INJECTS) + load_injects(ALL_INJECTS)[:2]:
        r.schedule_inject(inj, source="ds", source_id="file")
    r.run_to_end(Bot(load_bot(BOT)))
    return r


@pytest.fixture(scope="module")
def run(ridge, terrain_available, tmp_path_factory):  # type: ignore[no-untyped-def]
    log = tmp_path_factory.mktemp("replay") / "run.sqlite"
    return headless(ridge, log), log


def test_replay_identical_hashes(run) -> None:  # type: ignore[no-untyped-def]
    r, log = run
    assert r.state.tick == TICKS
    assert [t for t, _ in r.hashes] == list(range(60, TICKS + 1, 60))
    res = replay(log)
    assert res.ok, f"mismatch at tick {res.first_mismatch_tick}"
    assert res.hashes == r.hashes
    assert res.final_hash == r.final_hash


def test_two_processes_same_seed(run, tmp_path) -> None:  # type: ignore[no-untyped-def]
    r, _ = run
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(ROOT / "server")}
    lists = []
    for i in range(2):
        out = subprocess.run(
            [sys.executable, "-m", "kohra.cli", "headless", "--scenario", str(RIDGE), "--bot", str(BOT),
             "--injects", str(DEMO_INJECTS), "--ticks", str(TICKS), "--log", str(tmp_path / f"p{i}.sqlite"), "--json"],
            capture_output=True, text=True, env=env, check=True, cwd=ROOT)
        lists.append(json.loads(out.stdout.strip().splitlines()[-1])["hashes"])
    assert lists[0] == lists[1]
    assert len(lists[0]) == TICKS // 60


def test_different_seed_differs(ridge, terrain_available, tmp_path) -> None:  # type: ignore[no-untyped-def]
    a = headless(ridge, tmp_path / "a.sqlite", seed=42, ticks=300)
    b = headless(ridge, tmp_path / "b.sqlite", seed=43, ticks=300)
    assert a.final_hash != b.final_hash


def test_chain_verifies_and_detects_one_byte_edit(run, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, log = run
    ok, bad, n = verify_chain(log)
    assert ok and bad is None and n > 100
    copy = tmp_path / "tampered.sqlite"
    copy.write_bytes(Path(log).read_bytes())
    con = sqlite3.connect(copy)
    seq, payload = con.execute("SELECT seq, payload FROM events WHERE kind='command' LIMIT 1").fetchone()
    i = payload.index('"apply_tick":') + len('"apply_tick":')
    edited = payload[:i] + ("9" if payload[i] != "9" else "8") + payload[i + 1 :]
    con.execute("UPDATE events SET payload=? WHERE seq=?", (edited, seq))
    con.commit()
    con.close()
    ok, bad, _ = verify_chain(copy)
    assert not ok and bad == seq
    env = {**os.environ, "PYTHONPATH": str(ROOT / "server")}
    cli = subprocess.run([sys.executable, "-m", "kohra.cli", "verify-chain", str(copy)], capture_output=True,
                         text=True, env=env, cwd=ROOT)
    assert cli.returncode == 1 and "BROKEN" in cli.stdout
