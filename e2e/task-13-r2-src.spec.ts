import { expect, test } from "@playwright/test";

const hasSupabaseConfig = Boolean(
  process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY,
);

const r2PublicBaseUrl = process.env.R2_PUBLIC_BASE_URL ?? "";
const normalizedR2PublicBaseUrl = r2PublicBaseUrl.endsWith("/")
  ? r2PublicBaseUrl.slice(0, -1)
  : r2PublicBaseUrl;

test.describe("task 13: grid image src uses R2 public URL", () => {
  test.skip(!hasSupabaseConfig, "缺少 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY，跳过数据相关用例");
  test.skip(!normalizedR2PublicBaseUrl, "缺少 R2_PUBLIC_BASE_URL，无法断言公开直链域名");

  test("normal column images should not use /api/comfyui/image proxy", async ({ page }) => {
    await page.goto("/");

    const modelLink = page.locator("a[href^='/models/']").first();
    await expect(modelLink).toBeVisible();
    await modelLink.click();

    await expect(page.getByTestId("run-grid")).toBeVisible();

    const firstImage = page.getByTestId("run-grid-image").first();
    await expect(firstImage).toHaveClass(/opacity-100/, { timeout: 10_000 });

    const src = await firstImage.evaluate((img) => {
      const node = img as HTMLImageElement;
      return node.getAttribute("src") || node.currentSrc || node.src;
    });

    expect(src).not.toContain("/api/comfyui/image/");
    expect(src).toMatch(/^https:\/\//);
    expect(src.startsWith(`${normalizedR2PublicBaseUrl}/`)).toBeTruthy();
  });
});
