import path from "node:path";

import { defineConfig } from "@playwright/test";

import "./e2e/block-env-file-access.cjs";
import { mergeNodeRequireOption } from "./e2e/no-env-node-options";

const e2ePort = process.env.E2E_PORT ?? "3100";
const e2eBaseUrl = `http://localhost:${e2ePort}`;

delete process.env.SUPABASE_URL;
delete process.env.SUPABASE_SERVICE_ROLE_KEY;
process.env.NEXT_PUBLIC_SUPABASE_URL = e2eBaseUrl;
process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "e2e-public-key";
process.env.NEXT_PUBLIC_R2_PUBLIC_BASE_URL = e2eBaseUrl;
process.env.R2_PUBLIC_BASE_URL = e2eBaseUrl;

const envBlocker = path.resolve("e2e/block-env-file-access.cjs");
const nextCli = path.resolve("node_modules/.bin/next");
const nodeOptions = mergeNodeRequireOption(process.env.NODE_OPTIONS, envBlocker);
process.env.NODE_OPTIONS = nodeOptions;

function quoteShellArgument(value: string): string {
  return `'${value.replaceAll("'", `'"'"'`)}'`;
}

const explicitNodeOptions = quoteShellArgument(nodeOptions);
const explicitNextCli = quoteShellArgument(nextCli);

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
    command: `NODE_OPTIONS=${explicitNodeOptions} ${explicitNextCli} build && NODE_OPTIONS=${explicitNodeOptions} ${explicitNextCli} start -p ${e2ePort}`,
    url: e2eBaseUrl,
    reuseExistingServer: false,
    timeout: 300_000,
  },
});
