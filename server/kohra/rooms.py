"""The single default room (M1). `Runner` owns state, RNG, command queue and log writer and is shared by
the server, headless runs and tests. `Room` wraps it with the wall-clock tick loop and sockets."""

from __future__ import annotations

import asyncio
import contextlib
import platform
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import ValidationError

from kohra.log.events import LogWriter
from kohra.observe.perception import last_contact_id
from kohra.scenario.schema import Inject, Scenario
from kohra.sim.rng import Rng
from kohra.sim.scripts import common_net
from kohra.sim.state import initial_state, state_hash
from kohra.sim.step import StepResult, step
from kohra.sim.world import World, build_world
from kohra.views import ds_state, view_for
from kohra.wire import ClientOrder, ClientText, POrderResult

HASH_EVERY = 60
DS_EVENT_KINDS = {"inject_fired", "inject_failed", "decision_point", "red_rule", "fire_impact", "jammer_expired",
                  "order_applied", "order_rejected", "order_say_again"}


def build_info() -> dict[str, str]:
    return {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()}


class Runner:
    def __init__(self, scenario: Scenario, scenario_text: str, *, seed: int | None = None,
                 log_path: str | Path | None = None, world: World | None = None, end_tick: int | None = None) -> None:
        if seed is not None:
            scenario = scenario.model_copy(update={"seed": seed})
        self.scenario = scenario
        self.world = world or build_world(scenario)
        self.state = initial_state(scenario, self.world)
        self.rng = Rng(scenario.seed)
        self.end_tick = end_tick or scenario.duration_ticks
        self.pending: list[dict[str, Any]] = []
        self.scheduled: list[tuple[int, int, dict[str, Any]]] = []
        self.seqs: dict[str, int] = {}
        self.hashes: list[tuple[int, str]] = []
        self.step_ms: list[float] = []
        self.final_hash: str | None = None
        self.log = LogWriter(log_path) if log_path else None
        self._log(0, "run_start", {"scenario_text": scenario_text, "seed": scenario.seed, "end_tick": self.end_tick,
                                   "build": build_info()})
        for inj in scenario.injects:
            self.schedule_inject(inj, source="scenario")
        if self.log:
            self.log.commit()

    def _log(self, tick: int, kind: str, payload: dict[str, Any]) -> None:
        if self.log:
            self.log.append(tick, kind, payload)

    def _next_seq(self, source_id: str) -> int:
        self.seqs[source_id] = self.seqs.get(source_id, 0) + 1
        return self.seqs[source_id]

    def _queue(self, source: str, source_id: str, ctype: str, payload: dict[str, Any], apply_tick: int,
               late: bool = False) -> dict[str, Any]:
        cmd = {"apply_tick": apply_tick, "source": source, "source_id": source_id,
               "client_seq": self._next_seq(source_id), "type": ctype, "payload": payload, "late": late}
        self.pending.append(cmd)
        self._log(self.state.tick, "command", cmd)
        return cmd

    @property
    def done(self) -> bool:
        return self.state.tick >= self.end_tick

    # ---- input ------------------------------------------------------------------------------
    def submit_player(self, raw: dict[str, Any], source: str = "player", source_id: str = "player") -> POrderResult:
        """Validate a player order/text. Rejections are logged as `order_rejected` and never touch the sim."""
        seq = raw.get("client_seq", 0) if isinstance(raw, dict) else 0
        seq = seq if isinstance(seq, int) else 0
        try:
            if self.done:
                raise ValueError("ENDEX")
            msg: ClientOrder | ClientText
            msg = ClientText.model_validate(raw) if raw.get("type") == "text" else ClientOrder.model_validate(raw)
            me = self.state.unit_by_callsign(self.state.player)
            to = self.state.unit_by_callsign(msg.to)
            if me is None or to is None or to.callsign == me.callsign:
                raise ValueError(f"unknown addressee {msg.to}")
            if isinstance(msg, ClientText):
                if msg.net not in me.nets or msg.net not in to.nets:
                    raise ValueError("addressee not on that net")
            elif common_net(me, to) is None:
                raise ValueError("no common net")
        except (ValidationError, ValueError, AttributeError) as e:
            reason = e.errors(include_url=False, include_input=False) if isinstance(e, ValidationError) else str(e)
            self._log(self.state.tick, "order_rejected", {"source": source, "reason": str(reason)[:500],
                                                          "raw": _safe(raw)})
            return POrderResult(ok=False, client_seq=seq, reason=str(reason)[:300])
        payload = msg.model_dump(exclude={"type", "client_seq"})
        self._queue(source, source_id, msg.type, payload, self.state.tick)
        return POrderResult(ok=True, client_seq=seq)

    def schedule_inject(self, inj: Inject, source: str = "ds", source_id: str = "cli") -> dict[str, Any]:
        payload = {"kind": inj.kind, "args": inj.args}
        if inj.at_tick is None or inj.at_tick <= self.state.tick:
            late = inj.at_tick is not None and inj.at_tick < self.state.tick
            cmd = self._queue(source, source_id, "inject", payload, self.state.tick, late)
            return {"queued": True, "apply_tick": cmd["apply_tick"], "late": late}
        self.scheduled.append((inj.at_tick, len(self.scheduled), {"source": source, "source_id": source_id,
                                                                  "payload": payload}))
        return {"queued": False, "scheduled_for": inj.at_tick}

    # ---- tick ---------------------------------------------------------------------------------
    def advance(self) -> StepResult:
        t = self.state.tick
        for _at, _i, s in sorted(x for x in self.scheduled if x[0] <= t):
            self._queue(s["source"], s["source_id"], "inject", s["payload"], t)
        self.scheduled = [x for x in self.scheduled if x[0] > t]
        cmds = [c for c in self.pending if c["apply_tick"] == t]
        self.pending = [c for c in self.pending if c["apply_tick"] != t]
        t0 = time.perf_counter()
        res = step(self.state, cmds, self.rng, self.world)
        self.step_ms.append((time.perf_counter() - t0) * 1000)
        for kind, payload in res.events:
            self._log(res.tick, kind, payload)
        if self.state.tick % HASH_EVERY == 0:
            self._hash()
        if self.log:
            self.log.commit()
        return res

    def _hash(self) -> str:
        h = state_hash(self.state, self.rng)
        if not self.hashes or self.hashes[-1][0] != self.state.tick:
            self.hashes.append((self.state.tick, h))
            self._log(self.state.tick, "state_hash", {"tick": self.state.tick, "hash": h})
        return h

    def finish(self) -> str:
        self.final_hash = self._hash()
        self._log(self.state.tick, "endex", {"tick": self.state.tick, "final_hash": self.final_hash})
        if self.log:
            self.log.close()
            self.log = None
        return self.final_hash

    def run_to_end(self, bot: Bot | None = None) -> str:
        while not self.done:
            if bot:
                bot.before_tick(self)
            self.advance()
        return self.finish()


def _safe(raw: Any) -> Any:
    try:
        return {str(k): v for k, v in dict(raw).items()}
    except (TypeError, ValueError):
        return repr(raw)[:200]


class Bot:
    """Headless player from a bot YAML (ridge.bot.yaml). Uses the same validated path as a human."""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.entries = entries

    def before_tick(self, runner: Runner) -> None:
        for e in self.entries:
            if int(e["tick"]) != runner.state.tick:
                continue
            if "order" in e:
                o = dict(e["order"])
                if "to_place" in o:
                    o["grid"] = runner.world.place_grid(o.pop("to_place"))
                rel = []
                for r in o.get("relied_on", []):
                    if r == "@last_contact":
                        lc = last_contact_id(runner.state)
                        rel += [lc] if lc else []
                    else:
                        rel.append(r)
                o["relied_on"] = rel
                runner.submit_player({"type": "order", **o}, source="bot", source_id="bot")
            elif "text" in e:
                runner.submit_player({"type": "text", **e["text"]}, source="bot", source_id="bot")


class Room:
    """Wall-clock wrapper: ticks the Runner at `speed` x real time and fans frames out to sockets."""

    def __init__(self, runner: Runner, speed: float | None, basemap_kind: str, bot: Bot | None = None,
                 on_endex: Callable[[str], Awaitable[None]] | None = None) -> None:
        self.runner = runner
        self.speed = speed
        self.basemap_kind = basemap_kind
        self.bot = bot
        self.on_endex = on_endex
        self.players: list[Any] = []
        self.ds: list[Any] = []
        self.ds_events: list[dict[str, Any]] = []
        self.planted: set[str] = set()  # msg ids of planted reports, so the DS feed can flag orders citing them
        self.paused = False
        self.lock = asyncio.Lock()

    @property
    def endex(self) -> bool:
        return self.runner.final_hash is not None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self.runner.done:
            if self.paused:  # wall-clock pause only: commands are stamped by tick, so replay is unaffected
                await asyncio.sleep(0.1)
                continue
            t0 = loop.time()
            async with self.lock:
                if self.bot:
                    self.bot.before_tick(self.runner)
                res = self.runner.advance()
                self.collect(res)
                if self.runner.done:
                    self.runner.finish()
            await self.broadcast(res.player_msgs)
            if self.speed:
                await asyncio.sleep(max(0.0, 1.0 / self.speed - (loop.time() - t0)))
            else:
                await asyncio.sleep(0)
        if self.on_endex and self.runner.final_hash:
            await self.on_endex(self.runner.final_hash)

    def collect(self, res: StepResult) -> None:
        """Keep the events the DS view shows; orders citing a planted report are flagged for the DS."""
        for kind, payload in res.events:
            if kind == "inject_fired" and payload.get("kind") == "planted_report" and payload.get("msg"):
                self.planted.add(str(payload["msg"]))
            if kind in DS_EVENT_KINDS:
                detail = payload
                if kind == "order_applied":
                    detail = {**payload, "planted_refs": [r for r in payload.get("relied_on") or [] if r in self.planted]}
                self.ds_events.append({"tick": res.tick, "kind": kind, "detail": detail})

    def player_frames(self, new_msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        r = self.runner
        return view_for(r.state.player, r.state, r.world, new_msgs, self.speed or 0.0, self.paused, self.endex,
                        r.final_hash)

    def ds_frame(self) -> dict[str, Any]:
        r = self.runner
        return ds_state(r.state, r.world, self.ds_events[-200:], self.endex, r.final_hash, self.paused,
                        self.speed or 0.0).model_dump()

    async def broadcast(self, new_msgs: list[dict[str, Any]]) -> None:
        if self.players:
            frames = self.player_frames(new_msgs)
            for ws in list(self.players):
                await self._send(self.players, ws, frames)
        if self.ds:
            frame = self.ds_frame()
            for ws in list(self.ds):
                await self._send(self.ds, ws, [frame])

    @staticmethod
    async def _send(group: list[Any], ws: Any, frames: list[dict[str, Any]]) -> None:
        """Send with a timeout; a closed or stalled socket is dropped instead of holding up the tick loop."""
        try:
            for f in frames:
                await asyncio.wait_for(ws.send_json(f), timeout=2.0)
        except Exception:
            with contextlib.suppress(ValueError):
                group.remove(ws)
