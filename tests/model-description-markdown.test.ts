import assert from "node:assert/strict";
import test from "node:test";

import { transformModelDescriptionUrl } from "../app/models/[runDir]/model-description-markdown";

test("transformModelDescriptionUrl rejects slash-based network-path references", () => {
  for (const url of [
    "//example.com/path",
    "\\\\example.com/path",
    "/\\example.com/path",
    "\\/example.com/path",
  ]) {
    assert.equal(transformModelDescriptionUrl(url), undefined, url);
  }
});

test("transformModelDescriptionUrl preserves relative and http(s) links", () => {
  assert.equal(transformModelDescriptionUrl("/info"), "/info");
  assert.equal(
    transformModelDescriptionUrl("https://example.com/docs"),
    "https://example.com/docs",
  );
  assert.equal(transformModelDescriptionUrl("javascript:alert(1)"), undefined);
});
