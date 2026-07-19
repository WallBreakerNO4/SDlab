import assert from "node:assert/strict";
import test from "node:test";

import { isEnvFilePath } from "../e2e/env-file-path.cjs";

test("isEnvFilePath 识别字符串形式的环境文件路径", () => {
  assert.equal(isEnvFilePath("/virtual/project/.env.local"), true);
  assert.equal(isEnvFilePath("/virtual/project/environment.json"), false);
});

test("isEnvFilePath 识别 Buffer 形式的环境文件路径", () => {
  assert.equal(isEnvFilePath(Buffer.from("/virtual/project/.env.test")), true);
  assert.equal(isEnvFilePath(Buffer.from("/virtual/project/settings.json")), false);
});

test("isEnvFilePath 识别 WHATWG file URL 形式的环境文件路径", () => {
  assert.equal(isEnvFilePath(new URL("file:///virtual/project/.env.production")), true);
  assert.equal(isEnvFilePath(new URL("file:///virtual/project/config.json")), false);
});

test("isEnvFilePath 不把非 file URL 识别为本地环境文件", () => {
  assert.equal(isEnvFilePath(new URL("https://example.com/.env")), false);
});
