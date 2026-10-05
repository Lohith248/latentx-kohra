"""Perception store: records exactly what reached the player, built only from delivered text (D17)."""

from __future__ import annotations

from typing import Any

from kohra.comms.queue import Delivery
from kohra.reports.parse import parse
from kohra.sim.state import Message, State


def record_delivery(state: State, dv: Delivery) -> dict[str, Any]:
    m = dv.msg
    entry = {
        "msg_id": m.msg_id, "tick": state.tick, "net": m.net, "from": m.sender, "to": m.to,
        "precedence": m.precedence, "text": dv.text, "fields": parse(dv.text), "grade": m.grade,
        "partial": dv.partial, "contact_no": m.contact_no, "direction": "in",
    }
    state.perception.inbox.append(entry)
    state.perception.last_heard[m.sender] = state.tick
    return entry


def record_sent(state: State, m: Message) -> dict[str, Any]:
    entry = {
        "msg_id": m.msg_id, "tick": state.tick, "net": m.net, "from": m.sender, "to": m.to,
        "precedence": m.precedence, "text": m.text, "fields": parse(m.text), "grade": None, "partial": False,
        "contact_no": None, "direction": "out",
    }
    state.perception.sent.append(entry)
    return entry


def last_contact_id(state: State) -> str | None:
    for e in reversed(state.perception.inbox):
        if e["fields"].get("type") == "contact":
            return str(e["msg_id"])
    return None
