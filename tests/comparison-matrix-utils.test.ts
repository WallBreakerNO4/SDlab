import assert from "node:assert/strict";
import test from "node:test";

import {
  buildComparisonBlurhashLookup,
  getComparisonBlurhash,
  getComparisonPlaceholderBlurhash,
  getVariantBoundValue,
  getHorizontalModelWindow,
  getShiftWheelDelta,
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
