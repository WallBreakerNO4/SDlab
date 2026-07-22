import { expect, test } from "@playwright/test";

import {
  DISPLAY_VARIANT_URL_PATTERN,
  installModelViewMock,
  MOCK_MODEL_VIEW_RUN_DIR,
  PUBLIC_ROW_URL_PATTERN,
} from "./model-view-test-helpers";

test.describe("task 13: dialog display image loads on demand", () => {
  test("grid scrolling should not request display URLs before opening the dialog", async ({
    page,
  }) => {
    let rowRequestCount = 0;
    let displayRequestCount = 0;

    page.on("request", (request) => {
      const url = request.url();
      if (PUBLIC_ROW_URL_PATTERN.test(url)) {
        rowRequestCount += 1;
      }

      if (DISPLAY_VARIANT_URL_PATTERN.test(url)) {
        displayRequestCount += 1;
      }
    });

    await installModelViewMock(page);
    await page.goto(`/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

    await expect(page).toHaveURL(/\/models\//);
    await expect(page.getByTestId("run-grid")).toBeVisible();
    await expect
      .poll(() => rowRequestCount, { timeout: 10_000 })
      .toBeGreaterThan(0);

    const scrollEl = page.getByTestId("run-grid-scroll");
    await scrollEl.evaluate((el) => {
      el.scrollTop = el.scrollTop + el.clientHeight * 4;
    });

    const previewButton = page.getByLabel("打开单元格预览").first();
    await expect(previewButton).toBeVisible({ timeout: 10_000 });
    expect(displayRequestCount).toBe(0);

    await previewButton.click();

    await expect(page.getByTestId("cell-dialog")).toBeVisible();
    await expect
      .poll(() => displayRequestCount, { timeout: 10_000 })
      .toBeGreaterThan(0);
  });

  test("dialog should use the loaded preview image until the display image finishes loading", async ({
    page,
  }) => {
    let releaseDisplayRequest = () => {};
    const displayRequestReleased = new Promise<void>((resolve) => {
      releaseDisplayRequest = resolve;
    });

    await installModelViewMock(page, {
      beforeDisplayFulfill: () => displayRequestReleased,
    });
    await page.goto(`/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

    await expect(page).toHaveURL(/\/models\//);
    await expect(page.getByTestId("run-grid")).toBeVisible();

    const previewButton = page.getByLabel("打开单元格预览").first();
    const previewImage = previewButton.getByTestId("run-grid-image");
    await expect(previewImage).toHaveClass(/opacity-100/, { timeout: 10_000 });

    await previewButton.click();

    const dialog = page.getByTestId("cell-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId("cell-dialog-preview-image")).toHaveClass(
      /opacity-100/,
      { timeout: 10_000 },
    );
    await expect(dialog.getByTestId("cell-dialog-display-image")).toHaveClass(
      /opacity-0/,
    );

    releaseDisplayRequest();

    await expect(dialog.getByTestId("cell-dialog-display-image")).toHaveClass(
      /opacity-100/,
      { timeout: 10_000 },
    );
    await expect(dialog.getByTestId("cell-dialog-preview-image")).toHaveClass(
      /opacity-0/,
      { timeout: 10_000 },
    );
  });
});
