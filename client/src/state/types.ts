// Mirrors server/kohra/wire.py (player half and DS half).
export type LonLat = [number, number];
export type Precedence = "FLASH" | "IMMEDIATE" | "PRIORITY" | "ROUTINE";

export interface Place { name: string; kind: string; lonlat: LonLat }
export interface Route { name: string; points: LonLat[] }

export interface GridAffine { lonlat_to_grid_m: number[]; grid_m_to_lonlat: number[] }

export interface PlayerHello {
  type: "hello"; role: "player"; title: string; classification: string; callsign: string;
  stations: { callsign: string; nets: string[] }[]; nets: { id: string; name: string }[];
  places: Place[]; routes: Route[]; bbox: [number, number, number, number]; grid_affine: GridAffine;
  start_clock: string; duration_ticks: number; tick_seconds: number; synthetic: boolean;
  basemap_kind: "vector" | "raster"; labels: Record<string, string>; own_sidc: string;
}

export interface Radio {
  type: "radio"; msg_id: string; tick: number; clock: string; net: string; sender: string; to: string;
  precedence: Precedence; text: string; fields: Record<string, string | null>; grade: string | null;
  partial: boolean; contact_no: string | null; direction: "in" | "out";
}

export interface Status {
  type: "status"; tick: number; clock: string; hq_lonlat: LonLat; last_heard: Record<string, number>;
  speed: number; paused: boolean; endex: boolean; final_hash: string | null;
}

export interface OrderResult { type: "order_result"; ok: boolean; client_seq: number; reason: string | null }

export interface DsNet { id: string; name: string; freq_mhz: number; bandwidth_khz: number }

export interface DsHello {
  type: "hello"; role: "ds"; title: string; classification: string; places: Place[]; routes: Route[];
  bbox: [number, number, number, number]; synthetic: boolean; basemap_kind: "vector" | "raster";
  start_clock: string; duration_ticks: number; nets: DsNet[]; place_ids: { id: string; name: string }[];
  stations: { callsign: string; nets: string[] }[]; player: string;
}

export interface DsEvent { tick: number; clock: string; kind: string; detail: Record<string, unknown> }

export interface DsState {
  type: "ds_state"; tick: number; clock: string; theta_db: number;
  units: { id: string; side: string; callsign: string; sidc: string; lonlat: LonLat; strength: number; posture: string; status: string }[];
  jammers: { id: string; lonlat: LonLat; active: boolean; emitting: boolean; radius_m: number }[];
  links: { net: string; a: string; b: string; a_lonlat: LonLat; b_lonlat: LonLat; sinr_db: number }[];
  events: DsEvent[];
  endex: boolean; final_hash: string | null; paused: boolean; speed: number;
}
