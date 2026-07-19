import { expect, test } from "@playwright/test";

import {
  installModelViewMock,
  MOCK_MODEL_VIEW_RUN_DIR,
} from "./model-view-test-helpers";

test.describe("task 13: grid image src uses R2 public URL", () => {
  test("normal column images should not use /api/comfyui/image proxy", async ({ page }) => {
    await installModelViewMock(page);
    await page.goto(`/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

    await expect(page.getByTestId("run-grid")).toBeVisible();

    const firstImage = page.getByTestId("run-grid-image").first();
    await expect(firstImage).toHaveClass(/opacity-100/, { timeout: 10_000 });

    const src = await firstImage.evaluate((img) => {
      const node = img as HTMLImageElement;
      return node.getAttribute("src") || node.currentSrc || node.src;
    });

    expect(src).not.toContain("/api/comfyui/image/");
    expect(new URL(src).pathname).toMatch(
      new RegExp(
        `^/runs/${MOCK_MODEL_VIEW_RUN_DIR}/media/\\d+-\\d+/thumb_webp\\.webp$`,
      ),
    );
  });
});
