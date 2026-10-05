// Read-only truth view for the Directing Staff: truth units, jammers and per-member link SINR. No editing.
import { useEffect, useMemo, useRef, useState } from "react";
import { unitImage } from "../map/symbols";
import { circle, setGeo, setPoints, useKohraMap } from "../map/useMap";
import { useDs } from "../state/store";

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

export function DsApp() {
  const { hello, state: live, error, connect } = useDs();
  const state = useThrottled(live, 1000);
  useEffect(() => { connect(); }, [connect]);
  const cfg = useMemo(() => hello && { bbox: hello.bbox, basemap_kind: hello.basemap_kind, places: hello.places, routes: hello.routes }, [hello]);
  const { ref, map } = useKohraMap(cfg);

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

  if (error) return <div className="fatal">{error}</div>;
  return (
    <div className="ds">
      <header className="topbar">
        <span className="title">KOHRA · DS truth view (read-only)</span>
        <span className="clock" data-testid="ds-clock">{state?.clock ?? "--:--:--"}</span>
        <span className="classif">{hello?.classification}</span>
        {hello?.synthetic && <span className="synthetic">SYNTHETIC TERRAIN</span>}
        {state?.endex && <span className="endex">ENDEX · {state.final_hash?.slice(0, 16)}</span>}
      </header>
      <div className="ds-body">
        <div ref={ref} className="map" />
        <aside className="ds-side">
          <h3>Links (TIGER → member)</h3>
          <table className="links"><tbody>
            {state?.links.map((l) => (
              <tr key={l.net + l.b}><td>{l.net}</td><td>{l.b}</td>
                <td style={{ color: sinrColour(l.sinr_db, state.theta_db), fontWeight: 600 }}>{l.sinr_db.toFixed(1)} dB</td></tr>
            ))}
          </tbody></table>
          <h3>Injects and decision points</h3>
          <ol className="events">
            {state?.events.filter((e) => ["inject_fired", "inject_failed", "decision_point", "red_rule", "fire_impact"].includes(e.kind)).slice().reverse().map((e, i) => (
              <li key={i}><b>{e.clock}</b> {e.kind}{" "}
                <span className="detail">{e.kind === "decision_point" ? String(e.detail.describes) : e.kind.startsWith("inject") ? `${e.detail.kind}${e.detail.late ? " (late)" : ""}` : ""}</span></li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  );
}
