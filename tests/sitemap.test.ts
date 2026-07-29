import assert from "node:assert/strict";
import test from "node:test";

import { buildGuideSitemapEntries } from "../lib/model-guides-sitemap";

test("guide sitemap only includes available locales and alternates", () => {
  const entries = buildGuideSitemapEntries([
    { modelKey: "anima base/1", locale: "zh" },
    { modelKey: "anima base/1", locale: "en" },
    { modelKey: "other", locale: "en" },
  ]);

  assert.equal(entries.length, 3);
  assert.deepEqual(
    entries.map((entry) => entry.url),
    [
      "https://sdlab.wall-breaker-no4.xyz/zh/guides/anima%20base%2F1",
      "https://sdlab.wall-breaker-no4.xyz/en/guides/anima%20base%2F1",
      "https://sdlab.wall-breaker-no4.xyz/en/guides/other",
    ],
  );
  assert.deepEqual(entries[0]?.alternates?.languages, {
    zh: "https://sdlab.wall-breaker-no4.xyz/zh/guides/anima%20base%2F1",
    en: "https://sdlab.wall-breaker-no4.xyz/en/guides/anima%20base%2F1",
  });
  assert.deepEqual(entries[2]?.alternates?.languages, {
    en: "https://sdlab.wall-breaker-no4.xyz/en/guides/other",
  });
});
