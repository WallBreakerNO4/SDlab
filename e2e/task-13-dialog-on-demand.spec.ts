import { expect, test } from "@playwright/test";

const hasSupabaseConfig = Boolean(
  process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY,
);

test.describe("task 13: dialog display image loads on demand", () => {
  test.skip(
    !hasSupabaseConfig,
    "缺少 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY，跳过数据相关用例",
  );

  test("grid scrolling should not request display URLs before opening the dialog", async ({
    page,
  }) => {
    let rowRequestCount = 0;
    let displayRequestCount = 0;

    page.on("request", (request) => {
      const url = request.url();
      if (!url.includes("/api/comfyui/run/")) return;

      if (url.includes("/row?")) {
        rowRequestCount += 1;
      }

      if (url.includes("/display?")) {
        displayRequestCount += 1;
      }
    });

    await page.goto("/");

    const modelLink = page.locator("a[href^='/models/']").first();
    await expect(modelLink).toBeVisible();
    await modelLink.click();

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
    let releaseDisplayRequest: (() => void) | null = null;

    await page.route("**/api/comfyui/run/*/display?*", async (route) => {
      await new Promise<void>((resolve) => {
        releaseDisplayRequest = resolve;
      });
      await route.continue();
    });

    await page.goto("/");

    const modelLink = page.locator("a[href^='/models/']").first();
    await expect(modelLink).toBeVisible();
    await modelLink.click();

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

    releaseDisplayRequest?.();

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
