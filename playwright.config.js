import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  outputDir: "test-results",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/en",
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    {
      name: "logic",
      testMatch: "personNames.spec.js",
      use: {},
    },
    {
      name: "desktop-chromium",
      testMatch: "interface.spec.js",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "mobile-chromium",
      testMatch: "interface.spec.js",
      use: {
        ...devices["Pixel 7"],
      },
    },
  ],
});
