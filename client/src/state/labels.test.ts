import { describe, expect, it } from "vitest";
import { gradeBand, orderName, sinrWord } from "./labels";

describe("plain-language labels", () => {
  it("bands a grade by the worse of reliability and credibility", () => {
    expect(gradeBand("A1")).toBe("good");
    expect(gradeBand("B2")).toBe("good");
    expect(gradeBand("C3")).toBe("doubt");
    expect(gradeBand("B3")).toBe("doubt");
    expect(gradeBand("D2")).toBe("poor");
    expect(gradeBand("A6")).toBe("poor");
  });

  it("names link quality with the map's colour bands", () => {
    expect(sinrWord(9.1, 6)).toBe("OK");
    expect(sinrWord(6, 6)).toBe("degraded");
    expect(sinrWord(5.9, 6)).toBe("jammed");
  });

  it("writes order kinds the way a reader says them", () => {
    expect(orderName("FIRE_MISSION")).toBe("Fire mission");
    expect(orderName("MOVE")).toBe("Move");
  });
});

describe("declutter", () => {
  it("leaves separate symbols in place and moves a stacked one to a free slot", async () => {
    const { declutter } = await import("../map/declutter");
    const off = declutter([[100, 100], [300, 100], [102, 101]]);
    expect(off[0]).toEqual([0, 0]);
    expect(off[1]).toEqual([0, 0]);
    expect(Math.hypot(102 + off[2][0] - 100, 101 + off[2][1] - 100)).toBeGreaterThanOrEqual(46);
  });
});
