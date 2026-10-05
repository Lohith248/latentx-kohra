import { describe, expect, it } from "vitest";
import { emptyDraft, missing, toWire } from "../orders/draft";
import { buildStyle } from "../map/style";
import { gridToLonlat, lonlatToGrid } from "./grid";
import { ackState, derivePicture, hostileSidc } from "./picture";
import type { GridAffine, Radio } from "./types";

// Affine for a 1 m = 1e-5 deg toy projection: lon/lat (76.1, 11.2) is grid origin.
const A: GridAffine = {
  lonlat_to_grid_m: [100000, 0, -7610000, 0, 100000, -1120000],
  grid_m_to_lonlat: [0.00001, 0, 76.1, 0, 0.00001, 11.2],
};

const radio = (p: Partial<Radio>): Radio => ({
  type: "radio", msg_id: "M-AAAA", tick: 0, clock: "06:00:00", net: "COY", sender: "TIGER-1", to: "TIGER",
  precedence: "PRIORITY", text: "", fields: {}, grade: "B3", partial: false, contact_no: null, direction: "in", ...p,
});

describe("grid", () => {
  it("round-trips through the affine", () => {
    expect(lonlatToGrid(A, [76.1 + 0.11549, 11.2 + 0.07201])).toBe("115 072");
    const ll = gridToLonlat(A, "115 072")!;
    expect(lonlatToGrid(A, ll)).toBe("115 072");
    expect(gridToLonlat(A, "11 072")).toBeNull();
  });
});

describe("order readiness (D14)", () => {
  it("needs addressee, order, grid, confidence and an explicit relied-on choice", () => {
    const d = emptyDraft();
    expect(missing(d)).toEqual(["addressee", "order", "confidence", "relied-on"]);
    const move = { ...d, to: "TIGER-1", kind: "MOVE" as const };
    expect(missing(move)).toEqual(["grid", "confidence", "relied-on"]);
    expect(missing({ ...move, grid: "010 020", confidence: 0 })).toEqual(["relied-on"]);
    expect(missing({ ...move, grid: "010 020", confidence: 0, reliedNone: true })).toEqual([]);
    expect(missing({ ...move, grid: "010 020", confidence: 40, reliedOn: ["M-1"] })).toEqual([]);
    expect(missing({ ...d, to: "TIGER-1", kind: "HALT", confidence: 10, reliedNone: true })).toEqual([]);
  });
  it("serialises confidence and relied_on, never for free text", () => {
    const w = toWire({ ...emptyDraft(), to: "TIGER-1", kind: "MOVE", grid: "010 020", confidence: 70, reliedOn: ["M-1"] }, 3, () => "COY");
    expect(w).toMatchObject({ type: "order", confidence: 70, relied_on: ["M-1"], grid: "010 020", speed: "tactical", client_seq: 3 });
    const t = toWire({ ...emptyDraft(), to: "ANVIL", kind: "TEXT", text: " hello " }, 4, () => "BN");
    expect(t).toEqual({ type: "text", to: "ANVIL", net: "BN", text: "hello", precedence: "PRIORITY", client_seq: 4 });
  });
});

describe("picture from parsed traffic only", () => {
  it("places contacts and own platoons from grids, fading with age", () => {
    const msgs = [
      radio({ msg_id: "M-1", tick: 0, contact_no: "C-1-01", fields: { type: "contact", grid: "010 020", unit_type: "APC", size: "platoon" } }),
      radio({ msg_id: "M-2", tick: 100, fields: { type: "locstat", grid: "005 005" } }),
      radio({ msg_id: "M-3", tick: 100, fields: { type: "contact", grid: null } }),
    ];
    const items = derivePicture(msgs, A, 300, 1);
    expect(items.map((i) => i.kind)).toEqual(["hostile", "own"]);
    expect(items[0].sidc).toBe("SHGPUCIZ--D----");
    expect(items[0].opacity).toBeCloseTo(0.5);
    expect(derivePicture(msgs, A, 700, 1).map((i) => i.kind)).toEqual(["own"]);
    expect(hostileSidc("tank", "company")).toBe("SHGPUCA---E----");
  });
  it("tracks WILCO / SAY AGAIN by ref", () => {
    const sent = radio({ msg_id: "M-9", direction: "out" });
    expect(ackState(sent, [])).toBe("awaiting WILCO");
    expect(ackState(sent, [radio({ fields: { type: "ack", ref: "M-9" } })])).toBe("WILCO");
    expect(ackState(sent, [radio({ fields: { type: "say_again", ref: "M-9" } })])).toBe("SAY AGAIN");
  });
});

describe("map style (D22)", () => {
  it("has no glyphs, sprite, text, POI or boundary layers and only same-origin sources", () => {
    for (const kind of ["vector", "raster"] as const) {
      const s = buildStyle("http://127.0.0.1:8765", kind);
      expect(s.glyphs).toBeUndefined();
      expect(s.sprite).toBeUndefined();
      const json = JSON.stringify(s);
      expect(json).not.toMatch(/text-field|"places"|"pois"|"boundaries"/);
      for (const src of Object.values(s.sources)) expect((src as { url: string }).url).toMatch(/^pmtiles:\/\/http:\/\/127\.0\.0\.1:8765\/tiles\//);
      expect(s.layers.some((l) => l.type === "hillshade")).toBe(true);
    }
  });
});
