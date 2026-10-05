"""K-02: DS start/pause/speed controls, DS hello fields, and the after-action review endpoint."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from kohra.app import create_app
from kohra.rooms import Room, Runner
from kohra.sim.step import StepResult

from tests.conftest import RIDGE


def test_ds_feed_flags_orders_citing_a_planted_report(ridge, flat_ridge_world) -> None:  # type: ignore[no-untyped-def]
    room = Room(Runner(ridge[0], ridge[1], world=flat_ridge_world), None, "vector")
    room.collect(StepResult(5, [("inject_fired", {"kind": "planted_report", "msg": "M-PLNT", "args": {}})]))
    room.collect(StepResult(9, [("order_applied", {"msg": "M-ORDR", "kind": "FIRE_MISSION", "to": "ANVIL",
                                                   "relied_on": ["M-PLNT", "M-REAL"], "confidence": 75})]))
    order = room.ds_events[-1]
    assert order["kind"] == "order_applied" and order["detail"]["planted_refs"] == ["M-PLNT"]


def _app(tmp_path: Path, **kw: Any) -> FastAPI:
    return create_app(str(RIDGE), log_path=str(tmp_path / "run.sqlite"), tokens_path=tmp_path / "tokens.json",
                      quiet=True, **kw)


def _wait(cond: Any, timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    while not cond() and time.time() < end:
        time.sleep(0.05)
    return bool(cond())


def test_start_pause_and_speed(terrain_available, tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = _app(tmp_path, speed=40.0, start_paused=True)
    tok, room = app.state.tokens, app.state.room
    ds = {"Authorization": f"Bearer {tok.ds}"}
    with TestClient(app) as c:
        assert c.post("/api/ds/control", json={"paused": False}).status_code == 403
        assert c.post("/api/ds/control", json={"paused": False},
                      headers={"Authorization": f"Bearer {tok.player}"}).status_code == 403
        time.sleep(0.3)
        assert room.runner.state.tick == 0, "the clock must hold until the DS starts the exercise"
        assert c.post("/api/ds/control", json={"paused": False}, headers=ds).json()["paused"] is False
        assert _wait(lambda: room.runner.state.tick > 5, 10)
        assert c.post("/api/ds/control", json={"paused": True}, headers=ds).json()["paused"] is True
        time.sleep(0.15)
        held = room.runner.state.tick
        time.sleep(0.4)
        assert room.runner.state.tick == held
        assert c.post("/api/ds/control", json={"speed": 99}, headers=ds).status_code == 422
        assert c.post("/api/ds/control", json={"speed": 8}, headers=ds).json()["speed"] == 8
        with c.websocket_connect(f"/ws/ds?t={tok.ds}") as ws:
            hello = ws.receive_json()
            assert {n["id"] for n in hello["nets"]} == {"COY", "BN"} and hello["player"] == "TIGER"
            assert "TAMARIND" in {p["id"] for p in hello["place_ids"]}
            assert {"callsign": "ANVIL", "nets": ["BN"]} in hello["stations"]
            state = ws.receive_json()
            assert state["paused"] is True and state["speed"] == 8


def test_aar_endpoint_only_for_ds_after_endex(terrain_available, tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = _app(tmp_path, speed=None, ticks=40, start_paused=True)
    tok, room = app.state.tokens, app.state.room
    with TestClient(app) as c:
        assert c.get("/api/ds/aar", params={"t": tok.player}).status_code == 403
        assert c.get("/api/ds/aar", params={"t": tok.ds}).status_code == 409
        c.post("/api/ds/control", json={"paused": False}, headers={"Authorization": f"Bearer {tok.ds}"})
        assert _wait(lambda: room.endex)
        r = c.get("/api/ds/aar", params={"t": tok.ds})
        assert r.status_code == 200 and "After-action review" in r.text and "hash chain intact" in r.text
