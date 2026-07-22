import type { Page } from "@playwright/test";

export const MOCK_MODEL_VIEW_RUN_DIR = "mock-run-model-view";
export const MOCK_MODEL_VIEW_RELEASE_ID = "mock-model-view-release";
export const MOCK_MODEL_VIEW_BLURHASH = "LEHV6nWB2yk8pyo0adR*.7kCMdnj";

export const PUBLIC_ROW_URL_PATTERN =
  /\/rows\/public\/(\d+)\.json(?:\?.*)?$/;
export const DISPLAY_VARIANT_URL_PATTERN =
  /\/(?:display_webp\.webp|display_avif\.avif)(?:\?.*)?$/;
export const THUMB_VARIANT_URL_PATTERN =
  /\/(?:thumb_webp\.webp|thumb_avif\.avif)(?:\?.*)?$/;

export function getFirstModelLink(page: Page) {
  return page.locator('main a[href*="/models/"]').first();
}

type InstallModelViewMockOptions = {
  runDir?: string;
  rowCount?: number;
  thumbDelayMs?: number;
  beforeDisplayFulfill?: () => Promise<void>;
};

const MOCK_IMAGE_BODY = [
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="24"',
  ' viewBox="0 0 16 24"><rect width="16" height="24" fill="#7c8799"/></svg>',
].join("");

function buildBootstrap(runDir: string, rowCount: number) {
  const xColumns = Array.from({ length: 2 }, (_, index) => ({
    type: "normal",
    description: { zh: `列 ${index + 1}`, en: `Column ${index + 1}` },
  }));
  const yIndexes = Array.from({ length: rowCount }, (_, index) => index);

  return {
    run: {
      run_id: "mock-model-view-run-id",
      created_at: "2026-07-19T00:00:00.000Z",
      run_dir: runDir,
      selection: { total_cells: xColumns.length * yIndexes.length },
      model: {
        name: "Mock Model View Run",
        description: {
          zh: "用于详情页 E2E 的确定性数据。",
          en: "Deterministic model detail E2E data.",
        },
      },
      workflow: null,
    },
    xLabels: xColumns.map((column) => column.description.zh),
    yLabels: yIndexes.map((yIndex) => `第 ${yIndex} 行`),
    x_columns: xColumns,
    y_indexes: yIndexes,
    y_labels: yIndexes.map((yIndex) => `第 ${yIndex} 行`),
    prompts: [],
    blurhash_cells: yIndexes.flatMap((yIndex) =>
      xColumns.map((_, xIndex) => ({
        x_index: xIndex,
        y_index: yIndex,
        batch_index: 0,
        category: "normal",
        width: 512,
        height: 768,
        blurhash: MOCK_MODEL_VIEW_BLURHASH,
      })),
    ),
  };
}

function buildRowPayload(runDir: string, yIndex: number) {
  return {
    run_dir: runDir,
    y_index: yIndex,
    cells: Array.from({ length: 2 }, (_, xIndex) => ({
      x_index: xIndex,
      y_index: yIndex,
      items: [
        {
          batch_index: 0,
          category: "normal",
          width: 512,
          height: 768,
          blurhash: MOCK_MODEL_VIEW_BLURHASH,
          meta: {
            seed: String(30_000 + yIndex),
            prompt_hash: `model-view-prompt-${xIndex}-${yIndex}`,
            positive_prompt: `mock prompt ${xIndex}-${yIndex}`,
            y_value: `第 ${yIndex} 行`,
          },
          thumb: {
            webp: {
              bucket: "public",
              cache_key: `thumb-${xIndex}-${yIndex}`,
              key: `runs/${runDir}/media/${xIndex}-${yIndex}/thumb_webp.webp`,
            },
          },
          display: {
            webp: {
              bucket: "public",
              cache_key: `display-${xIndex}-${yIndex}`,
              key: `runs/${runDir}/media/${xIndex}-${yIndex}/display_webp.webp`,
            },
          },
        },
      ],
    })),
  };
}

export async function installModelViewMock(
  page: Page,
  {
    runDir = MOCK_MODEL_VIEW_RUN_DIR,
    rowCount = 80,
    thumbDelayMs = 0,
    beforeDisplayFulfill,
  }: InstallModelViewMockOptions = {},
) {
  const bootstrap = buildBootstrap(runDir, rowCount);
  const releaseBase = `runs/${runDir}/view/v2/${MOCK_MODEL_VIEW_RELEASE_ID}`;

  await page.route(
    new RegExp(`/runs/${runDir}/view/current\\.json(\\?.*)?$`),
    async (route) => {
      await route.fulfill({
        json: {
          schema_version: 2,
          run_dir: runDir,
          release_id: MOCK_MODEL_VIEW_RELEASE_ID,
          bootstrap_sfw_key: `${releaseBase}/bootstrap.sfw.json`,
          public_row_prefix: `${releaseBase}/rows/public/`,
        },
      });
    },
  );

  await page.route(
    new RegExp(`/${releaseBase}/bootstrap\\.sfw\\.json(\\?.*)?$`),
    async (route) => {
      await route.fulfill({ json: bootstrap });
    },
  );

  await page.route(
    new RegExp(`/${releaseBase}/rows/public/\\d+\\.json(\\?.*)?$`),
    async (route) => {
      const match = route.request().url().match(PUBLIC_ROW_URL_PATTERN);
      const yIndex = match ? Number(match[1]) : 0;
      await route.fulfill({
        json: buildRowPayload(runDir, Number.isFinite(yIndex) ? yIndex : 0),
      });
    },
  );

  await page.route(
    new RegExp(`/runs/${runDir}/media/.*_webp\\.webp(\\?.*)?$`),
    async (route) => {
      const isDisplay = DISPLAY_VARIANT_URL_PATTERN.test(route.request().url());
      if (isDisplay && beforeDisplayFulfill) {
        await beforeDisplayFulfill();
      } else if (!isDisplay && thumbDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, thumbDelayMs));
      }
      await route.fulfill({
        status: 200,
        contentType: "image/svg+xml",
        body: MOCK_IMAGE_BODY,
      });
    },
  );

  await page.route(`**/api/comfyui/run/${runDir}/style-items`, async (route) => {
    await route.fulfill({ json: [] });
  });
}
