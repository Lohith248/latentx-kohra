import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

export const PORT = 8799;
export const ROOT = path.resolve(import.meta.dirname, "..");
export const TOKENS = path.join(ROOT, ".kohra", "e2e-tokens.json");
const py = process.env.KOHRA_PY ?? "uv run python";

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, ...devices["Desktop Chrome"], viewport: { width: 1500, height: 900 } },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: {
    command: `${py} -m kohra.cli run --port ${PORT} --speed 4 --ticks 5000 --tokens "${TOKENS}" --log "${path.join(ROOT, "runs", `e2e-${Date.now()}.sqlite`)}"`,
    cwd: ROOT,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: { PYTHONHASHSEED: "0", PYTHONPATH: path.join(ROOT, "server") },
  },
});
