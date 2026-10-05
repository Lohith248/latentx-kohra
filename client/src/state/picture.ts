// The player's picture, derived ONLY from radio traffic that reached them (parsed fields).
import { gridToLonlat } from "./grid";
import type { GridAffine, LonLat, Radio } from "./types";

export const CONTACT_FADE_S = 600;

export interface MapItem {
  key: string; kind: "hostile" | "own"; lonlat: LonLat; sidc: string; label: string;
  grade: string | null; ageS: number; opacity: number; msg: Radio;
}

const HOSTILE_FN: Record<string, string> = {
  infantry: "UCI---", APC: "UCIZ--", tank: "UCA---", recce: "UCR---", vehicle: "E-----",
  "EW detachment": "UUMSE-", unknown: "------",
};
const ECHELON: Record<string, string> = { single: "-", pair: "-", section: "C", platoon: "D", company: "E" };

export function hostileSidc(unitType: string | null, size: string | null): string {
  return `SHGP${HOSTILE_FN[unitType ?? "unknown"] ?? "------"}${ECHELON[size ?? ""] ?? "-"}----`;
}

export function ageText(s: number): string {
  if (s < 60) return `${Math.max(0, Math.floor(s))}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

export function derivePicture(msgs: Radio[], affine: GridAffine, nowTick: number, tickS: number): MapItem[] {
  const hostiles = new Map<string, MapItem>();
  const own = new Map<string, MapItem>();
  for (const m of msgs) {
    if (m.direction !== "in") continue;
    const t = m.fields.type;
    const grid = m.fields.grid;
    if (!grid) continue;
    const ll = gridToLonlat(affine, grid);
    if (!ll) continue;
    const ageS = (nowTick - m.tick) * tickS;
    if (t === "contact" || t === "intsum") {
      const key = m.contact_no ? `${m.sender}/${m.contact_no}` : m.msg_id;
      if (ageS > CONTACT_FADE_S) { hostiles.delete(key); continue; }
      hostiles.set(key, {
        key, kind: "hostile", lonlat: ll, sidc: hostileSidc(m.fields.unit_type ?? null, m.fields.size ?? null),
        label: m.contact_no ?? m.sender, grade: m.grade, ageS, opacity: Math.max(0.25, 1 - ageS / CONTACT_FADE_S), msg: m,
      });
    } else if (t === "locstat" || t === "sitrep") {
      own.set(m.sender, {
        key: `own/${m.sender}`, kind: "own", lonlat: ll, sidc: "SFGPUCI---D----", label: m.sender, grade: m.grade,
        ageS, opacity: 1, msg: m,
      });
    }
  }
  return [...hostiles.values(), ...own.values()];
}

export type AckState = "awaiting WILCO" | "WILCO" | "SAY AGAIN";

export function ackState(sent: Radio, msgs: Radio[]): AckState {
  for (const m of msgs) {
    if (m.direction !== "in" || m.fields.ref !== sent.msg_id) continue;
    if (m.fields.type === "ack") return "WILCO";
    if (m.fields.type === "say_again") return "SAY AGAIN";
  }
  return "awaiting WILCO";
}

export function sinceText(nowTick: number, tick: number | undefined, tickS: number): string {
  if (tick === undefined) return "never";
  const s = Math.max(0, Math.floor((nowTick - tick) * tickS));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} ago`;
}
