import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  buildComparisonBlurhashLookup,
  buildVisibleComparisonXColumns,
  getComparisonBlurhash,
  getComparisonPlaceholderBlurhash,
  getComparisonSyncModePersistenceValue,
  getComparisonSyncModeToggleValue,
  getSceneColumnDescription,
  getVariantBoundValue,
  getHorizontalModelWindow,
  getShiftWheelDelta,
  isComparisonSyncMode,
  resolveComparisonSyncMode,
  wrapSlideIndex,
} from "../components/favorites/comparison-matrix-utils";

const RUN_DIR = "model-a";

test("slice blurhash lookup resolves exact x and batch in O(1) keys", () => {
  const lookup = buildComparisonBlurhashLookup({
    "collection:1": [
      {
        run_dir: RUN_DIR,
        y_index: 7,
        blurhashes: [
          [0, 0, "hash-x0-b0"],
          [0, 1, "hash-x0-b1"],
          [1, 0, "hash-x1-b0"],
        ],
      },
    ],
  });

  assert.equal(
    getComparisonBlurhash(lookup, RUN_DIR, 7, 0, 1, null),
    "hash-x0-b1",
  );
  assert.equal(getComparisonBlurhash(lookup, RUN_DIR, 7, 2, 0, null), null);
});

test("row manifest blurhash takes precedence over the slice fallback", () => {
  const lookup = buildComparisonBlurhashLookup({
    "collection:1": [
      {
        run_dir: RUN_DIR,
        y_index: 7,
        blurhashes: [[0, 0, "slice-hash"]],
      },
    ],
  });

  assert.equal(
    getComparisonBlurhash(lookup, RUN_DIR, 7, 0, 0, "row-hash"),
    "row-hash",
  );
});

test("slice lookup exposes the first placement and first x-column placeholders", () => {
  const lookup = buildComparisonBlurhashLookup({
    "collection:1": [
      {
        run_dir: RUN_DIR,
        y_index: 7,
        blurhashes: [
          [0, 2, "hash-x0-b2"],
          [1, 0, "hash-x1-b0"],
          [1, 3, "hash-x1-b3"],
        ],
      },
    ],
  });

  assert.equal(
    getComparisonPlaceholderBlurhash(lookup, RUN_DIR, 7),
    "hash-x0-b2",
  );
  assert.equal(
    getComparisonPlaceholderBlurhash(lookup, RUN_DIR, 7, 1),
    "hash-x1-b0",
  );
  assert.equal(
    getComparisonPlaceholderBlurhash(lookup, RUN_DIR, 7, 2),
    null,
  );
});

test("duplicate placements do not replace the first stable slice blurhash", () => {
  const lookup = buildComparisonBlurhashLookup({
    "collection:1": [
      {
        run_dir: RUN_DIR,
        y_index: 7,
        blurhashes: [[0, 0, "first-hash"]],
      },
    ],
    "collection:2": [
      {
        run_dir: RUN_DIR,
        y_index: 7,
        blurhashes: [[0, 0, "duplicate-hash"]],
      },
    ],
  });

  assert.equal(
    getComparisonBlurhash(lookup, RUN_DIR, 7, 0, 0, null),
    "first-hash",
  );
});

test("variant-bound slice values never expose stale NSFW blurhash data", () => {
  const snapshot = { variantKey: "nsfw", data: "nsfw-slice" };

  assert.equal(getVariantBoundValue(snapshot, "nsfw"), "nsfw-slice");
  assert.equal(getVariantBoundValue(snapshot, "sfw"), null);
  assert.equal(getVariantBoundValue(null, "sfw"), null);
});

test("horizontal model window includes only visible columns plus one overscan column", () => {
  assert.deepEqual(
    getHorizontalModelWindow({
      scrollLeft: 0,
      viewportWidth: 1280,
      promptColumnWidth: 280,
      modelColumnWidth: 216,
      modelCount: 50,
      overscan: 1,
    }),
    { startIndex: 0, endIndex: 6 },
  );
});

test("horizontal model window follows scroll position without exceeding model count", () => {
  assert.deepEqual(
    getHorizontalModelWindow({
      scrollLeft: 432,
      viewportWidth: 1280,
      promptColumnWidth: 280,
      modelColumnWidth: 216,
      modelCount: 7,
      overscan: 1,
    }),
    { startIndex: 1, endIndex: 7 },
  );
});

test("horizontal model window keeps every visible column on an ultra-wide viewport", () => {
  assert.deepEqual(
    getHorizontalModelWindow({
      scrollLeft: 0,
      viewportWidth: 3840,
      promptColumnWidth: 280,
      modelColumnWidth: 216,
      modelCount: 50,
      overscan: 1,
    }),
    { startIndex: 0, endIndex: 18 },
  );
});

test("horizontal model window returns an empty range when there are no models", () => {
  assert.deepEqual(
    getHorizontalModelWindow({
      scrollLeft: 0,
      viewportWidth: 1280,
      promptColumnWidth: 280,
      modelColumnWidth: 216,
      modelCount: 0,
      overscan: 1,
    }),
    { startIndex: 0, endIndex: 0 },
  );
});

test("shift plus a vertical wheel gesture becomes horizontal scroll", () => {
  assert.equal(
    getShiftWheelDelta({ shiftKey: true, deltaX: 0, deltaY: 120 }),
    120,
  );
});

test("plain wheel and native horizontal gestures are left to the browser", () => {
  assert.equal(
    getShiftWheelDelta({ shiftKey: false, deltaX: 0, deltaY: 120 }),
    null,
  );
  assert.equal(
    getShiftWheelDelta({ shiftKey: true, deltaX: 80, deltaY: 20 }),
    null,
  );
});

test("comparison sync mode guard accepts only the three known modes", () => {
  assert.equal(isComparisonSyncMode("cell"), true);
  assert.equal(isComparisonSyncMode("column"), true);
  assert.equal(isComparisonSyncMode("all"), true);
  assert.equal(isComparisonSyncMode("row"), false);
  assert.equal(isComparisonSyncMode(null), false);
});

test("comparison sync mode defaults to all while preserving valid saved modes", () => {
  assert.equal(resolveComparisonSyncMode(null), "all");
  assert.equal(resolveComparisonSyncMode("row"), "all");
  assert.equal(resolveComparisonSyncMode("cell"), "cell");
  assert.equal(resolveComparisonSyncMode("column"), "column");
  assert.equal(resolveComparisonSyncMode("all"), "all");
});

test("comparison sync mode persistence waits until the saved preference is hydrated", () => {
  assert.equal(getComparisonSyncModePersistenceValue("all", false), null);
  assert.equal(getComparisonSyncModePersistenceValue("cell", true), "cell");
  assert.equal(getComparisonSyncModePersistenceValue("column", true), "column");
  assert.equal(getComparisonSyncModePersistenceValue("all", true), "all");
});

test("comparison sync mode toggle hides its selection until hydration completes", () => {
  assert.equal(getComparisonSyncModeToggleValue("all", false), "");
  assert.equal(getComparisonSyncModeToggleValue("cell", true), "cell");
  assert.equal(getComparisonSyncModeToggleValue("column", true), "column");
  assert.equal(getComparisonSyncModeToggleValue("all", true), "all");
});

const COMPARISON_X_COLUMNS = [
  { x_index: 4, type: "portrait", description: { zh: "肖像" } },
  { x_index: 7, type: "nsfw", description: { zh: "NSFW 图片" } },
  { x_index: 11, type: "wide", description: { zh: "全身像" } },
] as const;

test("SFW comparison columns remove NSFW rows and compact x indexes", () => {
  assert.deepEqual(buildVisibleComparisonXColumns(COMPARISON_X_COLUMNS, false), [
    { x_index: 0, type: "portrait", description: { zh: "肖像" } },
    { x_index: 1, type: "wide", description: { zh: "全身像" } },
  ]);
});

test("NSFW comparison columns preserve every row in positional order", () => {
  assert.deepEqual(buildVisibleComparisonXColumns(COMPARISON_X_COLUMNS, true), [
    { x_index: 0, type: "portrait", description: { zh: "肖像" } },
    { x_index: 1, type: "nsfw", description: { zh: "NSFW 图片" } },
    { x_index: 2, type: "wide", description: { zh: "全身像" } },
  ]);
});

test("favorite comparison image frames expose the 832 by 1216 portrait ratio", () => {
  const source = readFileSync(
    new URL(
      "../components/favorites/favorite-comparison-detail.tsx",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(
    source,
    /data-testid="favorite-comparison-image-frame"[\s\S]*?aspect-\[13\/19\]/,
  );
});

test("wrapSlideIndex cycles forward past the end and backward past the start", () => {
  assert.equal(wrapSlideIndex(0, 4), 0);
  assert.equal(wrapSlideIndex(3, 4), 3);
  assert.equal(wrapSlideIndex(4, 4), 0);
  assert.equal(wrapSlideIndex(9, 4), 1);
  assert.equal(wrapSlideIndex(-1, 4), 3);
  assert.equal(wrapSlideIndex(-5, 4), 3);
});

test("wrapSlideIndex collapses to 0 when there are no slides", () => {
  assert.equal(wrapSlideIndex(2, 0), 0);
  assert.equal(wrapSlideIndex(-1, 0), 0);
});

const SCENE_COLUMNS = [
  { x_index: 0, type: "close-up", description: { zh: "面部特写", en: null } },
  {
    x_index: 1,
    type: "half-body",
    description: { zh: "半身构图", en: "Half body" },
  },
] as const;

test("scene column description falls back to the first column without a synced scene", () => {
  assert.equal(getSceneColumnDescription(SCENE_COLUMNS, null, "zh"), "面部特写");
  assert.equal(getSceneColumnDescription(SCENE_COLUMNS, null, "en"), "面部特写");
});

test("scene column description resolves the synced scene with locale fallback", () => {
  assert.equal(getSceneColumnDescription(SCENE_COLUMNS, 1, "zh"), "半身构图");
  assert.equal(getSceneColumnDescription(SCENE_COLUMNS, 1, "en"), "Half body");
  assert.equal(getSceneColumnDescription(SCENE_COLUMNS, 0, "en"), "面部特写");
});

test("scene column description falls back to the column type when description is missing", () => {
  const columns = [{ x_index: 2, type: "wide", description: null }] as const;
  assert.equal(getSceneColumnDescription(columns, 2, "zh"), "wide");
  assert.equal(getSceneColumnDescription(columns, 9, "zh"), "wide");
});
