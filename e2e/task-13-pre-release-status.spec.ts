import { expect, test, type Page } from "@playwright/test";

import { installModelViewMock } from "./model-view-test-helpers";

const RUN_DIR = "mock-run-pre-release-status";
const EMPTY_ROW_INDEX = 1;

function gridRow(page: Page, yIndex: number) {
  return page.locator(
    `[data-testid="run-grid-row"][data-row-index="${yIndex}"]`,
  );
}

test.describe("task 13: 进行中评测的详情页状态呈现", () => {
  test("进行中评测显示中英文横幅，空单元格显示「待生成」", async ({ page }) => {
    await installModelViewMock(page, {
      runDir: RUN_DIR,
      runStatus: "in_progress",
      emptyRowIndexes: [EMPTY_ROW_INDEX],
    });

    await page.goto(`/zh/models/${RUN_DIR}`);

    const banner = page.getByTestId("model-in-progress-banner");
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toHaveText(
      "该模型仍在评测中，完整结果请耐心等待；可先浏览已生成的部分结果。",
    );

    // 行已就绪且无图 → 「待生成」；有图的行不显示占位。
    const emptyRow = gridRow(page, EMPTY_ROW_INDEX);
    await expect(emptyRow.getByTestId("run-grid-placeholder")).toHaveCount(2);
    await expect(
      emptyRow.getByTestId("run-grid-placeholder").first(),
    ).toHaveText("待生成");
    await expect(gridRow(page, 0).getByTestId("run-grid-placeholder")).toHaveCount(
      0,
    );

    await page.goto(`/en/models/${RUN_DIR}`);
    await expect(page.getByTestId("model-in-progress-banner")).toHaveText(
      "This model is still being evaluated. Full results are coming — you can browse the partial results in the meantime.",
    );
    await expect(
      gridRow(page, EMPTY_ROW_INDEX).getByTestId("run-grid-placeholder").first(),
    ).toHaveText("Pending");
  });

  test("已完结评测保持原「缺失」占位且不显示横幅", async ({ page }) => {
    await installModelViewMock(page, {
      runDir: RUN_DIR,
      runStatus: "complete",
      emptyRowIndexes: [EMPTY_ROW_INDEX],
    });

    await page.goto(`/zh/models/${RUN_DIR}`);

    await expect(
      gridRow(page, EMPTY_ROW_INDEX).getByTestId("run-grid-placeholder").first(),
    ).toHaveText("缺失");
    await expect(page.getByTestId("model-in-progress-banner")).toHaveCount(0);
  });

  test("缺状态字段的历史发布数据按已完结处理", async ({ page }) => {
    await installModelViewMock(page, {
      runDir: RUN_DIR,
      emptyRowIndexes: [EMPTY_ROW_INDEX],
    });

    await page.goto(`/zh/models/${RUN_DIR}`);

    await expect(
      gridRow(page, EMPTY_ROW_INDEX).getByTestId("run-grid-placeholder").first(),
    ).toHaveText("缺失");
    await expect(page.getByTestId("model-in-progress-banner")).toHaveCount(0);
  });

  test("加载失败占位不受评测状态影响", async ({ page }) => {
    await installModelViewMock(page, {
      runDir: RUN_DIR,
      runStatus: "in_progress",
      emptyRowIndexes: [EMPTY_ROW_INDEX],
      failedRowIndexes: [EMPTY_ROW_INDEX],
    });

    await page.goto(`/zh/models/${RUN_DIR}`);

    await expect(
      gridRow(page, EMPTY_ROW_INDEX).getByTestId("run-grid-placeholder").first(),
    ).toHaveText("加载失败");
  });
});
