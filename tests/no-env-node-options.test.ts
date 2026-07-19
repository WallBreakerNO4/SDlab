import assert from "node:assert/strict";
import test from "node:test";

import { mergeNodeRequireOption } from "../e2e/no-env-node-options";

const blockerPath = "/workspace with spaces/e2e/block-env-file-access.cjs";

test("mergeNodeRequireOption 保留既有选项并安全追加绝对 preload 路径", () => {
  const merged = mergeNodeRequireOption("--trace-warnings", blockerPath);

  assert.equal(
    merged,
    '--trace-warnings --require="/workspace with spaces/e2e/block-env-file-access.cjs"',
  );
});

test("mergeNodeRequireOption 不重复追加同一个 preload 路径", () => {
  const existing =
    '--trace-warnings --require="/workspace with spaces/e2e/block-env-file-access.cjs"';

  assert.equal(mergeNodeRequireOption(existing, blockerPath), existing);
});

test("mergeNodeRequireOption 识别空格分隔的既有 require 形式", () => {
  const existing =
    '--trace-warnings --require "/workspace with spaces/e2e/block-env-file-access.cjs"';

  assert.equal(mergeNodeRequireOption(existing, blockerPath), existing);
});
