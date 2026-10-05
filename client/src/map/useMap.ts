import maplibregl, { type GeoJSONSource, type Map as MlMap } from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import type { Place, Route } from "../state/types";
import { buildStyle, CREDITS } from "./style";
import { labelImage, type Img } from "./symbols";

let protocolAdded = false;

export interface MapCfg { bbox: [number, number, number, number]; basemap_kind: "vector" | "raster"; places: Place[]; routes: Route[] }

declare global { interface Window { __kohraMap?: MlMap } }

export function useKohraMap(cfg: MapCfg | null) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [map, setMap] = useState<MlMap | null>(null);
  useEffect(() => {
    if (!cfg || !ref.current) return;
    if (!protocolAdded) {
      maplibregl.addProtocol("pmtiles", new Protocol().tile);
      protocolAdded = true;
    }
    const [w, s, e, n] = cfg.bbox;
    // Open on the area the scenario names (places + routes), not the whole box.
    const pts = [...cfg.places.map((p) => p.lonlat), ...cfg.routes.flatMap((r) => r.points)];
    const view: [number, number, number, number] = pts.length
      ? [Math.min(...pts.map((p) => p[0])) - 0.01, Math.min(...pts.map((p) => p[1])) - 0.01,
        Math.max(...pts.map((p) => p[0])) + 0.01, Math.max(...pts.map((p) => p[1])) + 0.01]
      : [w, s, e, n];
    const m = new maplibregl.Map({
      container: ref.current, style: buildStyle(location.origin, cfg.basemap_kind), bounds: view,
      fitBoundsOptions: { padding: 30 }, maxBounds: [w - 0.1, s - 0.1, e + 0.1, n + 0.1], attributionControl: false,
      minZoom: 9, maxZoom: 17, dragRotate: false, pitchWithRotate: false,
    });
    m.addControl(new maplibregl.AttributionControl({ compact: false, customAttribution: CREDITS }), "bottom-left");
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    m.on("load", () => {
      m.addSource("routes", {
        type: "geojson",
        data: { type: "FeatureCollection", features: cfg.routes.map((r) => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: r.points } })) },
      });
      m.addLayer({ id: "routes", type: "line", source: "routes", paint: { "line-color": "#8a3b12", "line-width": 2, "line-dasharray": [3, 2], "line-opacity": 0.6 } });
      setPoints(m, "places", cfg.places.map((p) => ({ key: `place/${p.name}`, lonlat: p.lonlat, img: labelImage(p.name), props: {} })));
      window.__kohraMap = m;
      setMap(m);
    });
    return () => { m.remove(); setMap(null); };
  }, [cfg]);
  return { ref, map };
}

export interface Point { key: string; lonlat: [number, number]; img: Img; props: Record<string, unknown>; opacity?: number }

/** Upsert a symbol layer whose icons are canvas images (unit symbols or labels). */
export function setPoints(m: MlMap, id: string, pts: Point[], before?: string): void {
  for (const p of pts) {
    const img = { width: p.img.width, height: p.img.height, data: p.img.data };
    const pr = window.devicePixelRatio > 1 ? 2 : 1;
    if (m.hasImage(p.key)) {
      const cur = m.getImage(p.key);
      if (cur && cur.data.width === img.width && cur.data.height === img.height) m.updateImage(p.key, img);
      else { m.removeImage(p.key); m.addImage(p.key, img, { pixelRatio: pr }); }
    } else m.addImage(p.key, img, { pixelRatio: pr });
  }
  const data: FeatureCollection = {
    type: "FeatureCollection",
    features: pts.map((p) => ({ type: "Feature", properties: { ...p.props, icon: p.key, opacity: p.opacity ?? 1 }, geometry: { type: "Point", coordinates: p.lonlat } })),
  };
  const src = m.getSource(id) as GeoJSONSource | undefined;
  if (src) { src.setData(data); return; }
  m.addSource(id, { type: "geojson", data });
  m.addLayer({
    id, type: "symbol", source: id,
    layout: { "icon-image": ["get", "icon"], "icon-allow-overlap": true, "icon-ignore-placement": true },
    paint: { "icon-opacity": ["get", "opacity"] },
  }, before);
}

export function setGeo(m: MlMap, id: string, data: FeatureCollection, layer: maplibregl.AddLayerObject): void {
  const src = m.getSource(id) as GeoJSONSource | undefined;
  if (src) src.setData(data);
  else { m.addSource(id, { type: "geojson", data }); m.addLayer(layer); }
}

export function circle([lon, lat]: [number, number], radiusM: number, n = 64): [number, number][] {
  const out: [number, number][] = [];
  const dLat = radiusM / 111_320;
  const dLon = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= n; i++) {
    const a = (2 * Math.PI * i) / n;
    out.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return out;
}
