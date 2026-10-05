"""Append-only SQLite event log (WAL), hash-chained row by row."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from kohra.log.chain import GENESIS, row_hash
from kohra.sim.state import canonical_json

SCHEMA = """CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY, tick INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL)"""


class LogWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise FileExistsError(self.path)
        # The writer is created on the main thread and used from the server's event-loop thread; all
        # access goes through the single Runner (serialised by the room lock), so sharing is safe.
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute(SCHEMA)
        self.seq = 0
        self.prev = GENESIS

    def append(self, tick: int, kind: str, payload: dict[str, Any]) -> None:
        self.seq += 1
        body = canonical_json(payload)
        h = row_hash(self.seq, tick, kind, body, self.prev)
        self.con.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (self.seq, tick, kind, body, self.prev, h))
        self.prev = h

    def commit(self) -> None:
        self.con.commit()

    def close(self) -> None:
        self.con.commit()
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con.close()


def read_events(path: str | Path, kinds: tuple[str, ...] | None = None) -> Iterator[tuple[int, str, dict[str, Any]]]:
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        q = "SELECT tick, kind, payload FROM events"
        args: tuple[str, ...] = ()
        if kinds:
            q += f" WHERE kind IN ({','.join('?' * len(kinds))})"
            args = kinds
        for tick, kind, payload in con.execute(q + " ORDER BY seq", args):
            yield int(tick), str(kind), json.loads(payload)
    finally:
        con.close()
