import { expect, test } from "@playwright/test";

const MOCK_RUN_DIR = "mock-run-hash-jump";
const MOCK_BLURHASH = "LEHV6nWB2yk8pyo0adR*.7kCMdnj";
const MOCK_X_COLUMNS = Array.from({ length: 6 }, (_, index) => ({
  type: "normal",
  description: { zh: `列 ${index + 1}` },
}));
const MOCK_Y_INDEXES = Array.from({ length: 240 }, (_, index) => index);
const HASH_LINE_NUMBER = 121;
const EXPECTED_Y_INDEX = HASH_LINE_NUMBER - 1;

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
            seed: String(20_000 + yIndex),
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

test.describe("task 13: model detail hash jump", () => {
  test("url hash jumps to the requested line before restoring saved scroll", async ({
    page,
  }) => {
    await page.route(
      new RegExp(`/api/comfyui/run/${MOCK_RUN_DIR}(\\?.*)?$`),
      async (route) => {
        await route.fulfill({
          json: {
            run: {
              run_id: "mock-run-id",
              created_at: "2026-04-17T00:00:00.000Z",
              run_dir: MOCK_RUN_DIR,
              selection: {
                total_cells: MOCK_X_COLUMNS.length * MOCK_Y_INDEXES.length,
              },
              model: {
                name: "Mock Hash Jump Run",
                description: {
                  zh: "用于验证详情页可通过 URL 哈希跳转到指定行。",
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

    await page.route(
      new RegExp(`/api/comfyui/run/${MOCK_RUN_DIR}/grid(\\?.*)?$`),
      async (route) => {
        await route.fulfill({
          json: {
            x_columns: MOCK_X_COLUMNS,
            y_indexes: MOCK_Y_INDEXES,
            y_labels: MOCK_Y_INDEXES.map((yIndex) => `第 ${yIndex} 行`),
            blurhash_cells: MOCK_Y_INDEXES.slice(0, 160).flatMap((yIndex) =>
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

    await page.route(
      new RegExp(`/api/comfyui/run/${MOCK_RUN_DIR}/row\\?.*$`),
      async (route) => {
        const requestUrl = new URL(route.request().url());
        const yIndex = Number(requestUrl.searchParams.get("y_index") ?? "0");
        await route.fulfill({
          json: buildRowPayload(Number.isFinite(yIndex) ? yIndex : 0),
        });
      },
    );

    const storageKey = `sd-style-lab:model-grid-anchor:${MOCK_RUN_DIR}`;
    await page.addInitScript(
      ({ key, value }) => {
        window.sessionStorage.setItem(key, value);
      },
      {
        key: storageKey,
        value: JSON.stringify({
          version: 1,
          yIndex: 10,
          rowOffsetRatio: 0,
        }),
      },
    );

    await page.goto(`/models/${MOCK_RUN_DIR}#${HASH_LINE_NUMBER}`);

    const grid = page.getByTestId("run-grid");
    const scrollEl = page.getByTestId("run-grid-scroll");

    await expect(grid).toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(`/models/${MOCK_RUN_DIR}#${HASH_LINE_NUMBER}$`),
    );
    await expect
      .poll(
        async () =>
          Number((await grid.getAttribute("data-row-height")) ?? "0"),
        { timeout: 10_000 },
      )
      .toBeGreaterThan(0);

    const rowHeight = Number((await grid.getAttribute("data-row-height")) ?? "0");
    expect(rowHeight).toBeGreaterThan(0);

    await expect
      .poll(async () => Math.round(await scrollEl.evaluate((el) => el.scrollTop)))
      .toBeGreaterThan(rowHeight * 110);

    const targetRow = page.locator(
      `[data-testid="run-grid-row"][data-row-index="${EXPECTED_Y_INDEX}"]`,
    );
    await expect(targetRow).toBeVisible();
    await expect(targetRow.getByTestId("run-grid-y-label")).toContainText(
      `第 ${EXPECTED_Y_INDEX} 行`,
    );
  });
});
