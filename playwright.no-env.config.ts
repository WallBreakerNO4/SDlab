import path from "node:path";

import { defineConfig } from "@playwright/test";

import "./e2e/block-env-file-access.cjs";
import { mergeNodeRequireOption } from "./e2e/no-env-node-options";

const e2ePort = process.env.E2E_PORT ?? "3100";
const mockSupabasePort = process.env.E2E_MOCK_SUPABASE_PORT ?? "3199";
const e2eBaseUrl = `http://localhost:${e2ePort}`;

delete process.env.SUPABASE_URL;
delete process.env.SUPABASE_SERVICE_ROLE_KEY;
process.env.NEXT_PUBLIC_SUPABASE_URL = `http://127.0.0.1:${mockSupabasePort}`;
process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "e2e-public-key";
process.env.NEXT_PUBLIC_R2_PUBLIC_BASE_URL = e2eBaseUrl;
process.env.R2_PUBLIC_BASE_URL = e2eBaseUrl;

// Next 服务端渲染依赖 Supabase 查询；no-env 模式由本地 mock REST 端点提供固定数据。
const envBlocker = path.resolve("e2e/block-env-file-access.cjs");
const nodeOptions = mergeNodeRequireOption(process.env.NODE_OPTIONS, envBlocker);
process.env.NODE_OPTIONS = nodeOptions;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "/tmp/sdlab-playwright-no-env/",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  reporter: [["list"]],
  use: {
    baseURL: e2eBaseUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "node e2e/no-env-webserver.cjs",
    url: e2eBaseUrl,
    reuseExistingServer: false,
    timeout: 300_000,
  },
});
