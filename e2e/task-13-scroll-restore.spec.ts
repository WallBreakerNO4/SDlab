import { expect, test, type BrowserContext } from "@playwright/test";

const MOCK_RUN_DIR = "mock-run-scroll-restore";
const MOCK_BLURHASH = "LEHV6nWB2yk8pyo0adR*.7kCMdnj";
const MOCK_X_COLUMNS = Array.from({ length: 6 }, (_, index) => ({
  type: "normal",
  description: { zh: `列 ${index + 1}` },
}));
const MOCK_Y_INDEXES = Array.from({ length: 240 }, (_, index) => index);

function buildRowPayload(yIndex: number) {
  return {
    run_dir: MOCK_RUN_DIR,
    y_index: yIndex,
    cells: MOCK_X_COLUMNS.map((_, xIndex) => ({
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
            prompt_hash: `prompt-hash-${yIndex}`,
            positive_prompt: `mock prompt ${xIndex}-${yIndex}`,
            y_value: `第 ${yIndex} 行`,
          },
          thumb: null,
          display: null,
        },
      ],
    })),
  };
}

async function installMockRoutes(context: BrowserContext) {
  await context.route(
    new RegExp(`/api/comfyui/run/${MOCK_RUN_DIR}(\\?.*)?$`),
    async (route) => {
      await route.fulfill({
        json: {
          run: {
            run_id: "mock-run-id",
            created_at: "2026-04-11T00:00:00.000Z",
            run_dir: MOCK_RUN_DIR,
            selection: {
              total_cells: MOCK_X_COLUMNS.length * MOCK_Y_INDEXES.length,
            },
            model: {
              name: "Mock Scroll Restore Run",
              description: {
                zh: "用于验证详情页重新进入后是否保留滚动位置。",
              },
            },
            workflow: null,
          },
          xLabels: MOCK_X_COLUMNS.map((column) => column.description.zh),
          yLabels: MOCK_Y_INDEXES.map((yIndex) => `第 ${yIndex} 行`),
          x_columns: MOCK_X_COLUMNS,
          y_indexes: MOCK_Y_INDEXES,
        },
      });
    },
  );

  await context.route(
    new RegExp(`/api/comfyui/run/${MOCK_RUN_DIR}/grid(\\?.*)?$`),
    async (route) => {
      await route.fulfill({
        json: {
          x_columns: MOCK_X_COLUMNS,
          y_indexes: MOCK_Y_INDEXES,
          y_labels: MOCK_Y_INDEXES.map((yIndex) => `第 ${yIndex} 行`),
          x_count: MOCK_X_COLUMNS.length,
          y_count: MOCK_Y_INDEXES.length,
          cells: {},
          blurhash_cells: MOCK_Y_INDEXES.slice(0, 40).flatMap((yIndex) =>
            MOCK_X_COLUMNS.map((_, xIndex) => ({
              x_index: xIndex,
              y_index: yIndex,
              batch_index: 0,
              category: "normal",
              width: 512,
              height: 768,
              blurhash: MOCK_BLURHASH,
            })),
          ),
        },
      });
    },
  );

  await context.route(
    new RegExp(`/api/comfyui/run/${MOCK_RUN_DIR}/row\\?.*$`),
    async (route) => {
      const requestUrl = new URL(route.request().url());
      const yIndex = Number(requestUrl.searchParams.get("y_index") ?? "0");
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({
        json: buildRowPayload(Number.isFinite(yIndex) ? yIndex : 0),
      });
    },
  );
}

test.describe("task 13: model detail scroll restoration", () => {
  test("reopening the page keeps the current row in view", async ({ browser }) => {
    const firstContext = await browser.newContext();
    await installMockRoutes(firstContext);
    const page = await firstContext.newPage();

    await page.goto(`/models/${MOCK_RUN_DIR}`);

    const grid = page.getByTestId("run-grid");
    const scrollEl = page.getByTestId("run-grid-scroll");

    await expect(grid).toBeVisible();
    await expect(page.getByTestId("run-grid-y-label").first()).toContainText("第 0 行");
    await expect
      .poll(
        async () =>
          Number((await grid.getAttribute("data-row-height")) ?? "0"),
        { timeout: 10_000 },
      )
      .toBeGreaterThan(0);

    const rowHeight = Number((await grid.getAttribute("data-row-height")) ?? "0");
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

    const beforeClose = Math.round(await scrollEl.evaluate((el) => el.scrollTop));
    const storageState = await firstContext.storageState();

    await firstContext.close();

    const reopenedContext = await browser.newContext({ storageState });
    await installMockRoutes(reopenedContext);
    const reopenedPage = await reopenedContext.newPage();

    await reopenedPage.goto("/");
    await reopenedPage.goto(`/models/${MOCK_RUN_DIR}`);

    const reopenedGrid = reopenedPage.getByTestId("run-grid");
    const reopenedScrollEl = reopenedPage.getByTestId("run-grid-scroll");

    await expect(reopenedGrid).toBeVisible();
    await expect
      .poll(
        async () =>
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
});
