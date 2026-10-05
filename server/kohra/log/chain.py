"""SHA-256 hash chain over event rows, and its verifier."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

GENESIS = "0" * 64


def row_hash(seq: int, tick: int, kind: str, payload: str, prev: str) -> str:
    return hashlib.sha256(f"{seq}|{tick}|{kind}|{payload}|{prev}".encode()).hexdigest()


def verify_chain(path: str | Path) -> tuple[bool, int | None, int]:
    """(ok, first_bad_seq, rows_checked)."""
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        prev = GENESIS
        n = 0
        for seq, tick, kind, payload, prev_hash, h in con.execute(
                "SELECT seq, tick, kind, payload, prev_hash, hash FROM events ORDER BY seq"):
            n += 1
            if prev_hash != prev or row_hash(seq, tick, kind, payload, prev) != h:
                return False, int(seq), n
            prev = h
        return True, None, n
    finally:
        con.close()
