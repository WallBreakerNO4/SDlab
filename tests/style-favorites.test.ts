import assert from "node:assert/strict";
import test from "node:test";

import { isStyleFavoriteLabel } from "../lib/style-favorites";

test("isStyleFavoriteLabel accepts a regular label", () => {
  assert.equal(isStyleFavoriteLabel("artist style"), true);
});

test("isStyleFavoriteLabel accepts labels with surrounding whitespace", () => {
  assert.equal(isStyleFavoriteLabel("  artist style  "), true);
});

test("isStyleFavoriteLabel rejects whitespace-only labels", () => {
  const whitespaceOnlyLabels = ["   ", "\t", "\n", "\r\n", " \t\n "];

  for (const label of whitespaceOnlyLabels) {
    assert.equal(
      isStyleFavoriteLabel(label),
      false,
      `expected ${JSON.stringify(label)} to be rejected`,
    );
  }
});

test("isStyleFavoriteLabel accepts a label at the 1000-character limit", () => {
  assert.equal(isStyleFavoriteLabel("a".repeat(1000)), true);
});

test("isStyleFavoriteLabel rejects a label over the 1000-character limit", () => {
  assert.equal(isStyleFavoriteLabel("a".repeat(1001)), false);
});
