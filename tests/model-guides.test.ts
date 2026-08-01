import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  buildGuideIndex,
  parseModelGuide,
  resolveGuideLocale,
  resolveGuidePath,
} from "../lib/model-guides";
import {
  buildModelGuideModule,
  collectModelGuides,
  collectModelKeys,
  renderModelGuideModule,
} from "../loaders/model-guide-data-builder";

test("parseModelGuide parses required frontmatter and defaults draft to false", () => {
  const guide = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Anima 使用指南\n---\n\n# 正文\n",
    "data/model-guides/anima.zh.md",
  );

  assert.deepEqual(guide, {
    modelKey: "anima-base-1",
    locale: "zh",
    title: "Anima 使用指南",
    draft: false,
    content: "# 正文\n",
    sourcePath: "data/model-guides/anima.zh.md",
  });
});

test("parseModelGuide accepts boolean draft values", () => {
  const draft = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Draft\ndraft: true\n---\nBody",
    "draft.md",
  );
  const published = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: en\ntitle: Published\ndraft: false\n---\nBody",
    "published.md",
  );

  assert.equal(draft.draft, true);
  assert.equal(published.draft, false);
});

test("parseModelGuide honors YAML quoting and punctuation", () => {
  const guide = parseModelGuide(
    '---\nmodel_key: anima-base-1\nlocale: en\ntitle: "How to use: Anima"\n---\nBody',
    "guide.md",
  );
  assert.equal(guide.title, "How to use: Anima");
});

test("parseModelGuide rejects missing, invalid, and unknown frontmatter fields", () => {
  assert.throws(
    () =>
      parseModelGuide(
        "---\nmodel_key: anima-base-1\nlocale: zh\n---\n正文",
        "guide.md",
      ),
    /title/,
  );
  assert.throws(
    () =>
      parseModelGuide(
        "---\nmodel_key: anima-base-1\nlocale: fr\ntitle: Test\n---\n正文",
        "guide.md",
      ),
    /locale/,
  );
  assert.throws(
    () =>
      parseModelGuide(
        "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Test\nauthor: Test\n---\n正文",
        "guide.md",
      ),
    /author|unknown/i,
  );
});

test("parseModelGuide rejects non-boolean draft values", () => {
  for (const draft of ['"true"', "1", "null"]) {
    assert.throws(
      () =>
        parseModelGuide(
          `---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Test\ndraft: ${draft}\n---\n正文`,
          "guide.md",
        ),
      /draft must be a boolean/i,
    );
  }
});

test("buildGuideIndex rejects duplicate model and locale entries", () => {
  const first = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: One\ndraft: true\n---\nOne",
    "one.md",
  );
  const second = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Two\n---\nTwo",
    "two.md",
  );

  assert.throws(() => buildGuideIndex([first, second]), /duplicate/i);
});

test("resolveGuideLocale prefers requested language and falls back", () => {
  const guides = buildGuideIndex([
    parseModelGuide(
      "---\nmodel_key: anima-base-1\nlocale: en\ntitle: English\n---\nEN",
      "en.md",
    ),
    parseModelGuide(
      "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: 中文\n---\nZH",
      "zh.md",
    ),
  ]);

  assert.equal(resolveGuideLocale(guides, "anima-base-1", "zh"), "zh");
  assert.equal(resolveGuideLocale(guides, "anima-base-1", "en"), "en");
  assert.equal(resolveGuideLocale(guides, "missing", "zh"), null);
});

test("resolveGuidePath falls back to the available language", () => {
  const guides = buildGuideIndex([
    parseModelGuide(
      "---\nmodel_key: anima-base-1\nlocale: en\ntitle: English\n---\nEN",
      "en.md",
    ),
  ]);
  assert.equal(
    resolveGuidePath(guides, "anima-base-1", "zh"),
    "/en/guides/anima-base-1",
  );
  assert.equal(resolveGuidePath(guides, "missing", "zh"), null);
});

test("collectModelGuides recursively scans and sorts by stable relative path", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "model-guides-"));
  fs.mkdirSync(path.join(root, "nested"));
  fs.writeFileSync(
    path.join(root, "nested", "z.md"),
    "---\nmodel_key: z\nlocale: zh\ntitle: Z\n---\nZ",
  );
  fs.writeFileSync(
    path.join(root, "a.md"),
    "---\nmodel_key: a\nlocale: en\ntitle: A\n---\nA",
  );

  const guides = collectModelGuides(root, new Set(["a", "z"]));
  assert.deepEqual(
    guides.map((guide) => path.relative(root, guide.sourcePath)),
    ["a.md", path.join("nested", "z.md")],
  );
});

test("collectModelGuides rejects an unknown model key", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "model-guides-"));
  fs.writeFileSync(
    path.join(root, "unknown.md"),
    "---\nmodel_key: missing-model\nlocale: zh\ntitle: Missing\ndraft: true\n---\nBody",
  );
  assert.throws(
    () => collectModelGuides(root, new Set(["known-model"])),
    /unknown model_key.*missing-model/i,
  );
});

test("collectModelKeys reads model.key from model config files", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "models-"));
  fs.mkdirSync(path.join(root, "one"));
  fs.mkdirSync(path.join(root, "two"));
  fs.writeFileSync(
    path.join(root, "one", "config.yaml"),
    "model:\n  key: first-model\n",
  );
  fs.writeFileSync(
    path.join(root, "two", "config.yaml"),
    "model:\n  key: second-model\n",
  );
  assert.deepEqual(
    [...collectModelKeys(root)],
    ["first-model", "second-model"],
  );
});

test("renderModelGuideModule is stable and server-only", () => {
  const guide = parseModelGuide(
    '---\nmodel_key: anima-base-1\nlocale: zh\ntitle: "A: Guide"\n---\nBody',
    "guide.md",
  );
  const publishedGuide = {
    modelKey: guide.modelKey,
    locale: guide.locale,
    title: guide.title,
    content: guide.content,
    sourcePath: guide.sourcePath,
  };
  assert.equal(
    renderModelGuideModule([guide]),
    `import "server-only";\nimport type { ModelGuide } from "../model-guides";\n\n// Generated by loaders/model-guide-data-builder.ts\nexport const modelGuides: readonly ModelGuide[] = ${JSON.stringify([publishedGuide])};\n`,
  );
});

test("renderModelGuideModule validates but omits draft guides", () => {
  const draft = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Draft\ndraft: true\n---\nDraft body",
    "draft.md",
  );
  const published = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: en\ntitle: Published\n---\nPublished body",
    "published.md",
  );

  const output = renderModelGuideModule([draft, published]);
  assert.doesNotMatch(output, /Draft body|"draft"/);
  assert.match(output, /Published body/);
});

test("renderModelGuideModule rejects duplicates before filtering drafts", () => {
  const draft = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Draft\ndraft: true\n---\nDraft",
    "draft.md",
  );
  const published = parseModelGuide(
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Published\n---\nPublished",
    "published.md",
  );

  assert.throws(() => renderModelGuideModule([draft, published]), /duplicate/i);
});

test("repository guide keeps the frontmatter title as the page heading source", () => {
  const sourcePath = path.join(
    process.cwd(),
    "data",
    "model-guides",
    "anima-base-1.zh.md",
  );
  const guide = parseModelGuide(
    fs.readFileSync(sourcePath, "utf8"),
    sourcePath,
  );

  assert.equal(guide.title, "模型使用指南（测试文章）");
  assert.equal(guide.draft, true);
  assert.doesNotMatch(guide.content, /^#\s+/m);
});

test("buildModelGuideModule writes repository-relative source paths", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "model-guide-repo-"));
  const modelsDir = path.join(root, "data", "models", "anima");
  const guidesDir = path.join(root, "data", "model-guides");
  fs.mkdirSync(modelsDir, { recursive: true });
  fs.mkdirSync(guidesDir, { recursive: true });
  fs.writeFileSync(
    path.join(modelsDir, "config.yaml"),
    "model:\n  key: anima-base-1\n",
  );
  fs.writeFileSync(
    path.join(guidesDir, "anima.zh.md"),
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Anima\n---\nBody",
  );

  const outputPath = buildModelGuideModule(root);
  const output = fs.readFileSync(outputPath, "utf8");
  assert.doesNotMatch(
    output,
    new RegExp(root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  );
  assert.match(output, /"sourcePath":"data\/model-guides\/anima\.zh\.md"/);
  assert.doesNotMatch(output, /"draft"/);
});

test("buildModelGuideModule emits an empty index when every guide is a draft", () => {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), "model-guide-draft-repo-"),
  );
  const modelsDir = path.join(root, "data", "models", "anima");
  const guidesDir = path.join(root, "data", "model-guides");
  fs.mkdirSync(modelsDir, { recursive: true });
  fs.mkdirSync(guidesDir, { recursive: true });
  fs.writeFileSync(
    path.join(modelsDir, "config.yaml"),
    "model:\n  key: anima-base-1\n",
  );
  fs.writeFileSync(
    path.join(guidesDir, "anima.zh.md"),
    "---\nmodel_key: anima-base-1\nlocale: zh\ntitle: Draft\ndraft: true\n---\nDraft body",
  );

  const outputPath = buildModelGuideModule(root);
  const output = fs.readFileSync(outputPath, "utf8");
  assert.match(output, /readonly ModelGuide\[\] = \[\];/);
  assert.doesNotMatch(output, /Draft body|"draft"/);
});
