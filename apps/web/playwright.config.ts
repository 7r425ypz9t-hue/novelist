import { defineConfig, devices } from "@playwright/test";

// E2E against the real stack: the FastAPI process serves the built control panel and a fresh SQLite DB.
const db = `/tmp/nis-e2e-${Date.now()}`;
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:8765", locale: "ar", trace: "retain-on-failure" },
  // NFR06: RTL behaviour across engines. Locally only Chromium is installed; CI runs the full matrix via E2E_BROWSERS.
  projects: (process.env.E2E_BROWSERS || "chromium").split(",").map((b) => b.trim()).map((name) =>
    name === "msedge" ? { name, use: { ...devices["Desktop Edge"], channel: "msedge" } }
      : name === "firefox" ? { name, use: { ...devices["Desktop Firefox"] } }
      : { name: "chromium", use: { ...devices["Desktop Chrome"] } }),
  webServer: {
    command: `cd ../api && NIS_DATABASE_URL=sqlite:///${db}/nis.db NIS_DATA_DIR=${db}/data NIS_RATE_LIMIT_PER_MINUTE=0 NIS_AUTH_RATE_LIMIT_PER_MINUTE=0 ${process.env.NIS_PYTHON || "python"} -m nis.cli serve --port 8765`,
    url: "http://127.0.0.1:8765/v1/health",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
