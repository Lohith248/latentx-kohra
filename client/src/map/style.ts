// MapLibre style from same-origin PMTiles (D22): land cover, water, roads, buildings and hillshade only.
// No text layers, POIs or boundaries, and no `glyphs` or `sprite`: names and symbols are canvas images.
import type { StyleSpecification } from "maplibre-gl";

export const CREDITS = [
  "© OpenStreetMap contributors (ODbL)",
  "Basemap: Protomaps",
  "Contains modified Copernicus DEM GLO-30 data, © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA",
  "MapLibre",
  "milsymbol",
];

export function buildStyle(origin: string, basemap: "vector" | "raster"): StyleSpecification {
  const base = `pmtiles://${origin}/tiles/basemap.pmtiles`;
  const dem = `pmtiles://${origin}/tiles/dem.pmtiles`;
  const vectorLayers: StyleSpecification["layers"] = [
    { id: "earth", type: "fill", source: "basemap", "source-layer": "earth", paint: { "fill-color": "#dfe3cf" } },
    {
      id: "landcover", type: "fill", source: "basemap", "source-layer": "landcover",
      paint: { "fill-color": ["match", ["get", "kind"], ["forest", "wood"], "#c3d3ad", ["grassland", "scrub"], "#d5dcbf", "#dde1cc"], "fill-opacity": 0.7 },
    },
    {
      id: "landuse", type: "fill", source: "basemap", "source-layer": "landuse",
      paint: {
        "fill-color": ["match", ["get", "kind"], ["forest", "wood", "nature_reserve"], "#bccfa6",
          ["residential", "commercial", "industrial", "retail"], "#d9d2c8", ["farmland", "orchard", "grass", "meadow"], "#d8deb9", "#dcdfcb"],
        "fill-opacity": 0.75,
      },
    },
    { id: "water", type: "fill", source: "basemap", "source-layer": "water", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "#9cbfe0" } },
    {
      id: "waterway", type: "line", source: "basemap", "source-layer": "water", filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": "#9cbfe0", "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.5, 15, 2] },
    },
    {
      id: "roads", type: "line", source: "basemap", "source-layer": "roads",
      paint: {
        "line-color": ["match", ["get", "kind"], "highway", "#e8b86b", "major_road", "#f2d79b", "#ffffff"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, ["match", ["get", "kind"], ["highway", "major_road"], 1.2, 0.4], 15, ["match", ["get", "kind"], ["highway", "major_road"], 5, 2]],
      },
    },
    { id: "buildings", type: "fill", source: "basemap", "source-layer": "buildings", minzoom: 13, paint: { "fill-color": "#c9c0b5", "fill-opacity": 0.8 } },
  ];
  const rasterLayers: StyleSpecification["layers"] = [{ id: "basemap-raster", type: "raster", source: "basemap" }];
  return {
    version: 8,
    sources: {
      basemap: basemap === "vector"
        ? { type: "vector", url: base, attribution: "" }
        : { type: "raster", url: base, tileSize: 256, attribution: "" },
      dem: { type: "raster-dem", url: dem, encoding: "terrarium", tileSize: 256, attribution: "" },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#e4e6d8" } },
      ...(basemap === "vector" ? vectorLayers : rasterLayers),
      {
        id: "hillshade", type: "hillshade", source: "dem",
        paint: { "hillshade-exaggeration": 0.55, "hillshade-shadow-color": "#4a4f3a", "hillshade-highlight-color": "#ffffff" },
      },
    ],
  };
}
