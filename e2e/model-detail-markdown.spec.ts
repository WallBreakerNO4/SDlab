import { expect, test } from "@playwright/test";

import {
  installModelViewMock,
  MOCK_MODEL_VIEW_RUN_DIR,
} from "./model-view-test-helpers";

test.describe("模型详情顶栏 Markdown", () => {
  test("渲染允许的 Markdown，并按链接类型应用安全属性", async ({ page }) => {
    const forbiddenImageRequests: string[] = [];
    page.on("request", (request) => {
      if (/example\.com\/(?:tracker|raw-html)\.png/.test(request.url())) {
        forbiddenImageRequests.push(request.url());
      }
    });

    await installModelViewMock(page, {
      description: {
        zh: [
          "支持 **粗体**、*斜体*、`行内代码`。",
          "",
          "[站内链接](/info) [外部链接](https://example.com/docs) [危险链接](javascript:alert(1))",
          "",
          "- 列表项",
          "",
          "<strong>原始 HTML</strong>",
          '<script>window.__modelDescriptionXss = true</script>',
          '<img src="https://example.com/raw-html.png" onerror="window.__modelDescriptionXss = true">',
          "",
          "![禁止图片](https://example.com/tracker.png)",
          "",
          "# 禁止标题",
          "",
          "```txt\n禁止代码块\n```",
        ].join("\n"),
      },
    });

    await page.goto(`/zh/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

    const toggle = page.getByTestId("model-description-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAccessibleName("展开模型简介");
    await toggle.click();
    const description = page.getByTestId("model-description-markdown");
    await expect(description).toBeVisible();
    await expect(description.locator("strong")).toHaveCount(1);
    await expect(description.locator("strong")).toHaveText("粗体");
    await expect(description.locator("em")).toHaveText("斜体");
    await expect(description.locator("ul > li")).toHaveText("列表项");
    await expect(description.locator("script, img, h1, table, pre")).toHaveCount(0);
    await expect(description).toContainText("原始 HTML");
    await expect(description).toContainText("禁止标题");
    expect(
      await page.evaluate(
        () =>
          Boolean(
            (
              window as typeof window & {
                __modelDescriptionXss?: boolean;
              }
            ).__modelDescriptionXss,
          ),
      ),
    ).toBe(false);
    expect(forbiddenImageRequests).toEqual([]);

    const internalLink = description.getByRole("link", { name: "站内链接" });
    await expect(internalLink).toHaveAttribute("href", "/zh/info");
    await expect(internalLink).not.toHaveAttribute("target", "_blank");

    const externalLink = description.getByRole("link", { name: "外部链接" });
    await expect(externalLink).toHaveAttribute(
      "href",
      "https://example.com/docs",
    );
    await expect(externalLink).toHaveAttribute("target", "_blank");
    await expect(externalLink).toHaveAttribute("rel", "noopener noreferrer");

    await expect(description.getByText("危险链接")).not.toHaveAttribute("href");
  });

  test("长简介默认折叠两行，可展开为限高滚动区域", async ({ page }) => {
    await installModelViewMock(page, {
      description: {
        zh: Array.from(
          { length: 12 },
          (_, index) =>
            `第 ${index + 1} 段模型简介，[链接 ${index + 1}](/info) 用于制造稳定溢出。`,
        ).join("\n\n"),
      },
    });

    await page.goto(`/zh/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

    const preview = page.getByTestId("model-description-preview");
    const description = page.getByTestId("model-description-markdown");
    const toggle = page.getByTestId("model-description-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAccessibleName("展开模型简介");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");

    const collapsed = await preview.evaluate((element) => ({
      clientHeight: element.clientHeight,
      lineHeight: Number.parseFloat(getComputedStyle(element).lineHeight),
      scrollHeight: element.scrollHeight,
    }));
    expect(collapsed.clientHeight).toBeLessThanOrEqual(collapsed.lineHeight * 2 + 1);
    expect(collapsed.scrollHeight).toBeGreaterThan(collapsed.clientHeight);

    await toggle.focus();
    await page.keyboard.press("Shift+Tab");
    await expect(description.locator("a:focus")).toHaveCount(0);
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(toggle).toHaveAccessibleName("收起模型简介");
    await expect(toggle).toBeFocused();
    await expect(preview).toBeHidden();
    await expect(description).toBeVisible();
    await expect(description).toHaveCSS("overflow-y", "auto");
    await expect(description).toHaveAttribute("role", "region");
    await expect(description).toHaveAttribute("tabindex", "0");
    await expect(description).toHaveAccessibleName("模型简介全文");
    await page.waitForTimeout(100);
    await expect(toggle).toBeVisible();
    const expanded = await description.evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
    }));
    expect(expanded.clientHeight).toBeGreaterThan(collapsed.clientHeight);
    expect(expanded.scrollHeight).toBeGreaterThan(expanded.clientHeight);

    await page.keyboard.press("Space");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toBeFocused();
    await expect(preview).toBeVisible();
    await expect(description).toBeHidden();
  });

  test("短简介直接显示可交互的完整 Markdown，且不显示展开按钮", async ({
    page,
  }) => {
    await installModelViewMock(page, {
      description: {
        zh: "一行 **简介**，包含 `代码` 与 [站内链接](/info)。",
      },
    });

    await page.goto(`/zh/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

    const description = page.getByTestId("model-description-markdown");
    await expect(description).toBeVisible();
    await expect(description.locator("strong")).toHaveText("简介");
    await expect(description.locator("code")).toHaveText("代码");
    await expect(
      description.getByRole("link", { name: "站内链接" }),
    ).toBeVisible();
    await expect(page.getByTestId("model-description-preview")).toBeHidden();
    await expect(
      page.getByTestId("model-description-toggle"),
    ).toBeHidden();
  });

  test("英文路由下的相对链接保留 locale", async ({ page }) => {
    await installModelViewMock(page, {
      description: {
        zh: "[站内链接](/info)",
        en: "[Internal link](/info)",
      },
    });

    await page.goto(`/en/models/${MOCK_MODEL_VIEW_RUN_DIR}`);

    const description = page.getByTestId("model-description-markdown");
    await expect(description).toBeVisible();
    await expect(
      description.getByRole("link", { name: "Internal link" }),
    ).toHaveAttribute("href", "/en/info");
  });
});
