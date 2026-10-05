"""Run-time tokens (D10). Generated fresh at every start; written only to the gitignored .kohra/."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tokens:
    player: str
    ds: str

    def is_player(self, t: str | None) -> bool:
        return bool(t) and secrets.compare_digest(str(t), self.player)

    def is_ds(self, t: str | None) -> bool:
        return bool(t) and secrets.compare_digest(str(t), self.ds)


def issue(path: Path, url: str) -> Tokens:
    tok = Tokens(player=secrets.token_urlsafe(16), ds=secrets.token_urlsafe(16))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"player": tok.player, "ds": tok.ds, "url": url}, indent=2), encoding="utf-8")
    return tok


def bearer(header: str | None) -> str | None:
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return None
