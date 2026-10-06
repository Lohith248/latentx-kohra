"""After-action review: one self-contained HTML page built from a run log.

It reads only logged events (run_start, order_applied, message_tx, message_rx, inject_fired, decision_point,
fire_impact, endex), so it can be produced for any finished run. It shows ground truth by design: it is the
debrief, not a player view.
"""

from __future__ import annotations

import html
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from kohra.log.chain import verify_chain
from kohra.log.events import read_events
from kohra.log.replay import replay

Event = dict[str, Any]
JAM_PHASE = "Jammer among the company"

CSS = """body{font:14px/1.5 "Segoe UI",system-ui,sans-serif;max-width:1050px;margin:24px auto;padding:0 16px;color:#1d2433}
h1{font-size:24px;margin:0}h2{font-size:16px;margin:22px 0 6px;border-bottom:2px solid #e5e9f0;padding-bottom:4px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #e5e9f0;padding:4px 6px;text-align:left;
vertical-align:top}th{background:#f4f6fa}.bad{color:#b00020}li.bad{color:#b00020}li.warn{color:#8a5a00}li{margin:4px 0}
.tl{width:100%;border:1px solid #e5e9f0;border-radius:6px;background:#fff}.cls{background:#2f3b2f;color:#e9e5c8;
padding:2px 8px;font-size:12px;display:inline-block}code{font-size:12px}.note{font-size:12px;color:#666}
@media print{body{margin:0;max-width:none}h2{break-after:avoid}tr{break-inside:avoid}}"""


def _clock(start_clock: str, dt: float) -> Callable[[int], str]:
    h0, m0, s0 = (int(x) for x in start_clock.split(":"))
    base = h0 * 3600 + m0 * 60 + s0

    def clock(tick: int) -> str:
        s = base + int(tick * dt)
        return f"{s // 3600 % 24:02d}:{s // 60 % 60:02d}:{s % 60:02d}"

    return clock


def _esc(v: Any) -> str:
    return html.escape(str(v))


def _order(kind: Any) -> str:
    """Order kinds as a reader says them: "FIRE_MISSION" -> "Fire mission"."""
    return _esc(str(kind).replace("_", " ").capitalize())


INJECT_NAMES = {"jammer_add": "Jammer placed", "jammer_move": "Jammer moved", "jammer_remove": "Jammer removed",
                "net_cut": "Net cut", "net_delay": "Net delayed", "planted_report": "Planted report",
                "gnss_zone_add": "GNSS spoofing started"}


def build_aar(log: str | Path, verify: bool = True) -> str:
    """Return the AAR page for a finished run. `verify` re-checks the hash chain and replays the run."""
    path = Path(log)
    events = list(read_events(path))
    start = next((p for _t, k, p in events if k == "run_start"), None)
    if start is None:
        raise ValueError(f"{path}: no run_start event")
    sc: dict[str, Any] = yaml.safe_load(start["scenario_text"])
    dt = float(sc.get("tick_seconds", 1.0))
    clock = _clock(str(sc["start_clock"]), dt)
    end = next((int(p["tick"]) for _t, k, p in events if k == "endex"), int(sc["duration_ticks"]))
    final = next((str(p["final_hash"]) for _t, k, p in events if k == "endex"), "not reached")
    player = next(str(u["callsign"]) for u in sc["sides"]["blue"]["units"] if u.get("player_role"))
    side = {str(u["id"]): str(s) for s in sc["sides"] for u in sc["sides"][s]["units"]}
    theta = float(sc["comms"].get("link_model", {}).get("theta_db", 6.0))

    tx: dict[str, Event] = {}
    rx: dict[str, dict[str, Event]] = defaultdict(dict)
    orders: list[Event] = []
    injects: list[Event] = []
    dps: list[Event] = []
    fires: list[Event] = []
    for t, k, p in events:
        if k == "message_tx":
            tx[str(p["msg"])] = {**p, "tick": t}
        elif k == "message_rx":
            rx[str(p["msg"])][str(p["rx"])] = {**p, "tick": t}
        elif k == "order_applied" and p.get("source") in ("player", "bot"):
            orders.append({**p, "tick": t})
        elif k == "inject_fired":
            injects.append({**p, "tick": t})
        elif k == "decision_point":
            dps.append({**p, "tick": t})
        elif k == "fire_impact":
            fires.append({**p, "tick": t})

    heard = [(m, rx[m][player]) for m in tx if player in rx[m] and tx[m]["from"] != player]
    jam_on = sorted(int(i["tick"]) for i in injects if i["kind"] == "jammer_add")
    jam_off = sorted(int(i["tick"]) for i in injects if i["kind"] in ("jammer_move", "jammer_remove"))

    def phase(t: int) -> str:
        if not jam_on or t < jam_on[0]:
            return "Before jamming"
        return JAM_PHASE if not jam_off or t < jam_off[0] else "After the jammer moved"

    findings: list[tuple[str, str]] = []
    rows: list[str] = []
    for o in orders:
        when = clock(int(o["tick"]))
        cited: list[str] = list(o.get("relied_on") or [])
        cited_txt: list[str] = []
        for r in cited:
            src = tx.get(r)
            if src is None:
                cited_txt.append(_esc(r))
                continue
            age = (int(o["tick"]) - int(src["tick"])) * dt
            planted = " <b class=bad>(planted)</b>" if src.get("planted") else ""
            cited_txt.append(f"{_esc(str(src['kind']).upper())} from {_esc(src['from'])}, grade "
                             f"{_esc(src.get('grade') or '-')}, {age:.0f} s old{planted} <span class=note>({_esc(r)})</span>")
            if src.get("planted"):
                others = len(cited) - 1
                findings.append(("bad", f"{when}: {_order(o['kind'])} to {_esc(o['to'])} (confidence {o['confidence']}%) "
                                        f"relied on a {_esc(src.get('grade'))} {_esc(str(src['kind']).upper())} "
                                        f"attributed to {_esc(src['from'])}. That report was planted by the instructor "
                                        "to deceive. "
                                        + ("No other report was cited." if not others
                                           else f"{others} other report(s) were cited alongside it.")))
        if o.get("confidence") is not None and int(o["confidence"]) >= 70 and not cited:
            findings.append(("warn", f"{when}: {_order(o['kind'])} to {_esc(o['to'])} stated {o['confidence']}% confidence "
                                     "but cited no report. Debrief question: what was the confidence based on?"))
        ack = next((m for m, d in heard
                    if tx[m]["kind"] == "ack" and str(o["msg"]) in str(tx[m]["text"]) and d["delivered"]), None)
        got = rx.get(str(o["msg"]), {}).get(str(o["to"]))
        delivery = "-" if got is None else ("Delivered" if got["delivered"] else "Lost")
        if got is not None and got.get("sinr_eff") is not None:
            delivery += f" ({float(got['sinr_eff']):.1f} dB)"
        conf = "" if o.get("confidence") is None else f"{o['confidence']}%"
        basis = "<br>".join(cited_txt) or ("None cited" if o.get("confidence") is not None else "")
        wilco = clock(int(rx[ack][player]["tick"])) if ack else "<span class=bad>Not received</span>"
        rows.append(f"<tr><td>{when}</td><td>{_order(o['kind'])}</td><td>{_esc(o['to'])}</td><td>{conf}</td><td>{basis}</td>"
                    f"<td>{_esc(o.get('rationale') or '')}</td><td>{delivery}</td><td>{wilco}</td></tr>")

    lost = [(m, d) for m, d in heard if not d["delivered"]]
    by_phase: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for _m, d in heard:
        by_phase[phase(int(d["tick"]))][0 if d["delivered"] else 1] += 1
    if lost:
        jam_lost = [x for x in lost if phase(int(x[1]["tick"])) == JAM_PHASE]
        kinds = ", ".join(sorted({str(tx[m]["kind"]).upper() for m, _ in jam_lost})) or "none"
        findings.append(("info", f"Reports lost: {len(lost)} of {len(heard)} transmissions on {player}'s nets did not reach "
                                 f"{player}; {len(jam_lost)} of them while the jammer was among the company ({kinds})."))
    for f in fires:
        hit = [str(u) for u in f.get("hit", [])]
        red = [u for u in hit if side.get(u) == "red"]
        blue = [u for u in hit if side.get(u) == "blue"]
        findings.append(("bad" if blue else "info",
                         f"{clock(int(f['tick']))}: fire mission {_esc(f['ref'])} impacted at GR {_esc(f['grid'])}. "
                         + (f"Enemy units hit: {', '.join(red)}." if red else "No enemy unit was within the effect radius.")
                         + (f" Own units hit: {', '.join(blue)}." if blue else "")))
    for d in dps:
        nxt = next((o for o in orders if int(o["tick"]) >= int(d["tick"])), None)
        lat = (f"First order issued {(int(nxt['tick']) - int(d['tick'])) * dt:.0f} s later ({_order(nxt['kind'])} to "
               f"{_esc(nxt['to'])})." if nxt else "No order followed.")
        findings.append(("info", f"{clock(int(d['tick']))}: decision point {_esc(d['id'])}, "
                                 f"“{_esc(d['describes'])}” {lat}"))

    gaps: list[str] = []
    for cs in sorted({str(tx[m]["from"]) for m, _ in heard}):
        ts = sorted(int(d["tick"]) for m, d in heard if tx[m]["from"] == cs and d["delivered"])
        pts = [0, *ts, end]
        gap, at = max((b - a, a) for a, b in zip(pts, pts[1:], strict=False))
        gaps.append(f"<tr><td>{_esc(cs)}</td><td>{len(ts)}</td><td>{gap * dt / 60:.1f} min from {clock(at)}</td></tr>")

    integrity = ""
    if verify:
        ok, bad, n = verify_chain(path)
        rep = replay(path)
        chain = f"hash chain intact ({n} rows)" if ok else f"hash chain broken at row {bad}"
        again = (f"replay reproduces the final state ({(rep.final_hash or '')[:16]}…)" if rep.ok
                 else f"replay diverges at tick {rep.first_mismatch_tick}")
        integrity = f"<p><b>Log integrity:</b> {chain}; {again}.</p>"

    lost_rows = []
    for m, d in lost:
        s = d.get("sinr_eff")
        cause = ("Net cut" if d.get("cut") else f"SINR below threshold ({theta:g} dB)" if s is None or float(s) < theta
                 else "Probabilistic loss above threshold")
        lost_rows.append(f"<tr><td>{clock(int(d['tick']))}</td><td>{_esc(tx[m]['from'])}</td>"
                         f"<td>{_esc(str(tx[m]['kind']).upper())}</td><td>{'' if s is None else f'{float(s):.1f}'}</td>"
                         f"<td>{cause}</td><td>{_esc(str(tx[m]['text'])[:90])}</td></tr>")
    phases = "".join(f"<tr><td>{k}</td><td>{v[0]}</td><td>{v[1]}</td></tr>" for k, v in by_phase.items())
    points = "".join(f"<li class={c}>{t}</li>" for c, t in findings) or "<li>No debrief points.</li>"
    timeline = _timeline(end, clock, injects, dps, orders, heard, tx, jam_on, jam_off)
    return f"""<!doctype html><html lang="en-GB"><meta charset=utf-8><title>AAR: {_esc(sc['title'])}</title>
<style>{CSS}</style>
<span class=cls>{_esc(sc.get('classification_label', 'ILLUSTRATIVE'))}</span>
<h1>After-action review</h1>
<p style="font-size:16px;margin:2px 0 10px">{_esc(sc['title'])}</p>
<p>Trainee: <b>{_esc(player)}</b> (company commander) | Seed {start['seed']} | {clock(0)} to {clock(end)} | Final state hash <code>{_esc(final)}</code></p>{integrity}
<h2>Debrief points</h2><ul>{points}</ul>
<h2>Timeline</h2>{timeline}
<p class=note>Shaded: jammer among the company. Red dots: instructor injects. Bars: orders, height proportional to stated confidence. Ticks: reports that reached {_esc(player)} (green) and reports lost (red).</p>
<h2>Decision log</h2>
<table><tr><th>Time</th><th>Order</th><th>To</th><th>Confidence</th><th>Reports cited</th><th>Rationale</th><th>Order delivery</th><th>WILCO received</th></tr>{''.join(rows)}</table>
<h2>Reports lost to degraded communications</h2><table><tr><th>Phase</th><th>Received</th><th>Lost</th></tr>{phases}</table>
<table style="margin-top:8px"><tr><th>Time</th><th>From</th><th>Type</th><th>SINR (dB)</th><th>Cause</th><th>Content (not received by the trainee)</th></tr>{''.join(lost_rows)}</table>
<h2>Longest gap between reports, per station</h2><table><tr><th>Station</th><th>Reports received</th><th>Longest gap</th></tr>{''.join(gaps)}</table>
<p class=note>Generated from <code>{_esc(path.name)}</code>. All figures are computed from the hash-chained exercise log.</p></html>"""


def _timeline(end: int, clock: Callable[[int], str], injects: list[Event], dps: list[Event], orders: list[Event],
              heard: list[tuple[str, Event]], tx: dict[str, Event], jam_on: list[int], jam_off: list[int]) -> str:
    width, left = 1000, 150

    def x(t: int) -> float:
        return left + (width - left - 20) * t / max(end, 1)

    svg = [f'<svg viewBox="0 0 {width} 196" class=tl><style>text{{font:14px system-ui;fill:#1d2433}}</style>']
    for i, lane in enumerate(["Instructor injects", "Decision points", "Orders", "Reports in / lost"]):
        y = 30 + i * 42
        svg.append(f'<text x="6" y="{y + 5}">{lane}</text><line x1="{left}" x2="{width - 20}" y1="{y}" y2="{y}" stroke="#ddd"/>')
    for t0 in range(0, end + 1, 60):
        svg.append(f'<text x="{x(t0) - 18:.0f}" y="190" style="fill:#555">{clock(t0)[3:]}</text>')
    if jam_on:
        a, b = jam_on[0], (jam_off[0] if jam_off else end)
        svg.append(f'<rect x="{x(a):.0f}" y="12" width="{x(b) - x(a):.0f}" height="158" fill="#d01c1c" opacity=".07"/>')
    for inj in injects:
        svg.append(f'<circle cx="{x(int(inj["tick"])):.0f}" cy="30" r="5" fill="#d01c1c">'
                   f'<title>{clock(int(inj["tick"]))} {_esc(INJECT_NAMES.get(str(inj["kind"]), inj["kind"]))}</title></circle>')
    for d in dps:
        svg.append(f'<rect x="{x(int(d["tick"])) - 4:.0f}" y="68" width="8" height="8" fill="#e0a100"><title>{_esc(d["id"])}</title></rect>')
    for o in orders:
        c = int(o.get("confidence") or 0)
        svg.append(f'<rect x="{x(int(o["tick"])) - 3:.0f}" y="{114 - c * 0.3:.0f}" width="6" height="{c * 0.3:.0f}" '
                   f'fill="#1f5fa8"><title>{clock(int(o["tick"]))} {_order(o["kind"])} {c}%</title></rect>')
    for m, d in heard:
        col, y = ("#1b9e3a", 148) if d["delivered"] else ("#d01c1c", 162)
        svg.append(f'<line x1="{x(int(d["tick"])):.0f}" x2="{x(int(d["tick"])):.0f}" y1="{y - 7}" y2="{y + 3}" stroke="{col}" '
                   f'stroke-width="2"><title>{clock(int(d["tick"]))} {_esc(tx[m]["kind"])} from {_esc(tx[m]["from"])}</title></line>')
    svg.append("</svg>")
    return "".join(svg)
