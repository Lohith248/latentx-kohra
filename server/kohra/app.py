"""FastAPI app: built client, range-capable tile route, /ws/play, /ws/ds, /api/ds/inject and the tick loop."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from kohra import auth
from kohra.cli import TOKENS, default_log_path
from kohra.log.replay import replay
from kohra.rooms import Bot, Room, Runner
from kohra.scenario.load import REPO_ROOT, load_bot, load_injects, load_scenario
from kohra.scenario.schema import Inject
from kohra.views import ds_hello, hello_for, history_for

DIST = REPO_ROOT / "client" / "dist"
TILES = REPO_ROOT / "data" / "tiles"
TILE_FILES = {"basemap.pmtiles", "dem.pmtiles"}
MAX_FRAME = 8192


def basemap_kind(path: Path = TILES / "basemap.pmtiles") -> str:
    """PMTiles v3 header byte 99 is the tile type: 1 = MVT (vector), 2+ = raster image."""
    try:
        with path.open("rb") as f:
            return "vector" if f.read(127)[99] == 1 else "raster"
    except (OSError, IndexError):
        return "vector"


def create_app(scenario_path: str, *, speed: float | None = 1.0, host: str = "127.0.0.1", port: int = 8765,
               log_path: str | None = None, bot: str | None = None, injects: str | None = None,
               seed: int | None = None, ticks: int | None = None, replay_at_endex: bool = False,
               tokens_path: Path = TOKENS, quiet: bool = False) -> FastAPI:
    shown = "127.0.0.1" if host in ("127.0.0.1", "0.0.0.0") else host
    url = f"http://{shown}:{port}"
    tokens = auth.issue(tokens_path, url)
    scen, text = load_scenario(scenario_path)
    log = Path(log_path) if log_path else default_log_path(scen.id)
    runner = Runner(scen, text, seed=seed, log_path=log, end_tick=ticks)
    for inj in load_injects(injects) if injects else []:
        runner.schedule_inject(inj, source="ds", source_id="file")

    async def on_endex(final: str) -> None:
        print(f"ENDEX final hash {final}\nlog: {log}", flush=True)
        if replay_at_endex:
            r = await asyncio.to_thread(replay, log)
            print(f"REPLAY OK {r.final_hash}" if r.ok else f"REPLAY MISMATCH at tick {r.first_mismatch_tick}",
                  flush=True)

    room = Room(runner, speed, basemap_kind(), Bot(load_bot(bot)) if bot else None, on_endex)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if not quiet:
            print(f"KOHRA {scen.title}\n  player: {url}/play?t={tokens.player}\n  DS:     {url}/ds?t={tokens.ds}\n"
                  f"  tokens: {tokens_path}\n  log:    {log}", flush=True)
        task = asyncio.create_task(room.run())

        def _report(t: asyncio.Task[None]) -> None:
            if not t.cancelled() and t.exception() is not None:
                import traceback

                traceback.print_exception(t.exception())
        task.add_done_callback(_report)
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.room = room
    app.state.tokens = tokens

    def index() -> Any:
        page = DIST / "index.html"
        if not page.exists():
            return HTMLResponse("<p>Client not built. Run <code>npm --prefix client run build</code>.</p>", 503)
        return FileResponse(page, headers={"Cache-Control": "no-store"})

    @app.get("/")
    @app.get("/play")
    @app.get("/ds")
    async def _page() -> Any:
        return index()

    @app.get("/tiles/{name}")
    async def _tiles(name: str) -> Any:
        if name not in TILE_FILES or not (TILES / name).exists():
            raise HTTPException(404)
        return FileResponse(TILES / name, media_type="application/octet-stream")  # honours Range requests

    @app.get("/api/health")
    async def _health() -> dict[str, Any]:
        return {"tick": runner.state.tick, "endex": room.endex}

    @app.post("/api/ds/inject")
    async def _inject(body: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, Any]:
        if not tokens.is_ds(auth.bearer(authorization)):
            raise HTTPException(403, "DS token required")
        try:
            inj = Inject.model_validate(body)
        except ValidationError as e:
            raise HTTPException(422, json.loads(e.json(include_url=False))) from e
        async with room.lock:
            if room.endex:
                raise HTTPException(409, "ENDEX")
            res = runner.schedule_inject(inj, source="ds", source_id="api")
        return {"ok": True, "tick": runner.state.tick, **res}

    @app.websocket("/ws/play")
    async def _ws_play(ws: WebSocket) -> None:
        if not tokens.is_player(ws.query_params.get("t")):
            await ws.close(code=4403)
            return
        await ws.accept()
        async with room.lock:
            await ws.send_json(hello_for(runner.state, runner.world, room.basemap_kind).model_dump())
            await ws.send_json(history_for(runner.state, runner.world).model_dump())
            for f in room.player_frames([]):
                await ws.send_json(f)
            room.players.append(ws)
        try:
            while True:
                raw = await ws.receive_text()
                if len(raw) > MAX_FRAME:
                    await ws.send_json({"type": "order_result", "ok": False, "client_seq": 0, "reason": "too large"})
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    msg = None
                if not isinstance(msg, dict):
                    msg = {"type": "invalid"}
                async with room.lock:
                    res = runner.submit_player(msg)
                await ws.send_json(res.model_dump())
        except WebSocketDisconnect:
            pass
        finally:
            with contextlib.suppress(ValueError):
                room.players.remove(ws)

    @app.websocket("/ws/ds")
    async def _ws_ds(ws: WebSocket) -> None:
        if not tokens.is_ds(ws.query_params.get("t")):
            await ws.close(code=4403)
            return
        await ws.accept()
        async with room.lock:
            await ws.send_json(ds_hello(runner.world, room.basemap_kind).model_dump())
            await ws.send_json(room.ds_frame())
            room.ds.append(ws)
        try:
            while True:
                await ws.receive_text()  # read-only view: input is ignored
        except WebSocketDisconnect:
            pass
        finally:
            with contextlib.suppress(ValueError):
                room.ds.remove(ws)

    if (DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
    return app
