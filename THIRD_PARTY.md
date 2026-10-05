# Third-party software and data

No AGPL, GPL, SSPL, BUSL or non-commercial licence appears anywhere in the dependency tree. The only
weak-copyleft item is `certifi` (MPL-2.0, file-level; unmodified CA bundle, pulled in by `rasterio` and
`httpx` in the offline/dev tooling only). Regenerate the lists below after any dependency change
(`uv.lock` and `client/package-lock.json` pin every version).

## Data

| Data | Licence / terms | Where used |
| --- | --- | --- |
| Copernicus DEM GLO-30, tile `N11_00_E076_00` | Copernicus DEM licence (free, attribution required): "Contains modified Copernicus DEM GLO-30 data, © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA" | `data/raw` → `terrain.npz`, `dem.pmtiles` (never committed) |
| OpenStreetMap via the Protomaps daily build | ODbL 1.0, "© OpenStreetMap contributors" | `data/tiles/basemap.pmtiles` (never committed) |
| Protomaps basemap schema | BSD-3-Clause / attribution "Basemap: Protomaps" | basemap tiles |

The client's attribution control always shows: © OpenStreetMap contributors (ODbL) · Basemap: Protomaps ·
the Copernicus DEM line above · MapLibre · milsymbol.

## Tools (downloaded once into `.tools/`, never committed)

| Tool | Version | Licence |
| --- | --- | --- |
| go-pmtiles CLI (protomaps/go-pmtiles) | 1.31.2 (SHA-256 verified) | BSD-3-Clause |

## Python (server, offline pipeline, dev)

| Package | Version | Licence | Scope |
| --- | --- | --- | --- |
| fastapi | 0.115.12 | MIT | runtime |
| starlette | 0.46.2 | BSD-3-Clause | runtime |
| uvicorn | 0.34.2 | BSD-3-Clause | runtime |
| websockets | 15.0.1 | BSD-3-Clause | runtime |
| h11 | 0.16.0 | MIT | runtime |
| anyio | 4.15.1 | MIT | runtime |
| idna | 3.20 | BSD-3-Clause | runtime |
| click | 8.5.0 | BSD-3-Clause | runtime |
| colorama | 0.4.6 | BSD-3-Clause | runtime (Windows) |
| numpy | 2.2.5 | BSD-3-Clause | runtime |
| pydantic | 2.11.4 | MIT | runtime |
| pydantic-core | 2.33.2 | MIT | runtime |
| annotated-types | 0.8.0 | MIT | runtime |
| typing-extensions | 4.16.0 | PSF-2.0 | runtime |
| typing-inspection | 0.4.4 | MIT | runtime |
| pyyaml | 6.0.2 | MIT | runtime |
| pyproj | 3.7.1 | MIT (bundles PROJ, MIT) | runtime |
| certifi | 2026.7.22 | MPL-2.0 | via pyproj/rasterio/httpx |
| rasterio | 1.4.3 | BSD-3-Clause (bundles GDAL, MIT) | `[terrain]` extra |
| affine | 3.0.1 | BSD-3-Clause | `[terrain]` extra |
| attrs | 26.1.0 | MIT | `[terrain]` extra |
| click-plugins | 1.1.1.2 | BSD-3-Clause | `[terrain]` extra |
| cligj | 0.7.2 | BSD-3-Clause | `[terrain]` extra |
| pyparsing | 3.3.3 | MIT | `[terrain]` extra |
| pillow | 11.2.1 | MIT-CMU (HPND) | `[terrain]` extra |
| pmtiles (Python) | 3.4.1 | BSD-3-Clause | `[terrain]` extra |
| pytest | 8.3.5 | MIT | dev |
| iniconfig | 2.3.0 | MIT | dev |
| pluggy | 1.6.0 | MIT | dev |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | dev |
| mypy | 1.15.0 | MIT | dev |
| mypy-extensions | 1.1.0 | MIT | dev |
| ruff | 0.11.8 | MIT | dev |
| httpx | 0.28.1 | BSD-3-Clause | dev |
| httpcore | 1.0.9 | BSD-3-Clause | dev |
| types-PyYAML | 6.0.12.20250402 | Apache-2.0 | dev |

## JavaScript (client runtime bundle)

| Package | Version | Licence |
| --- | --- | --- |
| react / react-dom | 19.3.0 | MIT |
| scheduler | 0.28.0 | MIT |
| zustand | 5.0.15 | MIT |
| maplibre-gl | 5.24.0 | BSD-3-Clause |
| @maplibre/maplibre-gl-style-spec | 24.10.0 | ISC |
| @maplibre/geojson-vt | 6.1.2 | ISC |
| @maplibre/mlt | 1.3.0 | MIT OR Apache-2.0 |
| @maplibre/vt-pbf | 4.3.2 | MIT |
| @mapbox/jsonlint-lines-primitives | 2.0.3 | MIT |
| @mapbox/point-geometry | 1.1.0 | ISC |
| @mapbox/tiny-sdf | 2.2.0 | BSD-2-Clause |
| @mapbox/unitbezier | 0.0.1, 1.0.0 | BSD-2-Clause |
| @mapbox/vector-tile | 2.0.5 | BSD-3-Clause |
| @mapbox/whoots-js | 3.1.0 | ISC |
| pmtiles (JS) | 4.5.0 | BSD-3-Clause |
| milsymbol | 2.2.0 | MIT |
| earcut | 3.2.4 | ISC |
| fflate | 0.8.3 | MIT |
| gl-matrix | 3.4.4 | MIT |
| json-stringify-pretty-compact | 4.0.0 | MIT |
| kdbush | 4.1.0 | ISC |
| minimist | 1.2.8 | MIT |
| murmurhash-js | 1.0.0 | MIT |
| pbf | 4.0.2, 5.1.2 | BSD-3-Clause |
| potpack | 2.1.0 | ISC |
| protocol-buffers-schema | 3.6.1 | MIT |
| quickselect | 3.0.0 | ISC |
| resolve-protobuf-schema | 2.1.0 | MIT |
| tinyqueue | 3.0.0 | ISC |
| csstype, @types/react, @types/geojson | (types only) | MIT |

## JavaScript (client dev and test tooling, not shipped)

190 packages; licences: MIT (most), ISC, Apache-2.0 (typescript, @playwright/test, playwright),
BSD-2/3-Clause, MIT-0, CC-BY-4.0 (caniuse-lite data). Key pins: vite 6.4.3, @vitejs/plugin-react 4.7.0,
vitest 3.2.7, typescript 5.9.3, @playwright/test 1.63.0, @types/node 22.15.3.
