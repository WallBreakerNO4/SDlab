import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPrivateObjectCacheUrl,
  decodeStyleComparisonCursor,
  encodeStyleComparisonCursor,
  buildStyleComparisonPlacements,
  isStyleComparisonResponse,
  isStyleComparisonDetailResponse,
  isStyleComparisonSliceResponse,
  normalizeStyleComparisonModelsRpcRows,
  normalizeStyleComparisonSliceResponse,
  normalizeStyleComparisonSliceRpcResult,
  ownsAllRequestedStyleKeys,
  parseStyleComparisonLimit,
  parseStyleComparisonSliceBody,
  readViewerVariantFromCookie,
  type StyleComparisonResponse,
} from "../lib/style-comparison";
import { normalizeRowPayload } from "../components/comfyui/virtual-grid-utils";
import { resolveComparisonRowState } from "../components/favorites/comparison-loader";
import { isValidRunDir } from "../lib/comfyui-types";

test("style comparison cursor round-trips the keyset tuple", () => {
  const cursor = {
    created_at: "2026-07-20T01:02:03.000Z",
    style_key: "a,b:12",
  };
  assert.deepEqual(
    decodeStyleComparisonCursor(encodeStyleComparisonCursor(cursor)),
    cursor,
  );
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
    parseStyleComparisonSliceBody({
      style_keys: ["collection:1"],
      run_dirs: ["run-1"],
    }),
    { style_keys: ["collection:1"], run_dirs: ["run-1"] },
  );
  assert.equal(
    parseStyleComparisonSliceBody({
      style_keys: Array.from({ length: 41 }, (_, i) => `a:${i}`),
      run_dirs: ["run"],
    }),
    null,
  );
  assert.equal(
    parseStyleComparisonSliceBody({
      style_keys: ["a:1"],
      run_dirs: Array.from({ length: 13 }, (_, i) => `run-${i}`),
    }),
    null,
  );
  assert.equal(
    parseStyleComparisonSliceBody({ style_keys: [], run_dirs: ["run"] }),
    null,
  );
});

test("slice run dirs use the canonical lowercase kebab-case key", () => {
  assert.equal(isValidRunDir("anima-base-1-0-artist-mixer"), true);
  assert.equal(isValidRunDir("Anima-base-1.0-Artist-Mixer"), false);
  assert.equal(isValidRunDir("chenkinnoob-xl-v0-5"), true);
});

test("slice RPC response is bounded to the requested styles and runs", () => {
  const request = {
    style_keys: ["collection:1", "collection:2"],
    run_dirs: ["run-2", "run-1"],
  } as const;
  const result = normalizeStyleComparisonSliceRpcResult(
    {
      owned_style_keys: ["collection:2", "collection:1"],
      placements: [
        { style_key: "collection:1", run_dir: "run-2", y_index: 0 },
        {
          style_key: "collection:1",
          run_dir: "run-1",
          y_index: 7,
          blurhashes: [
            [2, 1, "hash-2-1"],
            [0, 0, "hash-0-0"],
            [2, 0, "hash-2-0"],
          ],
        },
      ],
      runs: [
        {
          run_dir: "run-1",
          release_id: "release-1",
          media_access_version: 2,
        },
      ],
    },
    request,
  );

  assert.ok(result);
  assert.equal(ownsAllRequestedStyleKeys(result, request.style_keys), true);
  assert.deepEqual(
    buildStyleComparisonPlacements(request.style_keys, result.placements),
    {
      "collection:1": [
        {
          run_dir: "run-1",
          y_index: 7,
          blurhashes: [
            [0, 0, "hash-0-0"],
            [2, 0, "hash-2-0"],
            [2, 1, "hash-2-1"],
          ],
        },
        { run_dir: "run-2", y_index: 0, blurhashes: [] },
      ],
      "collection:2": [],
    },
  );

  assert.equal(
    normalizeStyleComparisonSliceRpcResult(
      {
        owned_style_keys: ["collection:1"],
        placements: [
          { style_key: "collection:1", run_dir: "not-requested", y_index: 0 },
        ],
        runs: [],
      },
      request,
    ),
    null,
  );
  assert.equal(
    normalizeStyleComparisonSliceRpcResult(
      {
        owned_style_keys: ["collection:1"],
        placements: [
          { style_key: "collection:1", run_dir: "run-1", y_index: -1 },
        ],
        runs: [],
      },
      request,
    ),
    null,
  );
});

test("slice response normalizer keeps BlurHash tuples and upgrades legacy placements", () => {
  const normalized = normalizeStyleComparisonSliceResponse({
    access: [],
    placements: {
      "collection:1": [
        {
          run_dir: "run-1",
          y_index: 3,
          blurhashes: [
            [1, 2, "hash-1-2"],
            [0, 0, "hash-0-0"],
          ],
        },
        { run_dir: "run-2", y_index: 4 },
      ],
    },
  });

  assert.deepEqual(normalized, {
    access: [],
    placements: {
      "collection:1": [
        {
          run_dir: "run-1",
          y_index: 3,
          blurhashes: [
            [0, 0, "hash-0-0"],
            [1, 2, "hash-1-2"],
          ],
        },
        { run_dir: "run-2", y_index: 4, blurhashes: [] },
      ],
    },
  });
  assert.equal(isStyleComparisonSliceResponse(normalized), true);
  assert.equal(
    normalizeStyleComparisonSliceResponse({
      access: [],
      placements: {
        "collection:1": [
          { run_dir: "run-1", y_index: 0, blurhashes: [[0, 0, ""]] },
        ],
      },
    }),
    null,
  );
});

test("slice response normalizer rejects oversized and duplicate response data", () => {
  const access = (runDir: string) => ({
    run_dir: runDir,
    release_id: `release-${runDir}`,
    viewer_variant: "auth_sfw" as const,
    grant: `grant-${runDir}`,
    expires_at: 1_800_000_000,
  });
  const placement = (runDir: string) => ({
    run_dir: runDir,
    y_index: 0,
    blurhashes: [],
  });

  assert.equal(
    normalizeStyleComparisonSliceResponse({
      access: Array.from({ length: 13 }, (_, index) => access(`run-${index}`)),
      placements: {},
    }),
    null,
  );
  assert.equal(
    normalizeStyleComparisonSliceResponse({
      access: [access("run-1"), access("run-1")],
      placements: {},
    }),
    null,
  );
  assert.equal(
    normalizeStyleComparisonSliceResponse({
      access: [],
      placements: Object.fromEntries(
        Array.from({ length: 41 }, (_, index) => [`collection:${index}`, []]),
      ),
    }),
    null,
  );
  assert.equal(
    normalizeStyleComparisonSliceResponse({
      access: [],
      placements: {
        "collection:1": Array.from({ length: 13 }, (_, index) =>
          placement(`run-${index}`),
        ),
      },
    }),
    null,
  );
  assert.equal(
    normalizeStyleComparisonSliceResponse({
      access: [],
      placements: {
        "collection:1": [placement("run-1"), placement("run-1")],
      },
    }),
    null,
  );
  assert.equal(
    normalizeStyleComparisonSliceResponse({
      access: [],
      placements: Object.fromEntries(
        Array.from({ length: 40 }, (_, styleIndex) => [
          `collection:${styleIndex}`,
          Array.from({ length: 12 }, (_, runIndex) =>
            placement(`run-${runIndex}`),
          ),
        ]),
      ),
    }) !== null,
    true,
  );
});

test("slice RPC ownership result distinguishes a missing favorite", () => {
  const request = {
    style_keys: ["collection:1", "collection:2"],
    run_dirs: ["run-1"],
  } as const;
  const result = normalizeStyleComparisonSliceRpcResult(
    {
      owned_style_keys: ["collection:1"],
      placements: [],
      runs: [],
    },
    request,
  );

  assert.ok(result);
  assert.equal(ownsAllRequestedStyleKeys(result, request.style_keys), false);
});

test("model catalog RPC rows are normalized and malformed payloads are rejected", () => {
  assert.deepEqual(
    normalizeStyleComparisonModelsRpcRows([
      {
        run_dir: "run-1",
        name: "Model",
        created_at: "2026-07-20T00:00:00Z",
        x_columns: [
          { type: "portrait", description: { zh: "头像", en: "Portrait" } },
        ],
      },
    ]),
    [
      {
        run_dir: "run-1",
        name: "Model",
        created_at: "2026-07-20T00:00:00Z",
        x_columns: [
          {
            x_index: 0,
            type: "portrait",
            description: { zh: "头像", en: "Portrait" },
          },
        ],
      },
    ],
  );
  assert.equal(
    normalizeStyleComparisonModelsRpcRows([
      { run_dir: "run-1", name: null, created_at: null, x_columns: [] },
    ]),
    null,
  );
});

test("directory response guard rejects malformed models and accepts valid response", () => {
  const valid: StyleComparisonResponse = {
    favorites: [
      {
        style_key: "collection:1",
        label: "One",
        created_at: "2026-07-20T00:00:00Z",
      },
    ],
    models: [
      {
        run_dir: "run-1",
        name: "Model",
        created_at: "2026-07-20T00:00:00Z",
        x_columns: [
          {
            x_index: 0,
            type: "portrait",
            description: { zh: "头像", en: "Portrait" },
          },
        ],
      },
    ],
    next_cursor: null,
  };
  assert.equal(isStyleComparisonResponse(valid), true);
  assert.equal(isStyleComparisonResponse({ ...valid, next_cursor: 1 }), false);
  assert.equal(
    isStyleComparisonResponse({
      ...valid,
      favorites: [{ style_key: "bad", label: "x", created_at: "" }],
    }),
    false,
  );
});

test("detail response guard accepts one favorite plus the cached model catalog", () => {
  assert.equal(
    isStyleComparisonDetailResponse({
      favorite: {
        style_key: "collection:1",
        label: "One",
        created_at: "2026-07-20T00:00:00Z",
      },
      models: [],
    }),
    true,
  );
});

test("viewer variant follows the NSFW cookie", () => {
  assert.equal(readViewerVariantFromCookie(null), "auth_sfw");
  assert.equal(
    readViewerVariantFromCookie("foo=bar; sdslab_show_nsfw=1"),
    "auth_nsfw",
  );
  assert.equal(readViewerVariantFromCookie("sdslab_show_nsfw=0"), "auth_sfw");
});

test("private object cache key excludes grant but keeps object key", () => {
  const url = buildPrivateObjectCacheUrl(
    "https://example.test/api/private-object?key=runs%2Frun-1%2Fthumb.webp&grant=secret",
  );
  assert.equal(
    url,
    "https://example.test/api/private-object?key=runs%2Frun-1%2Fthumb.webp",
  );
});

test("row payload preserves item blurhash and accepts old manifests without it", () => {
  const rawItem = {
    batch_index: 0,
    category: "normal",
    width: 512,
    height: 768,
    meta: {},
    thumb: {
      webp: {
        bucket: "private",
        cache_key: "thumb-cache",
        key: "runs/run-1/thumb_webp.webp",
      },
    },
    display: null,
  };
  const withBlurhash = normalizeRowPayload(
    {
      run_dir: "run-1",
      y_index: 0,
      cells: [
        {
          x_index: 0,
          y_index: 0,
          items: [{ ...rawItem, blurhash: "LEHV6nWB2yk8pyo0adR*.7kCMdnj" }],
        },
      ],
    },
    0,
  );
  const legacy = normalizeRowPayload(
    {
      run_dir: "run-1",
      y_index: 0,
      cells: [{ x_index: 0, y_index: 0, items: [rawItem] }],
    },
    0,
  );

  assert.equal(
    withBlurhash?.cells[0]?.items[0]?.blurhash,
    "LEHV6nWB2yk8pyo0adR*.7kCMdnj",
  );
  assert.equal(legacy?.cells[0]?.items[0]?.blurhash, null);
});

test("comparison row states distinguish loading, missing, ready and error", () => {
  const readyRow = normalizeRowPayload(
    { run_dir: "run-1", y_index: 0, cells: [] },
    0,
  );
  assert.ok(readyRow);

  assert.deepEqual(resolveComparisonRowState(false, undefined), {
    status: "missing",
  });
  assert.deepEqual(resolveComparisonRowState(false, { status: "loading" }), {
    status: "loading",
  });
  assert.deepEqual(resolveComparisonRowState(true, undefined), {
    status: "loading",
  });
  assert.deepEqual(
    resolveComparisonRowState(true, { status: "ready", row: readyRow }),
    { status: "ready", row: readyRow },
  );
  assert.deepEqual(resolveComparisonRowState(true, { status: "error" }), {
    status: "error",
  });
});
