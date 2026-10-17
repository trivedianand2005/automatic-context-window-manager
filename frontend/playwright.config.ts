import { defineConfig, devices } from "@playwright/test";

// End-to-end tests drive the built site against a running ACWM API.
//   API:  uvicorn app.api.main:app --port 8000      (from the repository root)
//   Site: npm run build && npx vite preview --port 4173
// Override with E2E_BASE_URL to test a deployed site.
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 90_000 },
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:4173",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
