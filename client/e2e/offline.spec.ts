import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { PORT } from "../playwright.config";
import { tokens, waitForMap } from "./helpers";

const ORIGIN = `http://127.0.0.1:${PORT}`;

// Strings in the bundle that look like URLs but are never fetched: XML namespaces, licence and source
// comments, error-doc links, and attribution text.
const ALLOWED_URL_PREFIXES = [
  "http://www.w3.org/", "https://react.dev/errors/", "https://maplibre.org/", "https://github.com/maplibre/",
  "https://github.com/mapbox/", "https://github.com/protomaps/", "http://www.spatialillusions.com",
];

for (const pagePath of ["/play", "/ds"]) {
  test(`${pagePath} loads fully offline`, async ({ page }) => {
    const external: string[] = [];
    const consoleErrors: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
    page.on("pageerror", (e) => consoleErrors.push(String(e)));
    await page.route("**/*", (route) => {
      const url = route.request().url();
      if (url.startsWith(ORIGIN) || url.startsWith("ws://127.0.0.1") || url.startsWith("blob:") || url.startsWith("data:")) {
        return route.continue();
      }
      external.push(url);
      return route.abort();
    });
    const t = tokens();
    await page.goto(`${pagePath}?t=${pagePath === "/ds" ? t.ds : t.player}`);
    await waitForMap(page, pagePath === "/ds" ? "truth" : "picture");
    await expect(page.locator(".maplibregl-ctrl-attrib")).toContainText("OpenStreetMap contributors");
    await expect(page.locator(".maplibregl-ctrl-attrib")).toContainText("Copernicus DEM GLO-30");
    expect(external).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
}

test("built client contains no fetchable external URLs", () => {
  const dist = path.resolve(import.meta.dirname, "..", "dist");
  const bad: string[] = [];
  for (const f of fs.readdirSync(path.join(dist, "assets"))) {
    const text = fs.readFileSync(path.join(dist, "assets", f), "utf8");
    for (const m of text.matchAll(/https?:\/\/[A-Za-z0-9./_%-]+/g)) {
      if (!ALLOWED_URL_PREFIXES.some((p) => m[0].startsWith(p))) bad.push(`${f}: ${m[0]}`);
    }
  }
  const html = fs.readFileSync(path.join(dist, "index.html"), "utf8");
  for (const m of html.matchAll(/https?:\/\/[^\s"'<>]+/g)) bad.push(`index.html: ${m[0]}`);
  expect(bad).toEqual([]);
});
