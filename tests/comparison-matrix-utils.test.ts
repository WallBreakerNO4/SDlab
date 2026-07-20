import assert from "node:assert/strict";
import test from "node:test";

import {
  getHorizontalModelWindow,
  getShiftWheelDelta,
} from "../components/favorites/comparison-matrix-utils";

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
