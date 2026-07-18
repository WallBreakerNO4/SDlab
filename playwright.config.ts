import { defineConfig } from "@playwright/test";

const e2eServerMode = process.env.E2E_SERVER === "start" ? "start" : "dev";
const e2ePort = process.env.E2E_PORT ?? "3000";
const e2eBaseUrl = `http://localhost:${e2ePort}`;
const webServerCommand =
  e2eServerMode === "start"
    ? `pnpm build && pnpm start -p ${e2ePort}`
    : `pnpm dev -p ${e2ePort}`;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "test-results/",
  // 已登录态 session 建立 / 测试用户收藏清理（spec 决策记录 13）；缺 Supabase 环境变量时
  // setup 不写 state，已登录用例自行 skip
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
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
    command: webServerCommand,
    url: e2eBaseUrl,
    reuseExistingServer: e2eServerMode === "start" ? false : !process.env.CI,
    timeout: e2eServerMode === "start" ? 240_000 : 120_000,
  },
});
