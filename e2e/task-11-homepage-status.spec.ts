import path from "node:path";

import { expect, test } from "@playwright/test";

import runListItems from "./no-env-home-run-list.json";

const NO_ENV_OUTPUT_DIR = path.resolve("/tmp/sdlab-playwright-no-env/");
const IN_PROGRESS_RUN_DIR = "e2e-in-progress-run";
const COMPLETE_RUN_DIR = "e2e-complete-run";

test("task 11: 首页按最近发布时间排序并展示「评测中」徽章", async (
  { page },
  testInfo,
) => {
  test.skip(
    path.resolve(testInfo.project.outputDir) !== NO_ENV_OUTPUT_DIR,
    "仅 no-env mock 模式提供确定性首页数据",
  );

  await page.goto("/zh");

  const cards = page.locator('main a[href*="/models/"]');
  await expect(cards).toHaveCount(runListItems.length);

  // published_at 最新的进行中评测排在 created_at 更新的已完结评测之前。
  await expect(cards.nth(0)).toHaveAttribute(
    "href",
    new RegExp(`/models/${IN_PROGRESS_RUN_DIR}$`),
  );
  await expect(cards.nth(1)).toHaveAttribute(
    "href",
    new RegExp(`/models/${COMPLETE_RUN_DIR}$`),
  );

  const inProgressCard = page.locator(
    `main a[href*="${IN_PROGRESS_RUN_DIR}"]`,
  );
  const completeCard = page.locator(`main a[href*="${COMPLETE_RUN_DIR}"]`);

  const badge = inProgressCard.getByTestId("model-status-badge");
  await expect(badge).toBeVisible();
  await expect(badge).toHaveText("评测中");
  await expect(completeCard.getByTestId("model-status-badge")).toHaveCount(0);

  // 卡片图继续使用封面图与主页缩略图字段。
  await expect(
    inProgressCard.locator('img[alt="E2E In Progress Model"]'),
  ).toHaveAttribute(
    "src",
    /\/runs\/e2e-in-progress-run\/media\/cover\/display_webp\.webp$/,
  );
  await expect(
    inProgressCard
      .locator('img[src*="/runs/e2e-in-progress-run/media/card/"]')
      .first(),
  ).toHaveAttribute(
    "src",
    /\/runs\/e2e-in-progress-run\/media\/card\/display_webp\.webp$/,
  );
});

test("task 11: 英文首页显示 In progress 徽章", async ({ page }, testInfo) => {
  test.skip(
    path.resolve(testInfo.project.outputDir) !== NO_ENV_OUTPUT_DIR,
    "仅 no-env mock 模式提供确定性首页数据",
  );

  await page.goto("/en");

  const inProgressCard = page.locator(
    `main a[href*="${IN_PROGRESS_RUN_DIR}"]`,
  );
  const badge = inProgressCard.getByTestId("model-status-badge");
  await expect(badge).toHaveText("In progress");

  const completeCard = page.locator(`main a[href*="${COMPLETE_RUN_DIR}"]`);
  await expect(completeCard.getByTestId("model-status-badge")).toHaveCount(0);
});
