import { expect, test, type Page } from "@playwright/test";

const MOCK_RUN_DIR = "mock-run-mixer-prompt-parts";
const MOCK_BLURHASH = "LEHV6nWB2yk8pyo0adR*.7kCMdnj";
const MOCK_Y_INDEXES = [0, 1, 2];
const MOCK_X_COLUMNS = [
  {
    type: "normal",
    description: { zh: "构图示例" },
  },
];

const Y_PROMPT_PARTS = [
  {
    yIndex: 0,
    artist: "1.1::@artist-a, @artist-b",
    commonPrompt: "no lineart, watercolor wash,",
  },
  {
    yIndex: 1,
    artist: "@artist-only",
    commonPrompt: null,
  },
  {
    yIndex: 2,
    artist: null,
    commonPrompt: "year 2025, cinematic lighting,",
  },
];

function buildBootstrap() {
  return {
    run: {
      run_id: "mock-run-id",
      created_at: "2026-07-17T00:00:00.000Z",
      run_dir: MOCK_RUN_DIR,
      selection: { total_cells: MOCK_Y_INDEXES.length },
      model: {
        name: "Mock Anima Artist Mixer",
        description: { zh: "Mixer 首列拆分测试。" },
      },
      workflow: null,
    },
    xLabels: ["构图示例"],
    yLabels: [
      "@artist-a, @artist-b, no lineart, watercolor wash,",
      "@artist-only,",
      "year 2025, cinematic lighting,",
    ],
    yPromptParts: Y_PROMPT_PARTS,
    x_columns: MOCK_X_COLUMNS,
    y_indexes: MOCK_Y_INDEXES,
    prompts: [],
    blurhash_cells: MOCK_Y_INDEXES.map((yIndex) => ({
      x_index: 0,
      y_index: yIndex,
      batch_index: 0,
      category: "normal",
      width: 512,
      height: 768,
      blurhash: MOCK_BLURHASH,
    })),
  };
}

function buildRowPayload(yIndex: number) {
  return {
    run_dir: MOCK_RUN_DIR,
    y_index: yIndex,
    cells: [
      {
        x_index: 0,
        y_index: yIndex,
        items: [
          {
            batch_index: 0,
            category: "normal",
            width: 512,
            height: 768,
            meta: {
              seed: String(30_000 + yIndex),
              prompt_id: null,
              prompt_hash: `prompt-hash-${yIndex}`,
              positive_prompt: `mock prompt ${yIndex}`,
              y_value: buildBootstrap().yLabels[yIndex],
            },
            thumb: null,
            display: null,
          },
        ],
      },
    ],
  };
}

async function installMockRoutes(page: Page) {
  const bootstrap = buildBootstrap();
  await page.route(
    new RegExp(`/runs/${MOCK_RUN_DIR}/view/current\\.json(\\?.*)?$`),
    async (route) => {
      await route.fulfill({
        json: {
          schema_version: 2,
          run_dir: MOCK_RUN_DIR,
          release_id: "mixer-release",
          bootstrap_sfw_key: `runs/${MOCK_RUN_DIR}/view/v2/mixer-release/bootstrap.sfw.json`,
          public_row_prefix: `runs/${MOCK_RUN_DIR}/view/v2/mixer-release/rows/public/`,
        },
      });
    },
  );
  await page.route(
    new RegExp(
      `/runs/${MOCK_RUN_DIR}/view/v2/mixer-release/bootstrap\\.sfw\\.json(\\?.*)?$`,
    ),
    async (route) => {
      await route.fulfill({ json: bootstrap });
    },
  );
  await page.route(
    new RegExp(
      `/runs/${MOCK_RUN_DIR}/view/v2/mixer-release/rows/public/\\d+\\.json(\\?.*)?$`,
    ),
    async (route) => {
      const match = route
        .request()
        .url()
        .match(/\/public\/(\d+)\.json/);
      await route.fulfill({
        json: buildRowPayload(match ? Number(match[1]) : 0),
      });
    },
  );
}

test.describe("task 13: Mixer prompt parts", () => {
  test("renders, copies, and searches Artist/Common Prompt independently", async ({
    page,
    context,
  }, testInfo) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await installMockRoutes(page);
    await page.goto(`/models/${MOCK_RUN_DIR}`);

    const bothRow = page.locator(
      '[data-testid="run-grid-row"][data-row-index="0"]',
    );
    const artistOnlyRow = page.locator(
      '[data-testid="run-grid-row"][data-row-index="1"]',
    );
    const commonOnlyRow = page.locator(
      '[data-testid="run-grid-row"][data-row-index="2"]',
    );

    await expect(page.getByTestId("run-grid")).toBeVisible();
    await expect(bothRow.getByTestId("run-grid-artist-prompt")).toContainText(
      "artist-a",
    );
    await expect(bothRow.getByTestId("run-grid-common-prompt")).toContainText(
      "watercolor wash",
    );
    await expect(
      artistOnlyRow.getByTestId("run-grid-common-prompt"),
    ).toHaveCount(0);
    await expect(
      commonOnlyRow.getByTestId("run-grid-artist-prompt"),
    ).toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath("mixer-prompt-parts-desktop.png"),
      fullPage: false,
    });

    await bothRow.getByTestId("run-grid-copy-artist").click();
    await expect
      .poll(() => page.evaluate(() => navigator.clipboard.readText()))
      .toBe("1.1::@artist-a, @artist-b");

    await bothRow.getByTestId("run-grid-copy-common").click();
    await expect
      .poll(() => page.evaluate(() => navigator.clipboard.readText()))
      .toBe("no lineart, watercolor wash,");

    await page.getByLabel(/Open Grid Tools|打开网格工具/).click();
    await page
      .getByPlaceholder(
        /Search Artist or Common Prompt|搜索 Artist 或 Common Prompt/,
      )
      .fill("cinematic lighting");
    await expect(page.getByText("0/1", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: /Next Match|下一个匹配/ }).click();
    await expect(page.getByText("1/1", { exact: true })).toBeVisible();
    await expect(
      commonOnlyRow.getByTestId("run-grid-common-prompt").locator("mark"),
    ).toHaveText("cinematic lighting");

    await page
      .getByRole("button", { name: /Collapse Tool Panel|收起工具面板/ })
      .click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByTestId("run-grid-scroll").evaluate((element) => {
      element.scrollTop = 0;
    });
    await expect(bothRow).toBeVisible();

    const artistBox = await bothRow
      .getByTestId("run-grid-artist-prompt")
      .boundingBox();
    const commonBox = await bothRow
      .getByTestId("run-grid-common-prompt")
      .boundingBox();
    expect(artistBox).not.toBeNull();
    expect(commonBox).not.toBeNull();
    expect(artistBox!.y + artistBox!.height).toBeLessThanOrEqual(
      commonBox!.y + 1,
    );
    await page.screenshot({
      path: testInfo.outputPath("mixer-prompt-parts-mobile.png"),
      fullPage: false,
    });
  });
});
