import { expect, test, type Page } from "@playwright/test";

import { E2E_AUTH_STATE_PATH, hasE2EAuthEnv } from "./e2e-auth-state";

const hasAuthEnv = hasE2EAuthEnv();

const STYLE_KEY = "e2e-comparison-status:1";
const IN_PROGRESS_RUN_DIR = "e2e-in-progress-comparison";
const COMPLETE_RUN_DIR = "e2e-complete-comparison";

const FAVORITE = {
  style_key: STYLE_KEY,
  label: "e2e 对比状态收藏",
  created_at: "2026-09-10T00:00:00.000Z",
};

const X_COLUMNS = [
  {
    x_index: 0,
    type: "normal",
    description: { zh: "场景一", en: "Scene 1" },
  },
];

const MODELS = [
  {
    run_dir: IN_PROGRESS_RUN_DIR,
    name: "In Progress Model",
    created_at: "2026-09-01T00:00:00.000Z",
    published_at: "2026-09-19T00:00:00.000Z",
    status: "in_progress",
    x_columns: X_COLUMNS,
  },
  {
    run_dir: COMPLETE_RUN_DIR,
    name: "Complete Model",
    created_at: "2026-09-02T00:00:00.000Z",
    published_at: "2026-09-18T00:00:00.000Z",
    status: "complete",
    x_columns: X_COLUMNS,
  },
];

/**
 * 目录/详情/slice 都改写为固定响应：目录同时包含进行中与已完结评测，
 * slice 只回空 placement，用于断言请求 run_dirs 的范围。
 */
async function installComparisonMocks(page: Page) {
  const sliceRunDirs: string[][] = [];

  await page.route(/\/api\/viewer\/style-comparison\?/, async (route) => {
    await route.fulfill({
      json: { favorites: [FAVORITE], models: MODELS, next_cursor: null },
    });
  });

  await page.route(
    /\/api\/viewer\/style-comparison\/slice$/,
    async (route) => {
      const body = route.request().postDataJSON() as { run_dirs?: unknown };
      sliceRunDirs.push(
        Array.isArray(body.run_dirs)
          ? body.run_dirs.filter(
              (value): value is string => typeof value === "string",
            )
          : [],
      );
      await route.fulfill({
        json: { access: [], placements: { [STYLE_KEY]: [] } },
      });
    },
  );

  await page.route(
    /\/api\/viewer\/style-comparison\/(?!slice$)[^/]+$/,
    async (route) => {
      await route.fulfill({ json: { favorite: FAVORITE, models: MODELS } });
    },
  );

  return { sliceRunDirs };
}

test.describe("task 13: 模型对比的评测状态呈现", () => {
  test.use({ storageState: E2E_AUTH_STATE_PATH });
  test.skip(
    !hasAuthEnv,
    "缺少 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY，跳过已登录用例",
  );

  test("进行中评测在对比页是禁用条目，矩阵与 slice 只含已完结评测", async ({
    page,
  }) => {
    const { sliceRunDirs } = await installComparisonMocks(page);
    await page.goto("/zh/favorites");

    const note = page.getByTestId("comparison-in-progress-note");
    await expect(note).toBeVisible({ timeout: 15_000 });
    await expect(note).toHaveText("评测中的模型暂不参与对比，完结后自动加入。");

    const matrix = page.getByTestId("comparison-matrix-scroll");
    await expect(matrix).toBeVisible();
    await expect(
      matrix.locator(`a[href*="/models/${COMPLETE_RUN_DIR}"]`),
    ).toBeVisible();
    await expect(
      matrix.locator(`a[href*="/models/${IN_PROGRESS_RUN_DIR}"]`),
    ).toHaveCount(0);

    await page.getByRole("button", { name: /显示 1 个模型/ }).click();
    const inProgressItem = page.getByRole("menuitemcheckbox", {
      name: /In Progress Model/,
    });
    await expect(inProgressItem).toBeVisible();
    await expect(
      inProgressItem.getByTestId("comparison-model-status-badge"),
    ).toHaveText("评测中");
    expect(
      await inProgressItem.evaluate((element) =>
        element.hasAttribute("data-disabled"),
      ),
    ).toBe(true);

    const completeItem = page.getByRole("menuitemcheckbox", {
      name: /Complete Model/,
    });
    await expect(completeItem).toHaveAttribute("aria-checked", "true");

    await expect.poll(() => sliceRunDirs.length).toBeGreaterThan(0);
    for (const runDirs of sliceRunDirs) {
      expect(runDirs).toContain(COMPLETE_RUN_DIR);
      expect(runDirs).not.toContain(IN_PROGRESS_RUN_DIR);
    }
  });

  test("英文对比页显示 In progress 标记与说明", async ({ page }) => {
    await installComparisonMocks(page);
    await page.goto("/en/favorites");

    await expect(page.getByTestId("comparison-in-progress-note")).toHaveText(
      "Models under evaluation don't take part in comparisons yet; they join automatically once complete.",
    );

    await page.getByRole("button", { name: /Showing 1 models/ }).click();
    await expect(
      page
        .getByRole("menuitemcheckbox", { name: /In Progress Model/ })
        .getByTestId("comparison-model-status-badge"),
    ).toHaveText("In progress");
  });

  test("单收藏对比详情矩阵只含已完结评测", async ({ page }) => {
    const { sliceRunDirs } = await installComparisonMocks(page);
    await page.goto(`/zh/favorites/${encodeURIComponent(STYLE_KEY)}`);

    const table = page.locator("table");
    await expect(table).toBeVisible({ timeout: 15_000 });
    await expect(
      table.locator(`a[href*="/models/${COMPLETE_RUN_DIR}"]`),
    ).toBeVisible();
    await expect(
      table.locator(`a[href*="/models/${IN_PROGRESS_RUN_DIR}"]`),
    ).toHaveCount(0);
    await expect(page.getByTestId("comparison-in-progress-note")).toBeVisible();

    await expect.poll(() => sliceRunDirs.length).toBeGreaterThan(0);
    expect(sliceRunDirs.flat()).not.toContain(IN_PROGRESS_RUN_DIR);
  });
});
