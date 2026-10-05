import { expect, type Page } from "@playwright/test";
import fs from "node:fs";
import { TOKENS } from "../playwright.config";

export function tokens(): { player: string; ds: string } {
  return JSON.parse(fs.readFileSync(TOKENS, "utf8"));
}

/** Wait until the map is idle with the hillshade layer and at least one rendered unit symbol. */
export async function waitForMap(page: Page, layer: string): Promise<void> {
  await expect.poll(async () => page.evaluate((lyr) => {
    const m = window.__kohraMap;
    if (!m || !m.getLayer("hillshade") || !m.getLayer(lyr)) return false;
    return m.loaded() && m.areTilesLoaded() && m.queryRenderedFeatures({ layers: [lyr] }).length > 0;
  }, layer), { timeout: 60_000 }).toBe(true);
  await page.evaluate(() => new Promise<void>((res) => {
    const m = window.__kohraMap!;
    if (m.loaded() && m.areTilesLoaded()) res();
    else m.once("idle", () => res());
  }));
}
