"""K-06: no truth-only field ever reaches a player socket (static model check + live capture)."""

from __future__ import annotations

import json
import secrets
from typing import Any, get_args, get_origin

import pytest
from fastapi.testclient import TestClient
from kohra.app import create_app
from kohra.reports.parse import parse
from kohra.wire import PLAYER_MODELS
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from tests.conftest import ALL_INJECTS, BOT, RIDGE

TRUTH_ONLY_KEYS = {"truth_id", "is_planted", "sinr_db", "sinr_min", "sinr_eff", "p_deliver", "link_state",
                   "gnss_offset", "red_plan", "strength", "detection_q", "q", "canary", "path", "owner", "x", "y",
                   "emitting", "delivered", "loss", "lost", "posture", "target", "rep_x", "rep_y"}
TRUTH_PREFIXES = ("true_", "jammer", "truth")


def is_truth_key(k: str) -> bool:
    return k in TRUTH_ONLY_KEYS or k.startswith(TRUTH_PREFIXES)


def _model_fields(model: type[BaseModel], seen: set[type]) -> list[str]:
    if model in seen:
        return []
    seen.add(model)
    names = []
    for name, f in model.model_fields.items():
        names.append(name)
        stack = [f.annotation]
        while stack:
            t = stack.pop()
            if isinstance(t, type) and issubclass(t, BaseModel):
                names += _model_fields(t, seen)
            elif get_origin(t) is not None:
                stack += list(get_args(t))
    return names


def test_static_player_models_have_no_truth_fields() -> None:
    for m in PLAYER_MODELS:
        bad = [n for n in _model_fields(m, set()) if is_truth_key(n)]
        assert not bad, f"{m.__name__}: {bad}"


def _keys(o: Any) -> list[str]:
    if isinstance(o, dict):
        return [str(k) for k in o] + [k for v in o.values() for k in _keys(v)]
    if isinstance(o, list):
        return [k for v in o for k in _keys(v)]
    return []


def _pairs(o: Any) -> list[tuple[float, float]]:
    if isinstance(o, list) and len(o) == 2 and all(isinstance(v, float) for v in o):
        return [(o[0], o[1])]
    if isinstance(o, dict):
        return [p for v in o.values() for p in _pairs(v)]
    if isinstance(o, list):
        return [p for v in o for p in _pairs(v)]
    return []


def _capture(seed: int, tmp_path) -> tuple[list[str], set[tuple[float, float]], set[str], dict[str, str]]:  # type: ignore[no-untyped-def]
    app = create_app(str(RIDGE), speed=240.0, log_path=str(tmp_path / f"leak{seed}.sqlite"), bot=str(BOT),
                     injects=str(ALL_INJECTS), seed=seed, ticks=720, tokens_path=tmp_path / "tokens.json", quiet=True)
    room = app.state.room
    state = room.runner.state
    canaries = {}
    for u in state.units.values():
        u.canary = "CANARY" + secrets.token_hex(6)
        canaries[u.id] = u.canary
    truth_ids = set(state.units) | set(state.jammers) | {"J-DS-1"}
    red_xy: set[tuple[float, float]] = set()
    orig = room.runner.advance

    def advance():  # type: ignore[no-untyped-def]
        res = orig()
        for u in state.units.values():
            if u.side == "red":
                red_xy.add(room.runner.world.to_lonlat(u.x, u.y))
        return res

    room.runner.advance = advance
    frames: list[str] = []
    tok = app.state.tokens
    with TestClient(app) as client, client.websocket_connect(f"/ws/play?t={tok.player}") as ws:
        while True:
            raw = ws.receive_text()
            frames.append(raw)
            f = json.loads(raw)
            if f["type"] == "status" and f["endex"]:
                break
    return frames, red_xy, truth_ids, canaries


@pytest.mark.parametrize("seed", [42, 7, 1234])
def test_dynamic_no_truth_on_player_socket(seed, terrain_available, tmp_path) -> None:  # type: ignore[no-untyped-def]
    frames, red_xy, truth_ids, canaries = _capture(seed, tmp_path)
    types = {json.loads(f)["type"] for f in frames}
    assert {"hello", "history", "status", "radio"} <= types
    radios = 0
    # Places and route vertices are public map data; a red unit standing on one is not a leak.
    hello = json.loads(next(f for f in frames if json.loads(f)["type"] == "hello"))
    public = {tuple(p["lonlat"]) for p in hello["places"]} | {tuple(q) for r in hello["routes"] for q in r["points"]}
    red_xy = {p for p in red_xy if not any(abs(p[0] - a) < 1e-6 and abs(p[1] - b) < 1e-6 for a, b in public)}
    for raw in frames:
        for c in canaries.values():
            assert c not in raw
        for tid in truth_ids:
            assert f'"{tid}"' not in raw and f" {tid} " not in raw, tid
        f = json.loads(raw)
        bad = [k for k in _keys(f) if is_truth_key(k)]
        assert not bad, bad
        for lon, lat in _pairs(f):
            assert not any(abs(lon - a) < 1e-6 and abs(lat - b) < 1e-6 for a, b in red_xy)
        msgs = [f] if f["type"] == "radio" else f.get("messages", []) if f["type"] == "history" else []
        for m in msgs:
            radios += 1
            assert m["fields"] == parse(m["text"])  # D17: fields come from the delivered text only
    assert radios > 5


def test_player_token_refused_on_ds_surfaces(terrain_available, tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(str(RIDGE), speed=1.0, log_path=str(tmp_path / "auth.sqlite"),
                     tokens_path=tmp_path / "tokens.json", quiet=True)
    tok = app.state.tokens
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/ws/ds?t={tok.player}") as ws:
            ws.receive_text()
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/play?t=nope") as ws:
            ws.receive_text()
        body = {"kind": "net_cut", "args": {"net": "COY", "duration_s": 10}}
        assert client.post("/api/ds/inject", json=body, headers={"Authorization": f"Bearer {tok.player}"}).status_code == 403
        assert client.post("/api/ds/inject", json=body).status_code == 403
        ok = client.post("/api/ds/inject", json=body, headers={"Authorization": f"Bearer {tok.ds}"})
        assert ok.status_code == 200 and ok.json()["ok"]
        with client.websocket_connect(f"/ws/ds?t={tok.ds}") as ws:
            assert json.loads(ws.receive_text())["role"] == "ds"
