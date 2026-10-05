// Directing Staff view: ground truth, link SINR, live trainee decisions and exercise control (start, pause,
// speed, injects). Injects go through POST /api/ds/inject, which validates and logs them like CLI injects.
import type maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { unitImage } from "../map/symbols";
import { circle, setGeo, setPoints, useKohraMap } from "../map/useMap";
import { dsPost, token, useDs } from "../state/store";
import type { DsEvent, DsHello, DsState, LonLat } from "../state/types";

type Pick = { kind: "jammer_add"; net: string } | { kind: "jammer_move"; id: string } | { kind: "gnss_zone_add" };
type Notify = (text: string, ok: boolean) => void;

const SPEEDS = [1, 2, 4, 8];
const UNIT_TYPES = ["tank", "APC", "infantry", "recce"];
const SIZES = ["section", "platoon", "company"];
const DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const EVENT_KINDS = new Set(["inject_fired", "inject_failed", "decision_point", "red_rule", "fire_impact", "jammer_expired",
  "order_rejected", "order_say_again"]);

function sinrColour(s: number, theta: number): string {
  return s >= theta + 3 ? "#1b9e3a" : s >= theta ? "#e0a100" : "#d01c1c";
}

/** Latest value, at most every `ms` (trailing update guaranteed), so fast runs don't keep the map busy. */
function useThrottled<T>(value: T, ms: number): T {
  const [out, setOut] = useState(value);
  const last = useRef(0);
  useEffect(() => {
    const wait = Math.max(0, last.current + ms - Date.now());
    const id = setTimeout(() => { last.current = Date.now(); setOut(value); }, wait);
    return () => clearTimeout(id);
  }, [value, ms]);
  return out;
}

function nextId(prefix: string, taken: string[]): string {
  let n = 1;
  while (taken.includes(`${prefix}-${n}`)) n += 1;
  return `${prefix}-${n}`;
}

function errorText(data: unknown, status: number): string {
  const d = (data as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => String((x as { msg?: string }).msg ?? "")).filter(Boolean).join("; ") || `HTTP ${status}`;
  return `HTTP ${status}`;
}

async function inject(kind: string, args: Record<string, unknown>, label: string, notify: Notify): Promise<void> {
  const r = await dsPost("/api/ds/inject", { kind, args });
  notify(r.ok ? label : `Refused: ${errorText(r.data, r.status)}`, r.ok);
}

/** One-line description of a DS event, for the events list. */
export function describe(e: DsEvent): string {
  const d = e.detail;
  const args = (d.args ?? {}) as Record<string, unknown>;
  const late = d.late ? " (late)" : "";
  switch (e.kind) {
    case "decision_point": return `Decision point ${String(d.id)}: ${String(d.describes)}`;
    case "inject_failed": return `Inject ${String(d.kind)} failed: ${String(d.error)}`;
    case "jammer_expired": return `Jammer ${String(d.id)} expired`;
    case "order_rejected": return `Order rejected: ${String(d.reason)}`;
    case "order_say_again": return `${String(d.unit)} asked SAY AGAIN for ${String(d.msg)}`;
    case "fire_impact": {
      const hit = (d.hit as string[] | undefined) ?? [];
      return `Fire mission ${String(d.ref)} impact at GR ${String(d.grid)}: ${hit.length ? `hit ${hit.join(", ")}` : "no units hit"}`;
    }
    case "red_rule": {
      const acts = (d.actions as Record<string, unknown>[] | undefined) ?? [];
      return acts.map((a) => `${String(a.unit)} ${String(a.action)}${a.to_place ? ` to ${String(a.to_place)}` : ""}${a.via_route ? ` via ${String(a.via_route)}` : ""}`).join("; ") || "Red plan step";
    }
    case "inject_fired":
      switch (d.kind) {
        case "jammer_add": return `Jammer ${String(args.id)} placed${late}`;
        case "jammer_move": return `Jammer ${String(args.id)} moved${late}`;
        case "jammer_remove": return `Jammer ${String(args.id)} removed${late}`;
        case "net_cut": return `${String(args.net)} net cut for ${String(args.duration_s)} s${late}`;
        case "net_delay": return `${String(args.net)} net delayed by ${String(args.extra_s)} s for ${String(args.duration_s)} s${late}`;
        case "planted_report": return `Planted ${String(args.template).toUpperCase()} from ${String(args.from_callsign)}, graded ${String(args.grade)}${late}`;
        case "gnss_zone_add": return `GNSS spoofing zone ${String(args.id)} active${late}`;
        default: return `${String(d.kind)}${late}`;
      }
    default: return e.kind;
  }
}

function Decisions({ events }: { events: DsEvent[] }) {
  const orders = events.filter((e) => e.kind === "order_applied").slice().reverse();
  if (!orders.length) return <p className="muted">No orders yet.</p>;
  return (
    <ol className="decisions" data-testid="ds-decisions">
      {orders.map((e) => {
        const d = e.detail;
        const cited = (d.relied_on as string[] | null) ?? [];
        const planted = new Set((d.planted_refs as string[] | undefined) ?? []);
        return (
          <li key={String(d.msg)}>
            <b>{e.clock}</b> {String(d.kind)} to {String(d.to)}
            {d.confidence !== null && d.confidence !== undefined && <span className="conf">{String(d.confidence)}%</span>}
            {d.kind !== "TEXT" && (
              <div className="cited">Cited: {cited.length
                ? cited.map((c) => <span key={c} className={planted.has(c) ? "planted" : ""}>{c}{planted.has(c) ? " (planted)" : ""}</span>)
                : "none"}</div>
            )}
            {d.rationale ? <div className="why">"{String(d.rationale)}"</div> : null}
          </li>
        );
      })}
    </ol>
  );
}

function InjectPanel({ hello, state, setPick, notify }: { hello: DsHello; state: DsState; setPick: (p: Pick | null) => void; notify: Notify }) {
  const nets = hello.nets.map((n) => n.id);
  const playerNets = hello.stations.find((s) => s.callsign === hello.player)?.nets ?? [];
  const senders = hello.stations.filter((s) => s.callsign !== hello.player && s.nets.some((n) => playerNets.includes(n)));
  const [jamNet, setJamNet] = useState(nets[0] ?? "");
  const [effNet, setEffNet] = useState(nets[0] ?? "");
  const [cutS, setCutS] = useState(60);
  const [delayS, setDelayS] = useState(20);
  const [tpl, setTpl] = useState<"intsum" | "contact">("intsum");
  const [from, setFrom] = useState(senders.find((s) => !s.nets.includes(nets[0] ?? ""))?.callsign ?? senders[0]?.callsign ?? "");
  const [unit, setUnit] = useState("tank");
  const [size, setSize] = useState("platoon");
  const [place, setPlace] = useState(hello.place_ids.find((p) => p.id === "TAMARIND")?.id ?? hello.place_ids[0]?.id ?? "");
  const [dir, setDir] = useState("SW");
  const [rel, setRel] = useState("C");
  const [cred, setCred] = useState("3");
  const off = state.endex;

  const plant = () => {
    const net = hello.stations.find((s) => s.callsign === from)?.nets.find((n) => playerNets.includes(n));
    if (!net) { notify(`${from} shares no net with ${hello.player}`, false); return; }
    const fields: Record<string, string> = { size, unit_type: unit, grid_from_place: place, time: "auto",
      ...(tpl === "intsum" ? { direction: dir } : { activity: `moving ${dir}` }) };
    void inject("planted_report", { net, from_callsign: from, to_callsign: hello.player, template: tpl, fields,
      grade: `${rel}${cred}`, precedence: "IMMEDIATE" }, `Planted ${tpl.toUpperCase()} from ${from}, graded ${rel}${cred}`, notify);
  };

  return (
    <fieldset className="inject" disabled={off}>
      <div className="inj-row">
        <button type="button" className="primary" data-testid="ds-place-jammer" onClick={() => setPick({ kind: "jammer_add", net: jamNet })}>Place jammer</button>
        <label>on <select value={jamNet} onChange={(e) => setJamNet(e.target.value)}>{nets.map((n) => <option key={n}>{n}</option>)}</select> net</label>
      </div>
      {state.jammers.map((j) => (
        <div className="inj-row" key={j.id}>
          <span className="mono">{j.id}</span> {j.emitting ? "emitting" : j.active ? "idle" : "off"}
          <button type="button" onClick={() => setPick({ kind: "jammer_move", id: j.id })}>Move</button>
          <button type="button" onClick={() => void inject("jammer_remove", { id: j.id }, `Jammer ${j.id} removed`, notify)}>Remove</button>
        </div>
      ))}
      <div className="inj-row">
        <select value={effNet} onChange={(e) => setEffNet(e.target.value)} aria-label="net">{nets.map((n) => <option key={n}>{n}</option>)}</select>
        <button type="button" onClick={() => void inject("net_cut", { net: effNet, duration_s: cutS }, `${effNet} net cut for ${cutS} s`, notify)}>Cut</button>
        <select value={cutS} onChange={(e) => setCutS(Number(e.target.value))} aria-label="cut duration">{[30, 60, 120].map((s) => <option key={s} value={s}>{s} s</option>)}</select>
        <button type="button" onClick={() => void inject("net_delay", { net: effNet, extra_s: delayS, duration_s: 120 }, `${effNet} net delayed by ${delayS} s for 2 min`, notify)}>Delay</button>
        <select value={delayS} onChange={(e) => setDelayS(Number(e.target.value))} aria-label="delay">{[10, 20, 30].map((s) => <option key={s} value={s}>+{s} s</option>)}</select>
      </div>
      <div className="inj-row">
        <button type="button" onClick={() => setPick({ kind: "gnss_zone_add" })}>Spoof GNSS</button>
        <span className="muted">800 m zone, drifts to 400 m</span>
      </div>
      <div className="plant">
        <div className="inj-row">
          <b>Planted report</b>
          <select value={tpl} onChange={(e) => setTpl(e.target.value as "intsum" | "contact")} aria-label="template">
            <option value="intsum">INTSUM</option><option value="contact">CONTACT</option>
          </select>
          from <select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="sender">{senders.map((s) => <option key={s.callsign}>{s.callsign}</option>)}</select>
        </div>
        <div className="inj-row">
          <select value={size} onChange={(e) => setSize(e.target.value)} aria-label="size">{SIZES.map((s) => <option key={s}>{s}</option>)}</select>
          <select value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="unit type">{UNIT_TYPES.map((s) => <option key={s}>{s}</option>)}</select>
          at <select value={place} onChange={(e) => setPlace(e.target.value)} aria-label="place">{hello.place_ids.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          {tpl === "intsum" ? "heading" : "moving"} <select value={dir} onChange={(e) => setDir(e.target.value)} aria-label="direction">{DIRECTIONS.map((s) => <option key={s}>{s}</option>)}</select>
        </div>
        <div className="inj-row">
          grade <select value={rel} onChange={(e) => setRel(e.target.value)} aria-label="reliability">{"ABCDEF".split("").map((s) => <option key={s}>{s}</option>)}</select>
          <select value={cred} onChange={(e) => setCred(e.target.value)} aria-label="credibility">{"123456".split("").map((s) => <option key={s}>{s}</option>)}</select>
          <button type="button" className="primary" data-testid="ds-plant" onClick={plant}>Send to {hello.player}</button>
        </div>
      </div>
    </fieldset>
  );
}

export function DsApp() {
  const { hello, state: live, error, connect } = useDs();
  const state = useThrottled(live, 1000);
  const [pick, setPickState] = useState<Pick | null>(null);
  const pickRef = useRef<Pick | null>(null);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);
  const gnssCount = useRef(0);
  useEffect(() => { connect(); }, [connect]);
  const cfg = useMemo(() => hello && { bbox: hello.bbox, basemap_kind: hello.basemap_kind, places: hello.places, routes: hello.routes }, [hello]);
  const { ref, map } = useKohraMap(cfg);

  const setPick = (p: Pick | null) => { pickRef.current = p; setPickState(p); };
  const notify: Notify = (text, ok) => setNote({ text, ok });
  useEffect(() => {
    if (!note) return;
    const id = setTimeout(() => setNote(null), 5000);
    return () => clearTimeout(id);
  }, [note]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setPick(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => { if (map) map.getCanvas().style.cursor = pick ? "crosshair" : ""; }, [map, pick]);

  useEffect(() => {
    if (!map) return;
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const p = pickRef.current;
      const { hello: h, state: s } = useDs.getState();
      if (!p || !h || !s) return;
      setPick(null);
      const lonlat: LonLat = [Number(e.lngLat.lng.toFixed(5)), Number(e.lngLat.lat.toFixed(5))];
      if (p.kind === "jammer_add") {
        const n = h.nets.find((x) => x.id === p.net) ?? h.nets[0];
        const id = nextId("J", s.jammers.map((j) => j.id));
        void inject("jammer_add", { id, lonlat, power_dbm: 47, antenna_m: 6, freq_mhz: n.freq_mhz, bandwidth_khz: n.bandwidth_khz,
          mode: "continuous" }, `Jammer ${id} placed on the ${n.id} net`, notify);
      } else if (p.kind === "jammer_move") {
        void inject("jammer_move", { id: p.id, lonlat }, `Jammer ${p.id} moved`, notify);
      } else {
        gnssCount.current += 1;
        const id = `G-${gnssCount.current}`;
        void inject("gnss_zone_add", { id, lonlat, radius_m: 800, bearing_deg: 45, rate_mps: 2, max_offset_m: 400, duration_s: 300 },
          `GNSS spoofing zone ${id} placed`, notify);
      }
    };
    map.on("click", onClick);
    return () => { map.off("click", onClick); };
  }, [map]);

  useEffect(() => {
    if (!map || !state) return;
    setGeo(map, "rings", {
      type: "FeatureCollection",
      features: state.jammers.map((j) => ({ type: "Feature", properties: { on: j.emitting }, geometry: { type: "LineString", coordinates: circle(j.lonlat, j.radius_m) } })),
    }, { id: "rings", type: "line", source: "rings", paint: { "line-color": "#d01c1c", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": ["case", ["get", "on"], 0.9, 0.35] } });
    setGeo(map, "links", {
      type: "FeatureCollection",
      features: state.links.map((l) => ({
        type: "Feature", properties: { colour: sinrColour(l.sinr_db, state.theta_db), dash: l.net === "BN" },
        geometry: { type: "LineString", coordinates: [l.a_lonlat, l.b_lonlat] },
      })),
    }, { id: "links", type: "line", source: "links", paint: { "line-color": ["get", "colour"], "line-width": 3, "line-opacity": 0.85 } });
    setPoints(map, "truth", [
      ...state.units.filter((u) => u.strength > 0).map((u) => ({
        key: `u/${u.id}`, lonlat: u.lonlat, props: {},
        img: unitImage(u.sidc, { uniqueDesignation: u.callsign || u.id, additionalInformation: `${Math.round(u.strength)}%` }),
      })),
      ...state.jammers.map((j) => ({
        key: `j/${j.id}`, lonlat: j.lonlat, props: {}, opacity: j.active ? 1 : 0.4,
        img: unitImage("SHGPUUMSE-C----", { uniqueDesignation: j.id, additionalInformation: j.emitting ? "EMITTING" : j.active ? "idle" : "off" }),
      })),
    ]);
  }, [map, state]);

  if (error && !hello) return <div className="fatal">{error}</div>;
  const paused = live?.paused ?? false;
  const control = async (body: Record<string, unknown>) => {
    const r = await dsPost("/api/ds/control", body);
    if (!r.ok) notify(`Refused: ${errorText(r.data, r.status)}`, false);
  };
  const startLabel = !live ? "..." : live.endex ? "ENDEX" : paused ? (live.tick === 0 ? "Start exercise" : "Resume") : "Pause";
  return (
    <div className="ds">
      <header className="topbar">
        <span className="title">KOHRA · Directing Staff</span>
        <span className="clock" data-testid="ds-clock">{live?.clock ?? "--:--:--"}</span>
        <button type="button" className={`ctl ${paused ? "go" : "hold"}`} data-testid="ds-start" disabled={!live || live.endex}
          onClick={() => void control({ paused: !paused })}>{startLabel}</button>
        <label className="ctl-speed">Speed
          <select data-testid="ds-speed" value={String(live?.speed || 1)} disabled={!live || live.endex}
            onChange={(e) => void control({ speed: Number(e.target.value) })}>
            {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
          </select>
        </label>
        <span className="classif">{hello?.classification}</span>
        {hello?.synthetic && <span className="synthetic">SYNTHETIC TERRAIN</span>}
        {live?.endex && <span className="endex">ENDEX · {live.final_hash?.slice(0, 16)}</span>}
        {live?.endex && (
          <a className="ctl aar" data-testid="ds-aar" href={`/api/ds/aar?t=${encodeURIComponent(token())}`} target="_blank" rel="noopener">
            After-action review
          </a>
        )}
      </header>
      {error && hello && <div className="endex-banner warn">{error}</div>}
      <div className="ds-body">
        <div ref={ref} className="map" />
        <aside className="ds-side">
          {pick && <div className="pick-hint" data-testid="ds-pick-hint">Click the map to {pick.kind === "jammer_move" ? `move ${pick.id}` : pick.kind === "jammer_add" ? "place the jammer" : "centre the spoofing zone"}. Esc cancels.</div>}
          {note && <div className={`note ${note.ok ? "ok" : "bad"}`} data-testid="ds-note">{note.text}</div>}
          {hello && live && (
            <details open>
              <summary>Injects</summary>
              <InjectPanel hello={hello} state={live} setPick={setPick} notify={notify} />
            </details>
          )}
          <details open>
            <summary>Trainee decisions</summary>
            <Decisions events={live?.events ?? []} />
          </details>
          <details open>
            <summary>Links ({hello?.player ?? "HQ"} to each member)</summary>
            <table className="links"><tbody>
              {live?.links.map((l) => (
                <tr key={l.net + l.b}><td>{l.net}</td><td>{l.b}</td>
                  <td style={{ color: sinrColour(l.sinr_db, live.theta_db), fontWeight: 600 }}>{l.sinr_db.toFixed(1)} dB</td></tr>
              ))}
            </tbody></table>
          </details>
          <details open>
            <summary>Events</summary>
            <ol className="events">
              {live?.events.filter((e) => EVENT_KINDS.has(e.kind)).slice().reverse().map((e, i) => (
                <li key={i}><b>{e.clock}</b> <span className="detail">{describe(e)}</span></li>
              ))}
            </ol>
          </details>
        </aside>
      </div>
    </div>
  );
}
