import { fileURLToPath } from "node:url";
import path from "node:path";
import { defineConfig } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables from .env if it exists
try {
  process.loadEnvFile();
} catch {}

const e2eServerMode = process.env.E2E_SERVER === "start" ? "start" : "dev";
const e2ePort = process.env.E2E_PORT ?? "3000";
const e2eBaseUrl = `http://127.0.0.1:${e2ePort}`;
const webServerCommand =
  e2eServerMode === "start"
    ? `pnpm build && pnpm start -p ${e2ePort}`
    : `pnpm dev -p ${e2ePort}`;

export default defineConfig({
  testDir: "./e2e",
  outputDir: ".sisyphus/evidence/playwright/",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  reporter: [["list"]],
  use: {
    baseURL: e2eBaseUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    cwd: __dirname,

    command: webServerCommand,
    url: e2eBaseUrl,
    reuseExistingServer: e2eServerMode === "start" ? false : !process.env.CI,
    timeout: e2eServerMode === "start" ? 240_000 : 120_000,
  },
});

