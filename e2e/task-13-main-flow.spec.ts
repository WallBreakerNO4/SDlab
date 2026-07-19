import { expect, test } from "@playwright/test";

import {
  installModelViewMock,
  MOCK_MODEL_VIEW_RUN_DIR,
  PUBLIC_ROW_URL_PATTERN,
} from "./model-view-test-helpers";

test.describe("task 13: detail -> grid -> scroll row lazy load", () => {
  test("grid renders and scrolling triggers more row requests", async ({ page }) => {
    const requestedYIndexes = new Set<number>();

    page.on("response", (response) => {
      const url = response.url();
      if (!response.ok()) return;

      const match = url.match(PUBLIC_ROW_URL_PATTERN);
      if (!match) return;
      const yIndex = Number(match[1]);
      if (Number.isFinite(yIndex)) requestedYIndexes.add(yIndex);
    });

    await installModelViewMock(page);
    await page.goto(`/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

    await expect(page).toHaveURL(/\/models\//);
    await expect(page.getByTestId("run-grid")).toBeVisible();

    await expect
      .poll(() => requestedYIndexes.size, { timeout: 10_000 })
      .toBeGreaterThan(0);

    const initialRequested = requestedYIndexes.size;
    const scrollEl = page.getByTestId("run-grid-scroll");

    await scrollEl.evaluate((el) => {
      el.scrollTop = el.scrollTop + el.clientHeight * 6;
    });

    await expect
      .poll(() => requestedYIndexes.size, { timeout: 10_000 })
      .toBeGreaterThan(initialRequested);

    const firstImage = page.getByTestId("run-grid-image").first();
    await expect(firstImage).toHaveClass(/opacity-100/, { timeout: 10_000 });
  });
});
