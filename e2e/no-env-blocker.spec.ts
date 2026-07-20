import path from "node:path";

import { expect, test } from "@playwright/test";

const NO_ENV_OUTPUT_DIR = path.resolve("/tmp/sdlab-playwright-no-env/");
const BLOCKER_MARKER = Symbol.for("sdlab.block-env-file-access.loaded");

test("no-env 配置会在 Playwright worker 中预加载环境文件 blocker", async (
  {},
  testInfo,
) => {
  test.skip(
    path.resolve(testInfo.project.outputDir) !== NO_ENV_OUTPUT_DIR,
    "仅 no-env Playwright 配置要求 worker 预加载 blocker",
  );

  expect(Reflect.get(globalThis, BLOCKER_MARKER)).toBe(true);
});
