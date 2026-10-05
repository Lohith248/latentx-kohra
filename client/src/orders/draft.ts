// Order draft and readiness rules (D14): nothing is sent without a confidence and a relied-on choice.
import type { Precedence } from "../state/types";

export type OrderKind = "MOVE" | "HALT" | "HOLD" | "OBSERVE" | "WITHDRAW" | "REQUEST_SITREP" | "FIRE_MISSION" | "TEXT";
export const GRID_KINDS: OrderKind[] = ["MOVE", "OBSERVE", "WITHDRAW", "FIRE_MISSION"];

export interface Draft {
  to: string | null;
  kind: OrderKind | null;
  grid: string | null;
  speed: "tactical" | "fast";
  precedence: Precedence;
  confidence: number | null; // null until the slider is touched
  reliedOn: string[];
  reliedNone: boolean;
  text: string;
}

export const emptyDraft = (): Draft => ({
  to: null, kind: null, grid: null, speed: "tactical", precedence: "PRIORITY", confidence: null,
  reliedOn: [], reliedNone: false, text: "",
});

export function kindsFor(to: string | null, bn: string): OrderKind[] {
  if (!to) return [];
  return to === bn ? ["FIRE_MISSION", "TEXT"] : ["MOVE", "HALT", "HOLD", "OBSERVE", "WITHDRAW", "REQUEST_SITREP", "TEXT"];
}

/** Missing steps, in order. Empty means Send is enabled. */
export function missing(d: Draft): string[] {
  const out: string[] = [];
  if (!d.to) out.push("addressee");
  if (!d.kind) out.push("order");
  if (d.kind === "TEXT") {
    if (!d.text.trim()) out.push("text");
    return out;
  }
  if (d.kind && GRID_KINDS.includes(d.kind) && !d.grid) out.push("grid");
  if (d.confidence === null) out.push("confidence");
  if (!d.reliedNone && d.reliedOn.length === 0) out.push("relied-on");
  return out;
}

export function toWire(d: Draft, seq: number, netFor: (to: string) => string): Record<string, unknown> {
  if (d.kind === "TEXT") {
    return { type: "text", to: d.to, net: netFor(d.to!), text: d.text.trim(), precedence: d.precedence, client_seq: seq };
  }
  return {
    type: "order", to: d.to, kind: d.kind, grid: d.kind && GRID_KINDS.includes(d.kind) ? d.grid : null,
    speed: d.kind === "MOVE" ? d.speed : null, precedence: d.precedence, confidence: d.confidence,
    relied_on: d.reliedNone ? [] : d.reliedOn, client_seq: seq,
  };
}
