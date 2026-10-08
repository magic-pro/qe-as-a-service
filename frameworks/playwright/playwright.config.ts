import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: [
    ["html", { outputFolder: "playwright-report" }],
    ["json", { outputFile: "playwright-report/results.json" }],
    ["list"],
  ],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    extraHTTPHeaders: {
      "X-Test-Source": "qe-playwright",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "api",
      testMatch: /.*\.api\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile",
      testMatch: /.*\.mobile\.spec\.ts/,
      use: { ...devices["iPhone 14"] },
    },
  ],
  globalSetup: "./helpers/global-setup.ts",
});
