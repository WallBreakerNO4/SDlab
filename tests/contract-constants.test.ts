import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { isValidRunDir, RUN_DIR_REGEX } from "../lib/comfyui-types";
import {
  isStyleFavoriteRunRef,
  isStyleItem,
  isStyleKey,
  LABEL_MAX_LENGTH,
  STYLE_KEY_MAX_LENGTH,
} from "../lib/style-favorites";
import {
  STYLE_COMPARISON_MAX_RUN_DIRS,
  STYLE_COMPARISON_MAX_STYLE_KEYS,
} from "../lib/style-comparison";

/**
 * 跨语言契约常量一致性守卫（TypeScript 侧）。
 *
 * run key / style_key 的镜像实现分散在 Python、TypeScript、SQL 三侧，y_index
 * 与上限常量也没有任何跨侧检查。本文件与 tests/test_contract_constants.py
 * 共享 tests/fixtures/contract-constants.json 的行为样本，任一处漂移都会在
 * pnpm test 或 pytest 中失败。
 */

const repoRoot = process.cwd();

interface ContractCases {
  valid: string[];
  invalid: string[];
}

const contractCases = JSON.parse(
  readFileSync(
    join(repoRoot, "tests", "fixtures", "contract-constants.json"),
    "utf8",
  ),
) as { runKey: ContractCases; styleKey: ContractCases };

const migrationSources = (() => {
  const directory = join(repoRoot, "supabase", "migrations");
  return readdirSync(directory)
    .filter((name) => name.endsWith(".sql"))
    .sort()
    .map((name) => readFileSync(join(directory, name), "utf8"));
})();

const runDirSqlPatterns = collectMatches(
  migrationSources,
  /run_dir\s*!~\s*'([^']+)'/g,
);

const styleKeySqlPatterns = collectMatches(
  migrationSources,
  /style_key\s*!~\s*'([^']+)'/g,
);

function readRepoFile(relativePath: string): string {
  return readFileSync(join(repoRoot, relativePath), "utf8");
}

/**
 * 只归一三端语义等价的方言写法（`(?:…)` 与 `\d`）；其余差异必须显式暴露，
 * 由人工裁决后同步所有副本。
 */
function canonicalizePattern(pattern: string): string {
  return pattern.replaceAll("(?:", "(").replaceAll("\\d", "[0-9]");
}

/** 从 TS 源码提取正则字面量，同时记录 flags 以确认没有状态化写法。 */
function extractTsRegex(
  source: string,
  constant: string,
): { source: string; flags: string } {
  const match = source.match(new RegExp(`${constant}\\s*=\\s*/([^/]+)/([a-z]*)`));
  assert.ok(match, `正则常量 ${constant} 必须保留字面量声明`);
  return { source: match[1], flags: match[2] };
}

function extractPythonRunKeyPattern(): string {
  const source = readRepoFile(join("scripts", "run_naming.py"));
  const match = source.match(/RUN_KEY_RE[^=\n]*=\s*re\.compile\(r"([^"]+)"\)/);
  assert.ok(match, "RUN_KEY_RE 必须保留 re.compile(r\"…\") 字面量");
  return match[1];
}

function collectMatches(sources: string[], pattern: RegExp): string[] {
  const matches: string[] = [];
  for (const source of sources) {
    for (const match of source.matchAll(pattern)) {
      matches.push(match[1]);
    }
  }
  return matches;
}

/**
 * 取出命名约束的 check 体，取迁移排序中最后一次声明（等价于数据库按序应用后的现行约束）。
 * `char_length(btrim(style_key))` 这类嵌套括号需要按平衡括号截取，不能用非贪婪正则。
 */
function extractConstraintCheckBody(constraint: string): string {
  const source = migrationSources.join("\n");
  const declarations = [
    ...source.matchAll(
      new RegExp(`constraint\\s+${constraint}\\b[\\s\\S]*?check\\s*\\(`, "g"),
    ),
  ];
  const declaration = declarations.at(-1);
  assert.ok(declaration, `必须存在约束 ${constraint}`);

  const open = declaration.index + declaration[0].length - 1;
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    const char = source[index];
    if (char === "(") depth += 1;
    else if (char === ")") {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, index);
    }
  }
  assert.fail(`约束 ${constraint} 的 check 体不完整`);
}

/**
 * SQL 迁移使用 POSIX 正则。当前契约只用到三端语法一致的最小子集；出现
 * JS 平移无法覆盖的语法（含 POSIX 字符类 `[[:alpha:]]`）时直接失败，
 * 逼迫人工确认语义后再扩展本函数。
 */
function compilePosixPattern(pattern: string): RegExp {
  assert.doesNotMatch(
    pattern,
    /\\|\?|\{|\||\[\[:/,
    `POSIX 正则包含 JS 平移未覆盖的语法: ${pattern}`,
  );
  return new RegExp(pattern);
}

/** 共享样本必须在两侧保持相同分类；SQL 侧逐个模式参与验证。 */
function assertCorpusClassification(
  cases: ContractCases,
  label: string,
  tsAccepts: (value: string) => boolean,
  sqlRegexes: RegExp[],
): void {
  for (const value of cases.valid) {
    assert.equal(tsAccepts(value), true, `valid ${label}: ${value}`);
    for (const regex of sqlRegexes) {
      assert.ok(regex.test(value), `SQL accepts ${label}: ${value}`);
    }
  }
  for (const value of cases.invalid) {
    assert.equal(tsAccepts(value), false, `invalid ${label}: ${value}`);
    for (const regex of sqlRegexes) {
      assert.ok(!regex.test(value), `SQL rejects ${label}: ${value}`);
    }
  }
}

test("run key mirrors across Python, TypeScript and SQL stay textually aligned", () => {
  const tsRegex = extractTsRegex(
    readRepoFile(join("lib", "comfyui-types.ts")),
    "RUN_DIR_REGEX",
  );

  assert.ok(runDirSqlPatterns.length > 0, "SQL 中必须存在 run_dir 形态校验");
  assert.equal(tsRegex.flags, "", "RUN_DIR_REGEX 不能带状态化 flags");
  assert.equal(RUN_DIR_REGEX.source, tsRegex.source);

  const expected = canonicalizePattern(tsRegex.source);
  assert.equal(canonicalizePattern(extractPythonRunKeyPattern()), expected);
  for (const pattern of runDirSqlPatterns) {
    assert.equal(canonicalizePattern(pattern), expected, pattern);
  }
});

test("run key corpus is classified identically by the TypeScript guard and SQL patterns", () => {
  assertCorpusClassification(
    contractCases.runKey,
    "run key",
    isValidRunDir,
    runDirSqlPatterns.map(compilePosixPattern),
  );
});

test("style_key mirrors across TypeScript and SQL stay textually aligned", () => {
  const tsRegex = extractTsRegex(
    readRepoFile(join("lib", "style-favorites.ts")),
    "STYLE_KEY_REGEX",
  );

  assert.ok(styleKeySqlPatterns.length > 0, "SQL 中必须存在 style_key 形态校验");
  assert.equal(tsRegex.flags, "", "STYLE_KEY_REGEX 不能带状态化 flags");

  const expected = canonicalizePattern(tsRegex.source);
  for (const pattern of styleKeySqlPatterns) {
    assert.equal(canonicalizePattern(pattern), expected, pattern);
  }
});

test("style_key corpus and length bound are shared by the TypeScript guard and SQL checks", () => {
  assertCorpusClassification(
    contractCases.styleKey,
    "style key",
    isStyleKey,
    styleKeySqlPatterns.map(compilePosixPattern),
  );

  const atLimit = `${"k".repeat(STYLE_KEY_MAX_LENGTH - 4)}:100`;
  const overLimit = `${"k".repeat(STYLE_KEY_MAX_LENGTH - 3)}:100`;
  assert.equal(atLimit.length, STYLE_KEY_MAX_LENGTH);
  assert.equal(overLimit.length, STYLE_KEY_MAX_LENGTH + 1);
  assert.equal(isStyleKey(atLimit), true);
  assert.equal(isStyleKey(overLimit), false);

  // 只钉现行收藏相关约束；20260526 迁移已删除的旧表（512/4000）不属于现行契约。
  const styleKeyBodies = [
    extractConstraintCheckBody("user_style_favorites_style_key_check"),
    extractConstraintCheckBody("run_style_items_style_key_check"),
  ];
  for (const body of styleKeyBodies) {
    assert.match(body, /char_length\(btrim\(style_key\)\)\s*>\s*0/);
    assert.match(
      body,
      new RegExp(
        `char_length\\(style_key\\)\\s*<=\\s*${STYLE_KEY_MAX_LENGTH}\\b`,
      ),
    );
  }

  const rejectBounds = collectMatches(
    migrationSources,
    /char_length\(style_key\)\s*>\s*(\d+)/g,
  );
  assert.deepEqual(
    new Set(rejectBounds),
    new Set([String(STYLE_KEY_MAX_LENGTH)]),
  );
});

test("style favorite label bound mirrors the SQL CHECK", () => {
  const labelBodies = [
    extractConstraintCheckBody("user_style_favorites_label_check"),
    extractConstraintCheckBody("run_style_items_label_check"),
  ];
  for (const body of labelBodies) {
    assert.match(body, /char_length\(btrim\(label\)\)\s*>\s*0/);
    assert.match(
      body,
      new RegExp(`char_length\\(label\\)\\s*<=\\s*${LABEL_MAX_LENGTH}\\b`),
    );
  }
});

test("comparison slice caps mirror the SQL RPC bounds", () => {
  const styleKeyCaps = collectMatches(
    migrationSources,
    /cardinality\(p_style_keys\)[\s\S]*?between 1 and (\d+)/g,
  );
  const runDirCaps = collectMatches(
    migrationSources,
    /cardinality\(p_run_dirs\)[\s\S]*?between 1 and (\d+)/g,
  );

  assert.deepEqual(
    new Set(styleKeyCaps),
    new Set([String(STYLE_COMPARISON_MAX_STYLE_KEYS)]),
  );
  assert.deepEqual(
    new Set(runDirCaps),
    new Set([String(STYLE_COMPARISON_MAX_RUN_DIRS)]),
  );
});

test("run_dir length bound in the slice parser mirrors the SQL RPC", () => {
  const sqlBounds = new Set(
    collectMatches(migrationSources, /char_length\(run_dir\)\s*>\s*(\d+)/g),
  );
  assert.equal(sqlBounds.size, 1, "SQL 中 run_dir 长度上限必须唯一");

  const parserMatch = readRepoFile(join("lib", "style-comparison.ts")).match(
    /runDir\.length\s*<=\s*(\d+)/,
  );
  assert.ok(parserMatch, "slice parser 必须保留 run_dir 长度上限");
  assert.equal(parserMatch[1], [...sqlBounds][0]);
});

test("y_index stays a 0-based contract on both sides", () => {
  const yIndexBody = extractConstraintCheckBody(
    "run_style_items_y_index_check",
  );
  assert.match(yIndexBody, /y_index\s*>=\s*0/);

  assert.equal(isStyleItem({ y_index: 0, style_key: "collection:1" }), true);
  assert.equal(isStyleItem({ y_index: -1, style_key: "collection:1" }), false);
  assert.equal(
    isStyleFavoriteRunRef({ run_dir: "run-1", name: null, y_index: 0 }),
    true,
  );
  assert.equal(
    isStyleFavoriteRunRef({ run_dir: "run-1", name: null, y_index: -1 }),
    false,
  );
});
