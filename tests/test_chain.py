from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from kohra.log.chain import GENESIS, row_hash, verify_chain
from kohra.log.events import LogWriter, read_events


def _write(path: Path, n: int = 20) -> None:
    w = LogWriter(path)
    for i in range(n):
        w.append(i, "x", {"i": i, "f": i / 3})
    w.close()


def test_chain_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    _write(p)
    assert verify_chain(p) == (True, None, 20)
    rows = list(read_events(p))
    assert rows[3] == (3, "x", {"i": 3, "f": 1.0})
    con = sqlite3.connect(p)
    first = con.execute("SELECT seq,tick,kind,payload,prev_hash,hash FROM events WHERE seq=1").fetchone()
    assert first[4] == GENESIS and first[5] == row_hash(1, 0, "x", first[3], GENESIS)


@pytest.mark.parametrize("col,val", [("payload", '{"f":0.0,"i":9}'), ("tick", 99), ("kind", "y")])
def test_tamper_detected(tmp_path: Path, col: str, val: object) -> None:
    p = tmp_path / "l.sqlite"
    _write(p)
    con = sqlite3.connect(p)
    con.execute(f"UPDATE events SET {col}=? WHERE seq=5", (val,))
    con.commit()
    con.close()
    assert verify_chain(p)[:2] == (False, 5)


def test_deleted_row_detected(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    _write(p)
    con = sqlite3.connect(p)
    con.execute("DELETE FROM events WHERE seq=7")
    con.commit()
    con.close()
    assert verify_chain(p)[:2] == (False, 8)


def test_writer_refuses_overwrite(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    _write(p)
    with pytest.raises(FileExistsError):
        LogWriter(p)
