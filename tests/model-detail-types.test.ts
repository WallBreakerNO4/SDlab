import assert from "node:assert/strict";
import test from "node:test";

import { isModelDetailResponse } from "../app/models/[runDir]/model-detail-types";

function validResponse() {
  return {
    run: {
      run_id: "run-id",
      created_at: "2026-07-22T00:00:00.000Z",
      run_dir: "run-dir",
      selection: { total_cells: 1 },
      model: {
        name: "Model",
        description: { zh: "中文", en: "English" },
      },
    },
    xLabels: [],
    yLabels: [],
    x_columns: [],
    y_indexes: [],
  };
}

test("isModelDetailResponse accepts localized string descriptions", () => {
  assert.equal(isModelDetailResponse(validResponse()), true);
});

test("isModelDetailResponse rejects non-string localized descriptions", () => {
  const response = validResponse();
  (response.run.model.description as { zh: unknown }).zh = 123;

  assert.equal(isModelDetailResponse(response), false);
});
