import { expect, test } from "@playwright/test";

import {
  DISPLAY_VARIANT_URL_PATTERN,
  getFirstModelLink,
  PUBLIC_ROW_URL_PATTERN,
  THUMB_VARIANT_URL_PATTERN,
} from "./model-view-test-helpers";

test.describe("model view E2E contracts", () => {
  test("finds a locale-prefixed model link in main content", async ({ page }) => {
    await page.setContent(`
      <nav><a href="/zh/models/navigation-model">Navigation model</a></nav>
      <main><a href="/zh/models/grid-model">Grid model</a></main>
    `);

    await expect(getFirstModelLink(page)).toHaveAttribute(
      "href",
      "/zh/models/grid-model",
    );
  });

  test("matches current R2 row and image variant URLs", () => {
    const rowUrl =
      "https://assets.example/runs/demo/view/v2/release/rows/public/42.json?cache=1";

    expect(rowUrl.match(PUBLIC_ROW_URL_PATTERN)?.[1]).toBe("42");
    expect(
      DISPLAY_VARIANT_URL_PATTERN.test(
        "https://assets.example/runs/demo/assets/hash/display_webp.webp",
      ),
    ).toBe(true);
    expect(
      THUMB_VARIANT_URL_PATTERN.test(
        "https://assets.example/runs/demo/assets/hash/thumb_avif.avif?cache=1",
      ),
    ).toBe(true);
    expect(
      PUBLIC_ROW_URL_PATTERN.test(
        "http://localhost/api/comfyui/run/demo/row?y_index=42",
      ),
    ).toBe(false);
  });
});
