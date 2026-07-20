import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPrivateObjectCacheUrl,
  decodeStyleComparisonCursor,
  encodeStyleComparisonCursor,
  isStyleComparisonResponse,
  isStyleComparisonDetailResponse,
  parseStyleComparisonLimit,
  parseStyleComparisonSliceBody,
  readViewerVariantFromCookie,
  type StyleComparisonResponse,
} from "../lib/style-comparison";

test("style comparison cursor round-trips the keyset tuple", () => {
  const cursor = { created_at: "2026-07-20T01:02:03.000Z", style_key: "a,b:12" };
  assert.deepEqual(decodeStyleComparisonCursor(encodeStyleComparisonCursor(cursor)), cursor);
  assert.equal(decodeStyleComparisonCursor("invalid"), null);
});

test("style comparison limit defaults to 40 and caps at 40", () => {
  assert.equal(parseStyleComparisonLimit(null), 40);
  assert.equal(parseStyleComparisonLimit(""), 40);
  assert.equal(parseStyleComparisonLimit("40"), 40);
  assert.equal(parseStyleComparisonLimit("100"), 40);
  assert.equal(parseStyleComparisonLimit("0"), null);
  assert.equal(parseStyleComparisonLimit("abc"), null);
});

test("slice body enforces bounded style keys and run dirs", () => {
  assert.deepEqual(
    parseStyleComparisonSliceBody({ style_keys: ["collection:1"], run_dirs: ["run-1"] }),
    { style_keys: ["collection:1"], run_dirs: ["run-1"] },
  );
  assert.equal(
    parseStyleComparisonSliceBody({ style_keys: Array.from({ length: 41 }, (_, i) => `a:${i}`), run_dirs: ["run"] }),
    null,
  );
  assert.equal(
    parseStyleComparisonSliceBody({ style_keys: ["a:1"], run_dirs: Array.from({ length: 13 }, (_, i) => `run-${i}`) }),
    null,
  );
  assert.equal(parseStyleComparisonSliceBody({ style_keys: [], run_dirs: ["run"] }), null);
});

test("directory response guard rejects malformed models and accepts valid response", () => {
  const valid: StyleComparisonResponse = {
    favorites: [{ style_key: "collection:1", label: "One", created_at: "2026-07-20T00:00:00Z" }],
    models: [{
      run_dir: "run-1",
      name: "Model",
      created_at: "2026-07-20T00:00:00Z",
      x_columns: [{ x_index: 0, type: "portrait", description: { zh: "头像", en: "Portrait" } }],
    }],
    next_cursor: null,
  };
  assert.equal(isStyleComparisonResponse(valid), true);
  assert.equal(isStyleComparisonResponse({ ...valid, next_cursor: 1 }), false);
  assert.equal(isStyleComparisonResponse({ ...valid, favorites: [{ style_key: "bad", label: "x", created_at: "" }] }), false);
});

test("detail response guard accepts one favorite plus the cached model catalog", () => {
  assert.equal(
    isStyleComparisonDetailResponse({
      favorite: { style_key: "collection:1", label: "One", created_at: "2026-07-20T00:00:00Z" },
      models: [],
    }),
    true,
  );
});

test("viewer variant follows the NSFW cookie", () => {
  assert.equal(readViewerVariantFromCookie(null), "auth_sfw");
  assert.equal(readViewerVariantFromCookie("foo=bar; sdslab_show_nsfw=1"), "auth_nsfw");
  assert.equal(readViewerVariantFromCookie("sdslab_show_nsfw=0"), "auth_sfw");
});

test("private object cache key excludes grant but keeps object key", () => {
  const url = buildPrivateObjectCacheUrl("https://example.test/api/private-object?key=runs%2Frun-1%2Fthumb.webp&grant=secret");
  assert.equal(url, "https://example.test/api/private-object?key=runs%2Frun-1%2Fthumb.webp");
});
