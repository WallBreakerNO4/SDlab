import { expect, test } from "@playwright/test";

import {
  installModelViewMock,
  MOCK_MODEL_VIEW_RUN_DIR,
} from "./model-view-test-helpers";

test("task 10: placeholder appears before image load", async ({ page }, testInfo) => {
  await installModelViewMock(page, { thumbDelayMs: 2_000 });
  await page.goto(`/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

  await expect(page.getByTestId("run-grid")).toBeVisible();

  const blurhashCanvas = page.getByTestId("blurhash-canvas").first();
  await expect(blurhashCanvas).toBeVisible();

  const image = page.getByTestId("run-grid-image").first();
  await expect(image).toHaveClass(/opacity-0/);

  await page.screenshot({ path: testInfo.outputPath("task-10-placeholder.png") });

  await expect(image).toHaveClass(/opacity-100/, { timeout: 5_000 });
  await expect(blurhashCanvas).toHaveClass(/opacity-0/);
});
