import {
  expect,
  test,
  type Locator,
  type Page,
  type Response as PlaywrightResponse,
} from "@playwright/test";

import { E2E_AUTH_STATE_PATH, hasE2EAuthEnv } from "./e2e-auth-state";

const hasAuthEnv = hasE2EAuthEnv();

// 生产数据（run_style_items 各 432 行）：Mixer / Legacy 两形态各取一个 run
const MIXER_RUN_DIR = "anima-base-1-arist-mixer";
const LEGACY_RUN_DIR = "nai-diffusion-4-5-full";
const GUEST_RELEASE_ID = "guest-style-favorite-release";
const GUEST_BLURHASH = "LEHV6nWB2yk8pyo0adR*.7kCMdnj";

interface StyleItem {
  y_index: number;
  style_key: string;
}

/** 从活体 style-items API 取真实 y_index ↔ style_key 映射（只依赖结构，不写死 label） */
async function fetchStyleItems(
  page: Page,
  runDir: string,
): Promise<StyleItem[]> {
  const res = await page.request.get(`/api/comfyui/run/${runDir}/style-items`);
  expect(res.ok(), `style-items API 不可用：${runDir}`).toBeTruthy();
  return (await res.json()) as StyleItem[];
}

function styleKeyAt(items: StyleItem[], yIndex: number): string {
  const item = items.find((entry) => entry.y_index === yIndex);
  if (!item) throw new Error(`style-items 缺少 y_index=${yIndex}`);
  return item.style_key;
}

/** 经应用 API 直接收藏（测试数据只用测试用户自己的收藏行） */
async function putFavorite(
  page: Page,
  styleKey: string,
  label: string,
): Promise<void> {
  const res = await page.request.put("/api/viewer/style-favorites", {
    data: { style_key: styleKey, label },
  });
  expect(res.ok(), `PUT 收藏失败：HTTP ${res.status()}`).toBeTruthy();
}

/** 用例收尾清理；失败静默（global teardown 最终兜底清空） */
async function deleteFavoriteQuiet(
  page: Page,
  styleKey: string,
): Promise<void> {
  try {
    await page.request.delete(
      `/api/viewer/style-favorites/${encodeURIComponent(styleKey)}`,
    );
  } catch {
    // 清理兜底失败不阻断用例结果
  }
}

/** 指定行的行标签星标 */
function rowStar(page: Page, yIndex: number): Locator {
  return page
    .locator(`[data-testid="run-grid-row"][data-row-index="${yIndex}"]`)
    .getByTestId("run-grid-favorite-star");
}

/**
 * AuthProvider 解析出用户后 useStyleFavorites 才发 GET；
 * 在导航 / reload 前注册等待，响应用来作为「登录态就绪」信号。
 */
function waitFavoritesLoaded(page: Page): Promise<PlaywrightResponse> {
  return page.waitForResponse(
    (res) =>
      res.url().includes("/api/viewer/style-favorites") &&
      res.request().method() === "GET",
    { timeout: 20_000 },
  );
}

interface ComparisonSliceCapture {
  runDirs: string[];
  placements: Array<{ run_dir: string; y_index: number }>;
}

async function mockComparisonSliceBlurhashFallback(
  page: Page,
  captureStyleKey?: string,
): Promise<{ capture: Promise<ComparisonSliceCapture> | null }> {
  let resolveCapture: ((value: ComparisonSliceCapture) => void) | null = null;
  const capture = captureStyleKey
    ? new Promise<ComparisonSliceCapture>((resolve) => {
        resolveCapture = resolve;
      })
    : null;

  await page.route("**/api/viewer/style-comparison/slice", async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as {
      placements?: Record<
        string,
        Array<{
          run_dir: string;
          y_index: number;
          blurhashes?: Array<[number, number, string]>;
        }>
      >;
    };
    if (captureStyleKey && resolveCapture) {
      const request = route.request().postDataJSON() as {
        run_dirs?: unknown;
      };
      const runDirs = Array.isArray(request.run_dirs)
        ? request.run_dirs.filter(
            (runDir): runDir is string => typeof runDir === "string",
          )
        : [];
      const placements = payload.placements?.[captureStyleKey] ?? [];
      const placedRunDirs = [...new Set(placements.map((item) => item.run_dir))];
      const protectedRunDirs = new Set(placedRunDirs.slice(0, 2));
      const missingRunDir = runDirs.find(
        (runDir) => !protectedRunDirs.has(runDir),
      );
      const capturedPlacements = missingRunDir
        ? placements.filter((item) => item.run_dir !== missingRunDir)
        : placements;
      if (payload.placements) {
        payload.placements[captureStyleKey] = capturedPlacements;
      }
      resolveCapture({
        runDirs,
        placements: capturedPlacements.map(({ run_dir, y_index }) => ({
          run_dir,
          y_index,
        })),
      });
      resolveCapture = null;
    }
    for (const placements of Object.values(payload.placements ?? {})) {
      for (const placement of placements) {
        placement.blurhashes = Array.from({ length: 20 }, (_, xIndex) => [
          xIndex,
          0,
          GUEST_BLURHASH,
        ]);
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    await route.fulfill({ response, json: payload });
  });

  await page.route("**/api/private-object?*", async (route) => {
    const key = new URL(route.request().url()).searchParams.get("key") ?? "";
    if (key.includes("/sha256/")) {
      await new Promise((resolve) => setTimeout(resolve, 1_000));
      await route.continue();
      return;
    }
    if (!key.includes("/rows/")) {
      await route.continue();
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 1_000));
    const response = await route.fetch();
    const payload = (await response.json()) as {
      cells?: Array<{ items?: Array<Record<string, unknown>> }>;
    };
    for (const cell of payload.cells ?? []) {
      for (const item of cell.items ?? []) delete item.blurhash;
    }
    await route.fulfill({ response, json: payload });
  });

  return { capture };
}

/** 点击星标并等待对应 mutation 响应落库，避免乐观更新与后续断言竞争 */
async function clickStarAndWait(
  page: Page,
  star: Locator,
  method: "PUT" | "DELETE",
): Promise<void> {
  const [res] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes("/api/viewer/style-favorites") &&
        r.request().method() === method,
      { timeout: 20_000 },
    ),
    star.click(),
  ]);
  expect(
    res.ok(),
    `${method} 收藏 API 失败：HTTP ${res.status()}`,
  ).toBeTruthy();
}

test.describe("task 14: style favorites guest flows", () => {
  test("task 14: guest clicking a row star opens the login dialog", async ({
    page,
  }) => {
    await page.route(
      new RegExp(`/runs/${MIXER_RUN_DIR}/view/current\\.json(\\?.*)?$`),
      async (route) => {
        await route.fulfill({
          json: {
            schema_version: 2,
            run_dir: MIXER_RUN_DIR,
            release_id: GUEST_RELEASE_ID,
            bootstrap_sfw_key: `runs/${MIXER_RUN_DIR}/view/v2/${GUEST_RELEASE_ID}/bootstrap.sfw.json`,
            public_row_prefix: `runs/${MIXER_RUN_DIR}/view/v2/${GUEST_RELEASE_ID}/rows/public/`,
          },
        });
      },
    );
    await page.route(
      new RegExp(
        `/runs/${MIXER_RUN_DIR}/view/v2/${GUEST_RELEASE_ID}/bootstrap\\.sfw\\.json(\\?.*)?$`,
      ),
      async (route) => {
        await route.fulfill({
          json: {
            run: {
              run_id: "guest-style-favorite-run-id",
              created_at: "2026-07-17T00:00:00.000Z",
              run_dir: MIXER_RUN_DIR,
              selection: { total_cells: 1 },
              model: {
                name: "Guest Style Favorite Run",
                description: { zh: "未登录收藏入口测试。" },
              },
              workflow: null,
            },
            xLabels: ["构图示例"],
            yLabels: ["@guest-artist"],
            x_columns: [{ type: "normal", description: { zh: "构图示例" } }],
            y_indexes: [0],
            y_labels: ["@guest-artist"],
            prompts: [],
            blurhash_cells: [
              {
                x_index: 0,
                y_index: 0,
                batch_index: 0,
                category: "normal",
                width: 512,
                height: 768,
                blurhash: GUEST_BLURHASH,
              },
            ],
          },
        });
      },
    );
    await page.route(
      new RegExp(
        `/runs/${MIXER_RUN_DIR}/view/v2/${GUEST_RELEASE_ID}/rows/public/0\\.json(\\?.*)?$`,
      ),
      async (route) => {
        await route.fulfill({
          json: {
            run_dir: MIXER_RUN_DIR,
            y_index: 0,
            cells: [
              {
                x_index: 0,
                y_index: 0,
                items: [
                  {
                    batch_index: 0,
                    category: "normal",
                    width: 512,
                    height: 768,
                    blurhash: GUEST_BLURHASH,
                    meta: {
                      seed: "14000",
                      prompt_hash: "guest-style-favorite-prompt",
                      positive_prompt: "guest prompt",
                      y_value: "@guest-artist",
                    },
                    thumb: null,
                    display: null,
                  },
                ],
              },
            ],
          },
        });
      },
    );
    await page.route(
      `**/api/comfyui/run/${MIXER_RUN_DIR}/style-items`,
      async (route) => {
        await route.fulfill({
          json: [{ y_index: 0, style_key: "e2e-style-table:0" }],
        });
      },
    );
    await page.goto(`/zh/models/${MIXER_RUN_DIR}`);
    const star = rowStar(page, 0);
    await expect(star).toBeVisible({ timeout: 15_000 });
    await expect(star).toHaveAttribute("aria-pressed", "false");

    await star.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: /GitHub/ })).toBeVisible();
  });

  test("task 14: /zh/favorites shows the login gate for guests", async ({
    page,
  }) => {
    await page.goto("/zh/favorites");
    await expect(
      page.getByRole("heading", { name: "登录以查看收藏" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "登录 / 注册" }),
    ).toBeVisible();
  });

  test("task 14: /en/favorites shows the login gate for guests", async ({
    page,
  }) => {
    await page.goto("/en/favorites");
    await expect(
      page.getByRole("heading", { name: "Sign in to view favorites" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Sign in / Register" }),
    ).toBeVisible();
  });
});

test.describe("task 14: style favorites signed-in flows", () => {
  test.use({ storageState: E2E_AUTH_STATE_PATH });
  test.skip(
    !hasAuthEnv,
    "缺少 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY，跳过已登录用例",
  );

  test("task 14: mixer run star toggle persists across reload", async ({
    page,
  }) => {
    const items = await fetchStyleItems(page, MIXER_RUN_DIR);
    const styleKey = styleKeyAt(items, 0);

    const favoritesLoaded = waitFavoritesLoaded(page);
    await page.goto(`/zh/models/${MIXER_RUN_DIR}`);
    await favoritesLoaded;
    const star = rowStar(page, 0);
    await expect(star).toBeVisible({ timeout: 15_000 });

    try {
      // 收藏：乐观置位 + PUT 落库
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await clickStarAndWait(page, star, "PUT");
      await expect(star).toHaveAttribute("aria-pressed", "true");

      // 刷新后保持
      const reloaded = waitFavoritesLoaded(page);
      await page.reload();
      await reloaded;
      const starAfterReload = rowStar(page, 0);
      await expect(starAfterReload).toBeVisible({ timeout: 15_000 });
      await expect(starAfterReload).toHaveAttribute("aria-pressed", "true", {
        timeout: 10_000,
      });

      // 取消：乐观复位 + DELETE 落库
      await clickStarAndWait(page, starAfterReload, "DELETE");
      await expect(starAfterReload).toHaveAttribute("aria-pressed", "false");

      // 刷新后仍为未收藏
      const reloadedAgain = waitFavoritesLoaded(page);
      await page.reload();
      await reloadedAgain;
      await expect(rowStar(page, 0)).toHaveAttribute("aria-pressed", "false", {
        timeout: 10_000,
      });
    } finally {
      await deleteFavoriteQuiet(page, styleKey);
    }
  });

  test("task 14: favorites panel lists the favorite and jumps to its grid row", async ({
    page,
  }) => {
    const targetYIndex = 100;
    const lineNumber = targetYIndex + 1;
    const items = await fetchStyleItems(page, MIXER_RUN_DIR);
    const styleKey = styleKeyAt(items, targetYIndex);
    await putFavorite(page, styleKey, "e2e 面板跳转验证收藏");

    try {
      // 工具面板默认收起；经 localStorage 预设展开（与实现同一 key）
      await page.addInitScript(() => {
        window.localStorage.setItem("sd-style-lab:grid-tools-open", "true");
      });
      const favoritesLoaded = waitFavoritesLoaded(page);
      await page.goto(`/zh/models/${MIXER_RUN_DIR}`);
      await favoritesLoaded;

      // 面板项 = 行号 + 当前 run 行标签（结构断言，不写死文案）
      const panelItem = page.locator(
        `[data-testid="run-grid-favorites-item"][data-line-number="${lineNumber}"]`,
      );
      await expect(panelItem).toBeVisible({ timeout: 15_000 });
      await expect(panelItem).toContainText(`#${lineNumber}`);
      const panelText = ((await panelItem.textContent()) ?? "").trim();
      expect(panelText.length).toBeGreaterThan(`#${lineNumber}`.length);

      const grid = page.getByTestId("run-grid");
      const scrollEl = page.getByTestId("run-grid-scroll");
      await panelItem.click();
      await expect(page).toHaveURL(
        new RegExp(`/zh/models/${MIXER_RUN_DIR}#${lineNumber}$`),
      );
      const rowHeight = Number(
        (await grid.getAttribute("data-row-height")) ?? "0",
      );
      expect(rowHeight).toBeGreaterThan(0);
      await expect
        .poll(async () => scrollEl.evaluate((el) => el.scrollTop), {
          timeout: 10_000,
        })
        .toBeGreaterThan(rowHeight * 80);
      await expect(
        page.locator(
          `[data-testid="run-grid-row"][data-row-index="${targetYIndex}"]`,
        ),
      ).toBeVisible();
    } finally {
      await deleteFavoriteQuiet(page, styleKey);
    }
  });

  test("task 14: legacy run star toggle works", async ({ page }) => {
    const items = await fetchStyleItems(page, LEGACY_RUN_DIR);
    const styleKey = styleKeyAt(items, 0);

    const favoritesLoaded = waitFavoritesLoaded(page);
    await page.goto(`/zh/models/${LEGACY_RUN_DIR}`);
    await favoritesLoaded;
    const star = rowStar(page, 0);
    await expect(star).toBeVisible({ timeout: 15_000 });

    try {
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await clickStarAndWait(page, star, "PUT");
      await expect(star).toHaveAttribute("aria-pressed", "true");

      const reloaded = waitFavoritesLoaded(page);
      await page.reload();
      await reloaded;
      const starAfterReload = rowStar(page, 0);
      await expect(starAfterReload).toBeVisible({ timeout: 15_000 });
      await expect(starAfterReload).toHaveAttribute("aria-pressed", "true", {
        timeout: 10_000,
      });

      await clickStarAndWait(page, starAfterReload, "DELETE");
      await expect(starAfterReload).toHaveAttribute("aria-pressed", "false");
    } finally {
      await deleteFavoriteQuiet(page, styleKey);
    }
  });

  test("task 14: favorites page lists favorites and model link jumps to the grid row", async ({
    page,
  }) => {
    const items = await fetchStyleItems(page, MIXER_RUN_DIR);
    const favA = { styleKey: styleKeyAt(items, 10), label: "e2e 收藏甲" };
    const favB = {
      styleKey: styleKeyAt(items, 120),
      label: "e2e 收藏乙",
      yIndex: 120,
    };
    await putFavorite(page, favA.styleKey, favA.label);
    await putFavorite(page, favB.styleKey, favB.label);

    try {
      await page.goto("/zh/favorites");
      const entryA = page.locator(`[data-favorite-entry="${favA.styleKey}"]`);
      const entryB = page.locator(`[data-favorite-entry="${favB.styleKey}"]`);
      await expect(entryA).toBeVisible({ timeout: 15_000 });
      await expect(entryB).toBeVisible();
      await expect(entryA).toContainText(favA.label);
      await expect(entryB).toContainText(favB.label);

      // 可用模型列表（结构断言：含 mixer run 跳转链接，hash 为 1-based 行号）
      const jumpLink = entryB.locator(
        `a[href$="/models/${MIXER_RUN_DIR}#${favB.yIndex + 1}"]`,
      );
      await expect(jumpLink).toBeVisible();
      await jumpLink.click();

      await expect(page).toHaveURL(
        new RegExp(`/zh/models/${MIXER_RUN_DIR}#${favB.yIndex + 1}$`),
      );
      const grid = page.getByTestId("run-grid");
      await expect(grid).toBeVisible({ timeout: 15_000 });
      const rowHeight = Number(
        (await grid.getAttribute("data-row-height")) ?? "0",
      );
      expect(rowHeight).toBeGreaterThan(0);
      const scrollEl = page.getByTestId("run-grid-scroll");
      await expect
        .poll(async () => scrollEl.evaluate((el) => el.scrollTop), {
          timeout: 10_000,
        })
        .toBeGreaterThan(rowHeight * 100);
      await expect(
        page.locator(
          `[data-testid="run-grid-row"][data-row-index="${favB.yIndex}"]`,
        ),
      ).toBeVisible({ timeout: 10_000 });
    } finally {
      await deleteFavoriteQuiet(page, favA.styleKey);
      await deleteFavoriteQuiet(page, favB.styleKey);
    }
  });

  test("task 14: favorites comparison matrix shows every model in a horizontal workspace", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const items = await fetchStyleItems(page, MIXER_RUN_DIR);
    const styleKey = styleKeyAt(items, 30);
    await putFavorite(page, styleKey, "e2e 横向模型矩阵验证收藏");

    try {
      const { capture } = await mockComparisonSliceBlurhashFallback(
        page,
        styleKey,
      );
      expect(capture).not.toBeNull();
      await page.goto("/zh/favorites");
      const capturedSlice = await capture!;
      const matrix = page.getByTestId("comparison-matrix-scroll");
      const frames = page.getByTestId("comparison-image-frame");
      const placementByRunDir = new Map(
        capturedSlice.placements.map((placement) => [
          placement.run_dir,
          placement,
        ]),
      );
      expect(new Set(placementByRunDir.keys()).size).toBeGreaterThanOrEqual(2);
      expect(
        capturedSlice.runDirs.filter(
          (runDir) => !placementByRunDir.has(runDir),
        ).length,
      ).toBeGreaterThanOrEqual(1);
      await expect(matrix).toBeVisible({ timeout: 15_000 });
      await expect(frames).toHaveCount(capturedSlice.runDirs.length);

      for (const [index, runDir] of capturedSlice.runDirs.entries()) {
        const placement = placementByRunDir.get(runDir);
        const links = frames
          .nth(index)
          .locator('a[href*="/models/"][href*="#"]');
        if (!placement) {
          await expect(links).toHaveCount(0);
          continue;
        }
        const localizedHref = `/zh/models/${encodeURIComponent(runDir)}#${placement.y_index + 1}`;
        await expect(links).toHaveCount(1);
        await expect(links).toHaveAttribute("href", localizedHref);
        await expect(links).toHaveAttribute(
          "aria-label",
          new RegExp(`第 ${placement.y_index + 1} 行$`),
        );
        await expect(links).toHaveAttribute(
          "title",
          new RegExp(`第 ${placement.y_index + 1} 行$`),
        );
      }

      const jumpTarget = capturedSlice.placements[0];
      const jumpTargetIndex = capturedSlice.runDirs.indexOf(jumpTarget.run_dir);
      expect(jumpTargetIndex).toBeGreaterThanOrEqual(0);
      const frame = frames.nth(jumpTargetIndex);
      await expect(frame).toBeVisible({ timeout: 15_000 });
      const rowJumpLink = frame.locator(
        `a[href="/zh/models/${encodeURIComponent(jumpTarget.run_dir)}#${jumpTarget.y_index + 1}"]`,
      );
      await expect(rowJumpLink).toBeVisible({ timeout: 15_000 });
      await expect(
        page.getByTestId("comparison-image-skeleton").first(),
      ).toBeVisible();
      await expect(page.getByTestId("blurhash-canvas").first()).toBeVisible({
        timeout: 15_000,
      });
      const thumb = frame.getByTestId("run-grid-image");
      await expect(thumb).toHaveClass(/opacity-100/, { timeout: 15_000 });
      await expect(frame.getByTestId("blurhash-canvas")).toHaveClass(
        /opacity-0/,
      );
      await frame.locator('button[type="button"]').first().click();
      const previewDialog = page.getByRole("dialog");
      await expect(previewDialog).toBeVisible();
      await expect(previewDialog.getByTestId("blurhash-canvas")).toBeVisible();
      await page.keyboard.press("Escape");

      const initialScroll = await matrix.evaluate((element) => ({
        left: element.scrollLeft,
        top: element.scrollTop,
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
      }));
      expect(initialScroll.scrollWidth).toBeGreaterThan(
        initialScroll.clientWidth,
      );

      await matrix.dispatchEvent("wheel", {
        bubbles: true,
        cancelable: true,
        shiftKey: true,
        deltaX: 0,
        deltaY: 240,
      });
      await expect
        .poll(() => matrix.evaluate((element) => element.scrollLeft))
        .toBeGreaterThan(initialScroll.left);
      expect(await matrix.evaluate((element) => element.scrollTop)).toBe(
        initialScroll.top,
      );

      const frameBox = await frame.boundingBox();
      expect(frameBox).not.toBeNull();
      const rowJumpLinkBox = await rowJumpLink.boundingBox();
      expect(rowJumpLinkBox).not.toBeNull();
      expect(rowJumpLinkBox!.x + rowJumpLinkBox!.width).toBeGreaterThan(
        frameBox!.x + frameBox!.width - 40,
      );
      expect(rowJumpLinkBox!.y).toBeLessThan(frameBox!.y + 40);
      // 图片框应撑满单元格内容区：列宽 216 - 2.5 内边距 ×2,行高 312 - 内边距 20 - 下边框 1
      expect(frameBox!.width).toBeCloseTo(196, 0);
      expect(frameBox!.height).toBeCloseTo(291, 0);

      await expect(
        page.getByRole("button", { name: /上一组模型|Previous models/ }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: /下一组模型|Next models/ }),
      ).toHaveCount(0);

      await page.screenshot({
        path: "test-results/comparison-matrix-ui.png",
        fullPage: false,
      });

      await rowJumpLink.click();
      await expect(page).toHaveURL((url) => {
        return (
          url.pathname ===
            `/zh/models/${encodeURIComponent(jumpTarget.run_dir)}` &&
          url.hash === `#${jumpTarget.y_index + 1}`
        );
      });
    } finally {
      await deleteFavoriteQuiet(page, styleKey);
    }
  });

  test("task 14: comparison detail falls back to slice blurhash for legacy row manifests", async ({
    page,
  }) => {
    const items = await fetchStyleItems(page, MIXER_RUN_DIR);
    const styleKey = styleKeyAt(items, 31);
    await putFavorite(page, styleKey, "e2e 详情 BlurHash 回退收藏");

    try {
      await mockComparisonSliceBlurhashFallback(page);
      await page.goto(`/zh/favorites/${encodeURIComponent(styleKey)}`);

      const firstCell = page.locator("tbody td").first();
      const placeholder = firstCell.getByTestId("blurhash-canvas");
      await expect(placeholder).toBeVisible({ timeout: 15_000 });
      await expect(firstCell.getByTestId("run-grid-image")).toHaveClass(
        /opacity-100/,
        { timeout: 15_000 },
      );
      await expect(placeholder).toHaveClass(/opacity-0/);
    } finally {
      await deleteFavoriteQuiet(page, styleKey);
    }
  });

  test("task 14: favorites page remove deletes the entry", async ({ page }) => {
    const items = await fetchStyleItems(page, LEGACY_RUN_DIR);
    const styleKey = styleKeyAt(items, 3);
    await putFavorite(page, styleKey, "e2e 待删除收藏");

    try {
      await page.goto("/zh/favorites");
      const entry = page.locator(`[data-favorite-entry="${styleKey}"]`);
      await expect(entry).toBeVisible({ timeout: 15_000 });

      await entry.getByRole("button", { name: "取消收藏" }).click();

      await expect(entry).toHaveCount(0);
      await expect(
        page.getByText(
          "暂无收藏。在模型详情页点击行标签上的星标即可收藏画师串。",
        ),
      ).toBeVisible();
    } finally {
      await deleteFavoriteQuiet(page, styleKey);
    }
  });
});
