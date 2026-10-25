const { defineConfig } = require("@playwright/test");

const FRONT = process.env.E2E_FRONT_URL || "http://localhost:3000";

module.exports = defineConfig({
  testDir: "./e2e",
  testMatch: "navigation.spec.js",
  timeout: 30000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: FRONT,
    trace: "retain-on-failure",
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  webServer: [{ command: "node e2e/serve.js 3000", url: FRONT, reuseExistingServer: true, timeout: 20000 }],
});
