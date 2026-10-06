import { defineConfig, devices } from "@playwright/test";
const port = Number(process.env.SEARCHBAR_E2E_PORT ?? "18765");
if (!Number.isInteger(port) || port < 1024 || port > 65535) {
  throw new Error(
    "SEARCHBAR_E2E_PORT must be an integer between 1024 and 65535",
  );
}
const baseURL = `http://127.0.0.1:${port}`;
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `uv run uvicorn e2e.server:create_test_app --factory --host 127.0.0.1 --port ${port} --no-access-log`,
    cwd: "..",
    url: `${baseURL}/health`,
    env: { SEARCHBAR_E2E_PORT: String(port) },
    reuseExistingServer: false,
  },
});
