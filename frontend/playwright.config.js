// E2E against the REAL backend (PostgreSQL) and the production build of the frontend. Nothing is mocked and nothing is
// sent: the server runs in dry-run, no provider key is set, and no test opens a connection to a third party.
// Local: start the API (see docs/deployment.md), `REACT_APP_BACKEND_URL=http://localhost:8000 npm run build`, then `npm run e2e`.
const { defineConfig } = require("@playwright/test");

const FRONT = process.env.E2E_FRONT_URL || "http://localhost:3000";
const API = process.env.E2E_API_URL || "http://localhost:8000";

module.exports = defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: FRONT,
    trace: "retain-on-failure",
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  webServer: [
    { command: "node e2e/serve.js 3000", url: FRONT, reuseExistingServer: true, timeout: 20000 },
    { command: "echo 'start the API first (see docs/deployment.md)'", url: `${API}/api/health`, reuseExistingServer: true, timeout: 5000 },
  ],
});
