import { expect, test, type BrowserContext } from "@playwright/test";

const MOCK_RUN_DIR = "mock-run-scroll-restore";
const MOCK_NARROW_RUN_DIR = "mock-run-scroll-restore-narrow";
const MOCK_BLURHASH = "LEHV6nWB2yk8pyo0adR*.7kCMdnj";
const MOCK_WIDE_X_COLUMNS = Array.from({ length: 6 }, (_, index) => ({
  type: "normal",
  description: { zh: `列 ${index + 1}` },
}));
const MOCK_NARROW_X_COLUMNS = Array.from({ length: 2 }, (_, index) => ({
  type: "normal",
  description: { zh: `列 ${index + 1}` },
}));
const MOCK_Y_INDEXES = Array.from({ length: 240 }, (_, index) => index);

type MockRouteOptions = {
  runDir: string;
  xColumns: typeof MOCK_WIDE_X_COLUMNS;
};

function buildBootstrap({ runDir, xColumns }: MockRouteOptions) {
  return {
    run: {
      run_id: "mock-run-id",
      created_at: "2026-04-11T00:00:00.000Z",
      run_dir: runDir,
      selection: {
        total_cells: xColumns.length * MOCK_Y_INDEXES.length,
      },
      model: {
        name: "Mock Scroll Restore Run",
        description: {
          zh: "用于验证详情页重新进入后是否保留滚动位置。",
        },
      },
      workflow: null,
    },
    xLabels: xColumns.map((column) => column.description.zh),
    yLabels: MOCK_Y_INDEXES.map((yIndex) => `第 ${yIndex} 行`),
    x_columns: xColumns,
    y_indexes: MOCK_Y_INDEXES,
    y_labels: MOCK_Y_INDEXES.map((yIndex) => `第 ${yIndex} 行`),
    prompts: [],
    blurhash_cells: MOCK_Y_INDEXES.flatMap((yIndex) =>
      xColumns.map((_, xIndex) => ({
        x_index: xIndex,
        y_index: yIndex,
        batch_index: 0,
        category: "normal",
        width: 512,
        height: 768,
        blurhash: MOCK_BLURHASH,
      })),
    ),
  };
}

function buildRowPayload(
  { runDir, xColumns }: MockRouteOptions,
  yIndex: number,
) {
  return {
    run_dir: runDir,
    y_index: yIndex,
    cells: xColumns.map((_, xIndex) => ({
      x_index: xIndex,
      y_index: yIndex,
      items: [
        {
          batch_index: 0,
          category: "normal",
          width: 512,
          height: 768,
          blurhash: MOCK_BLURHASH,
          meta: {
            seed: String(10_000 + yIndex),
            prompt_id: null,
            prompt_hash: `prompt-hash-${yIndex}`,
            positive_prompt: `mock prompt ${xIndex}-${yIndex}`,
            y_value: `第 ${yIndex} 行`,
          },
          thumb: {
            webp: {
              bucket: "public",
              cache_key: `thumb-${xIndex}-${yIndex}`,
              key: `runs/${runDir}/images/${xIndex}-${yIndex}.webp`,
            },
          },
          display: null,
        },
      ],
    })),
  };
}

async function installMockRoutes(
  context: BrowserContext,
  options: MockRouteOptions,
) {
  const bootstrap = buildBootstrap(options);

  await context.route(
    new RegExp(`/api/comfyui/run/${options.runDir}(\\?.*)?$`),
    async (route) => {
      await route.fulfill({
        json: bootstrap,
      });
    },
  );

  await context.route(
    new RegExp(`/api/comfyui/run/${options.runDir}/grid(\\?.*)?$`),
    async (route) => {
      await route.fulfill({
        json: bootstrap,
      });
    },
  );

  await context.route(
    new RegExp(`/api/comfyui/run/${options.runDir}/row\\?.*$`),
    async (route) => {
      const requestUrl = new URL(route.request().url());
      const yIndex = Number(requestUrl.searchParams.get("y_index") ?? "0");
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({
        json: buildRowPayload(options, Number.isFinite(yIndex) ? yIndex : 0),
      });
    },
  );

  await context.route(
    new RegExp(`/runs/${options.runDir}/view/current\\.json(\\?.*)?$`),
    async (route) => {
      await route.fulfill({
        json: {
          schema_version: 2,
          run_dir: options.runDir,
          release_id: "mock-release",
          bootstrap_sfw_key: `runs/${options.runDir}/view/v2/mock-release/bootstrap.sfw.json`,
          public_row_prefix: `runs/${options.runDir}/view/v2/mock-release/rows/public/`,
        },
      });
    },
  );

  await context.route(
    new RegExp(
      `/runs/${options.runDir}/view/v2/mock-release/bootstrap\\.sfw\\.json(\\?.*)?$`,
    ),
    async (route) => {
      await route.fulfill({ json: bootstrap });
    },
  );

  await context.route(
    new RegExp(
      `/runs/${options.runDir}/view/v2/mock-release/rows/public/\\d+\\.json(\\?.*)?$`,
    ),
    async (route) => {
      const match = route
        .request()
        .url()
        .match(/\/public\/(\d+)\.json/);
      const yIndex = match ? Number(match[1]) : 0;
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({
        json: buildRowPayload(options, Number.isFinite(yIndex) ? yIndex : 0),
      });
    },
  );

  await context.route(
    new RegExp(`/runs/${options.runDir}/images/.*\\.webp(\\?.*)?$`),
    async (route) => {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "image/webp" },
        body: Buffer.from([]),
      });
    },
  );
}

test.describe("task 13: model detail scroll restoration", () => {
  test("reopening the page keeps the current row in view", async ({
    browser,
  }) => {
    const firstContext = await browser.newContext();
    await installMockRoutes(firstContext, {
      runDir: MOCK_RUN_DIR,
      xColumns: MOCK_WIDE_X_COLUMNS,
    });
    const page = await firstContext.newPage();

    await page.goto(`/models/${MOCK_RUN_DIR}`);

    const grid = page.getByTestId("run-grid");
    const scrollEl = page.getByTestId("run-grid-scroll");

    await expect(grid).toBeVisible();
    await expect(page.getByTestId("run-grid-y-label").first()).toContainText(
      "第 0 行",
    );
    await expect
      .poll(
        async () => Number((await grid.getAttribute("data-row-height")) ?? "0"),
        { timeout: 10_000 },
      )
      .toBeGreaterThan(0);

    const rowHeight = Number(
      (await grid.getAttribute("data-row-height")) ?? "0",
    );
    expect(rowHeight).toBeGreaterThan(0);

    const targetRowIndex = 100;
    await scrollEl.evaluate(
      (el, targetOffset) => {
        el.scrollTop = targetOffset;
      },
      rowHeight * targetRowIndex + rowHeight / 2,
    );

    const storageKey = `sd-style-lab:model-grid-anchor:${MOCK_RUN_DIR}`;
    await expect
      .poll(
        () =>
          page.evaluate((key) => window.localStorage.getItem(key), storageKey),
        { timeout: 10_000 },
      )
      .not.toBeNull();

    await expect
      .poll(
        () =>
          page.evaluate((key) => {
            const raw = window.localStorage.getItem(key);
            if (!raw) return null;

            try {
              const parsed = JSON.parse(raw) as { yIndex?: unknown };
              return typeof parsed.yIndex === "number" ? parsed.yIndex : null;
            } catch {
              return null;
            }
          }, storageKey),
        { timeout: 10_000 },
      )
      .toBe(targetRowIndex);

    const beforeClose = Math.round(
      await scrollEl.evaluate((el) => el.scrollTop),
    );
    const storageState = await firstContext.storageState();

    await firstContext.close();

    const reopenedContext = await browser.newContext({ storageState });
    await installMockRoutes(reopenedContext, {
      runDir: MOCK_RUN_DIR,
      xColumns: MOCK_WIDE_X_COLUMNS,
    });
    const reopenedPage = await reopenedContext.newPage();

    await reopenedPage.goto("/");
    await reopenedPage.goto(`/models/${MOCK_RUN_DIR}`);

    const reopenedGrid = reopenedPage.getByTestId("run-grid");
    const reopenedScrollEl = reopenedPage.getByTestId("run-grid-scroll");

    await expect(reopenedGrid).toBeVisible();
    await expect
      .poll(async () =>
        Math.round(await reopenedScrollEl.evaluate((el) => el.scrollTop)),
      )
      .toBeGreaterThan(rowHeight * 95);

    const afterReopen = Math.round(
      await reopenedScrollEl.evaluate((el) => el.scrollTop),
    );
    const tolerance = Math.max(rowHeight, 48);

    expect(Math.abs(afterReopen - beforeClose)).toBeLessThanOrEqual(tolerance);

    await reopenedContext.close();
  });

  test("reopening the page restores rows beyond the initial estimated height", async ({
    browser,
  }) => {
    const firstContext = await browser.newContext();
    await installMockRoutes(firstContext, {
      runDir: MOCK_NARROW_RUN_DIR,
      xColumns: MOCK_NARROW_X_COLUMNS,
    });
    const page = await firstContext.newPage();

    await page.goto(`/models/${MOCK_NARROW_RUN_DIR}`);

    const grid = page.getByTestId("run-grid");
    const scrollEl = page.getByTestId("run-grid-scroll");

    await expect(grid).toBeVisible();
    await expect
      .poll(
        async () => Number((await grid.getAttribute("data-row-height")) ?? "0"),
        { timeout: 10_000 },
      )
      .toBeGreaterThan(0);

    const rowHeight = Number(
      (await grid.getAttribute("data-row-height")) ?? "0",
    );
    const targetRowIndex = 190;
    await scrollEl.evaluate(
      (el, targetOffset) => {
        el.scrollTop = targetOffset;
      },
      rowHeight * targetRowIndex + rowHeight / 2,
    );

    const storageKey = `sd-style-lab:model-grid-anchor:${MOCK_NARROW_RUN_DIR}`;
    await expect
      .poll(
        () =>
          page.evaluate((key) => {
            const raw = window.localStorage.getItem(key);
            if (!raw) return null;

            try {
              const parsed = JSON.parse(raw) as { yIndex?: unknown };
              return typeof parsed.yIndex === "number" ? parsed.yIndex : null;
            } catch {
              return null;
            }
          }, storageKey),
        { timeout: 10_000 },
      )
      .toBe(targetRowIndex);

    const beforeClose = Math.round(
      await scrollEl.evaluate((el) => el.scrollTop),
    );
    const storageState = await firstContext.storageState();

    await firstContext.close();

    const reopenedContext = await browser.newContext({ storageState });
    await installMockRoutes(reopenedContext, {
      runDir: MOCK_NARROW_RUN_DIR,
      xColumns: MOCK_NARROW_X_COLUMNS,
    });
    const reopenedPage = await reopenedContext.newPage();

    await reopenedPage.goto(`/models/${MOCK_NARROW_RUN_DIR}`);

    const reopenedGrid = reopenedPage.getByTestId("run-grid");
    const reopenedScrollEl = reopenedPage.getByTestId("run-grid-scroll");

    await expect(reopenedGrid).toBeVisible();
    await expect
      .poll(
        async () =>
          Math.round(await reopenedScrollEl.evaluate((el) => el.scrollTop)),
        { timeout: 10_000 },
      )
      .toBeGreaterThan(rowHeight * 185);

    const afterReopen = Math.round(
      await reopenedScrollEl.evaluate((el) => el.scrollTop),
    );
    const tolerance = Math.max(rowHeight, 48);

    expect(Math.abs(afterReopen - beforeClose)).toBeLessThanOrEqual(tolerance);

    await reopenedContext.close();
  });

  test("toggling the grid tools keeps bottom-region scroll anchors stable", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    await installMockRoutes(context, {
      runDir: MOCK_NARROW_RUN_DIR,
      xColumns: MOCK_NARROW_X_COLUMNS,
    });
    const page = await context.newPage();

    await page.goto(`/models/${MOCK_NARROW_RUN_DIR}`);

    const grid = page.getByTestId("run-grid");
    const scrollEl = page.getByTestId("run-grid-scroll");

    await expect(grid).toBeVisible();
    await expect
      .poll(
        async () => Number((await grid.getAttribute("data-row-height")) ?? "0"),
        { timeout: 10_000 },
      )
      .toBeGreaterThan(0);

    const rowHeight = Number(
      (await grid.getAttribute("data-row-height")) ?? "0",
    );
    const targetRowIndex = 220;
    await scrollEl.evaluate(
      (el, targetOffset) => {
        el.scrollTop = targetOffset;
      },
      rowHeight * targetRowIndex + rowHeight / 2,
    );

    const storageKey = `sd-style-lab:model-grid-anchor:${MOCK_NARROW_RUN_DIR}`;
    await expect
      .poll(
        () =>
          page.evaluate((key) => {
            const raw = window.localStorage.getItem(key);
            if (!raw) return null;

            try {
              const parsed = JSON.parse(raw) as { yIndex?: unknown };
              return typeof parsed.yIndex === "number" ? parsed.yIndex : null;
            } catch {
              return null;
            }
          }, storageKey),
        { timeout: 10_000 },
      )
      .toBe(targetRowIndex);

    const beforeToggle = Math.round(
      await scrollEl.evaluate((el) => el.scrollTop),
    );

    await page.getByLabel("打开网格工具").click();
    await page.getByLabel("收起工具面板").waitFor({ timeout: 5_000 });
    await expect
      .poll(
        async () => Number((await grid.getAttribute("data-row-height")) ?? "0"),
        { timeout: 10_000 },
      )
      .toBeLessThan(rowHeight);

    await page.getByLabel("收起工具面板").click();
    await page.getByLabel("打开网格工具").waitFor({ timeout: 5_000 });
    await expect
      .poll(
        async () => Math.round(await scrollEl.evaluate((el) => el.scrollTop)),
        { timeout: 10_000 },
      )
      .toBeGreaterThan(rowHeight * 215);

    const afterToggle = Math.round(
      await scrollEl.evaluate((el) => el.scrollTop),
    );
    const tolerance = Math.max(rowHeight, 48);

    expect(Math.abs(afterToggle - beforeToggle)).toBeLessThanOrEqual(tolerance);
    await expect
      .poll(
        () =>
          page.evaluate((key) => {
            const raw = window.localStorage.getItem(key);
            if (!raw) return null;

            try {
              const parsed = JSON.parse(raw) as { yIndex?: unknown };
              return typeof parsed.yIndex === "number" ? parsed.yIndex : null;
            } catch {
              return null;
            }
          }, storageKey),
        { timeout: 10_000 },
      )
      .toBe(targetRowIndex);

    await context.close();
  });
});
