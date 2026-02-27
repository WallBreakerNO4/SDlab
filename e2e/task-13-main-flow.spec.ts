import { expect, test } from "@playwright/test";

const hasSupabaseConfig = Boolean(
  process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY,
);

test.describe("task 13: runs -> detail -> grid -> scroll row lazy load", () => {
  test.skip(!hasSupabaseConfig, "缺少 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY，跳过数据相关用例");

  test("grid renders and scrolling triggers more row requests", async ({ page }) => {
    const requestedYIndexes = new Set<number>();

    page.on("response", (response) => {
      const url = response.url();
      if (!url.includes("/api/comfyui/run/") || !url.includes("/row?")) return;
      if (!response.ok()) return;

      try {
        const parsed = new URL(url);
        const yIndex = parsed.searchParams.get("y_index");
        if (!yIndex) return;
        const n = Number(yIndex);
        if (Number.isFinite(n)) requestedYIndexes.add(n);
      } catch {
      }
    });

    await page.goto("/");

    const runLink = page.locator("a[href^='/runs/']").first();
    await expect(runLink).toBeVisible();

    await runLink.click();
    await expect(page).toHaveURL(/\/runs\//);
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
