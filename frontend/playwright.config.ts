import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const executablePath =
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ||
  (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: [["list"], ["html", { open: "never" }]],
  projects: [
    { name: "foundation", testMatch: /workflows\.spec\.ts/ },
    {
      name: "enterprise",
      testMatch: /enterprise\.spec\.ts/,
      dependencies: ["foundation"],
      fullyParallel: false,
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:15173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    launchOptions: { executablePath },
  },
  webServer: [
    {
      command:
        "cd ../backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/python -m app.seed && ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18000",
      url: "http://127.0.0.1:18000/healthz",
      reuseExistingServer: false,
      env: {
        FRIP_MODE: "synthetic",
        FRIP_DATABASE_URL: `sqlite:///${join(tmpdir(), `frip-browser-${process.pid}.sqlite`)}`,
        FRIP_TOKENS_JSON: JSON.stringify({
          "synthetic-browser-editor": {
            role: "editor",
            subject: "browser-test",
            sources: "maintenance,parts,fdc,informs-demo,lam-demo,fdc-demo",
            equipment: "tool-1",
            collections: "maintenance,procedures,parts,telemetry",
          },
        }),
      },
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 15173 --strictPort",
      url: "http://127.0.0.1:15173",
      reuseExistingServer: false,
      env: { VITE_API_PROXY_TARGET: "http://127.0.0.1:18000" },
      timeout: 30_000,
    },
  ],
});
