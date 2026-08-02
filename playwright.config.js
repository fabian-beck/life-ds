import { defineConfig, devices } from "@playwright/test";

// Mirrors `basePath` in vite.config.js: the dev server serves the app under
// the deployment base path, so the tests have to enter it there. Test URLs are
// relative so they resolve against this base rather than the domain root.
const basePath = process.env.VITE_BASE_PATH ?? "/life-ds/";
const devServerOrigin = "http://127.0.0.1:4173";

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
    baseURL: `${devServerOrigin}${basePath}`,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: `${devServerOrigin}${basePath}en`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    {
      name: "logic",
      testMatch:
        /(personNames|historicalDates|relationshipLabels|descriptionSegments|birthEvent|publicationSource)\.spec\.js/,
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
