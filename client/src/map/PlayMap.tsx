import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";
import { gridToLonlat, lonlatToGrid } from "../state/grid";
import { ageText, derivePicture } from "../state/picture";
import { usePlayer } from "../state/store";
import { unitImage } from "./symbols";
import { setGeo, setPoints, useKohraMap } from "./useMap";

export function PlayMap() {
  const hello = usePlayer((s) => s.hello);
  const status = usePlayer((s) => s.status);
  const msgs = usePlayer((s) => s.msgs);
  const picking = usePlayer((s) => s.picking);
  const grid = usePlayer((s) => s.draft.grid);
  const cfg = useMemo(() => hello && { bbox: hello.bbox, basemap_kind: hello.basemap_kind, places: hello.places, routes: hello.routes }, [hello]);
  const { ref, map, ready } = useKohraMap(cfg);
  const pickingRef = useRef(picking);
  pickingRef.current = picking;
  // Re-render symbols on new traffic, and every 10 s of mission time so age stamps stay live.
  const ageBucket = status ? Math.floor(status.tick / 10) : 0;

  useEffect(() => {
    if (!map || !hello || !status) return;
    const items = derivePicture(msgs, hello.grid_affine, status.tick, hello.tick_seconds);
    setPoints(map, "picture", [
      ...items.map((it) => ({
        key: it.key, lonlat: it.lonlat, opacity: it.opacity, props: { msg: it.msg.msg_id, kind: it.kind },
        img: unitImage(it.sidc, { uniqueDesignation: it.label, additionalInformation: ageText(it.ageS), ...(it.grade ? { evaluationRating: it.grade } : {}) }),
      })),
      {
        key: "own/hq", lonlat: status.hq_lonlat, props: { kind: "hq" },
        img: unitImage(hello.own_sidc, { uniqueDesignation: hello.callsign, additionalInformation: "own GNSS" }),
      },
    ]);
  }, [map, hello, msgs.length, ageBucket, status?.hq_lonlat[0], status?.hq_lonlat[1]]);

  useEffect(() => {
    if (!map || !hello) return;
    const ll = grid ? gridToLonlat(hello.grid_affine, grid) : null;
    setGeo(map, "target", { type: "FeatureCollection", features: ll ? [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: ll } }] : [] },
      { id: "target", type: "circle", source: "target", paint: { "circle-radius": 9, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#b00020", "circle-stroke-width": 3 } });
  }, [map, hello, grid]);

  useEffect(() => {
    if (!map || !hello) return;
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const st = usePlayer.getState();
      if (pickingRef.current) {
        st.setDraft({ grid: lonlatToGrid(hello.grid_affine, [e.lngLat.lng, e.lngLat.lat]) });
        st.setPicking(false);
        return;
      }
      const f = map.queryRenderedFeatures(e.point, { layers: ["picture"] })[0];
      const id = f?.properties?.msg as string | undefined;
      const m = id && st.msgs.find((x) => x.msg_id === id);
      if (!m) return;
      const el = document.createElement("div");
      el.className = "popup";
      const head = document.createElement("div");
      head.className = "popup-head";
      head.textContent = `${m.clock} · ${m.net} · ${m.sender}${m.grade ? ` · ${m.grade}` : ""}${m.partial ? " · PARTIAL" : ""}`;
      const body = document.createElement("div");
      body.textContent = m.text;
      el.append(head, body);
      new maplibregl.Popup({ closeButton: true, maxWidth: "320px" }).setLngLat(e.lngLat).setDOMContent(el).addTo(map);
    };
    map.on("click", onClick);
    return () => { map.off("click", onClick); };
  }, [map, hello]);

  useEffect(() => { if (map) map.getCanvas().style.cursor = picking ? "crosshair" : ""; }, [map, picking]);

  return (
    <div className="map-wrap">
      <div ref={ref} className="map" data-testid="map" />
      {!ready && <div className="map-loading" data-testid="map-loading">Loading terrain…</div>}
    </div>
  );
}
