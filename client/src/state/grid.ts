// Local 6-figure grid (D3) via the server-supplied affine fit over the scenario bbox.
import type { GridAffine, LonLat } from "./types";

export function lonlatToGrid(a: GridAffine, [lon, lat]: LonLat): string {
  const m = a.lonlat_to_grid_m;
  const gx = m[0] * lon + m[1] * lat + m[2];
  const gy = m[3] * lon + m[4] * lat + m[5];
  const e = ((Math.floor(gx / 100) % 1000) + 1000) % 1000;
  const n = ((Math.floor(gy / 100) % 1000) + 1000) % 1000;
  return `${String(e).padStart(3, "0")} ${String(n).padStart(3, "0")}`;
}

export function gridToLonlat(a: GridAffine, grid: string): LonLat | null {
  const g = /^(\d{3}) (\d{3})$/.exec(grid.trim());
  if (!g) return null;
  const x = (Number(g[1]) + 0.5) * 100;
  const y = (Number(g[2]) + 0.5) * 100;
  const m = a.grid_m_to_lonlat;
  return [m[0] * x + m[1] * y + m[2], m[3] * x + m[4] * y + m[5]];
}
