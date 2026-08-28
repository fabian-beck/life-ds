import { defineConfig, devices } from "@playwright/test";

// Mirrors `basePath` in vite.config.js: the dev server serves the app under
// the deployment base path, so the tests have to enter it there. Test URLs are
// relative so they resolve against this base rather than the domain root.
const basePath = process.env.VITE_BASE_PATH ?? "/life-ds/";
const devServerOrigin = "http://127.0.0.1:4173";

export default defineConfig({
  testDir: "./tests",
  outputDir: "test-results",
  // The suite is a smoke check and a set of pure functions; nothing here is
  // allowed to take long enough for the old minute-scale budgets to matter.
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: true,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `${devServerOrigin}${basePath}`,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: `${devServerOrigin}${basePath}en`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    // Browser-free pure functions. They cost a few seconds for the whole set,
    // so they stay; anything that needs a page belongs in the smoke test.
    {
      name: "logic",
      testIgnore: /smoke\.spec\.js/,
      use: {},
    },
    // The single browser pass, at the phone viewport the application is
    // designed for. Everything else the interface can get wrong is found by AI
    // exploration rather than by a script; see docs/testing-strategy.md.
    {
      name: "smoke",
      testMatch: /smoke\.spec\.js/,
      use: {
        ...devices["Pixel 7"],
      },
    },
  ],
});
