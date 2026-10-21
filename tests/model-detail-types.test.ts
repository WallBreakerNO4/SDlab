import assert from "node:assert/strict";
import test from "node:test";

import {
  isCurrentRunView,
  isModelDetailResponse,
} from "../app/models/[runDir]/model-detail-types";

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

function validCurrentView() {
  return {
    schema_version: 2,
    run_dir: "run-dir",
    release_id: "release-1",
    bootstrap_sfw_key: "runs/run-dir/view/v2/release-1/bootstrap.sfw.json",
    public_row_prefix: "runs/run-dir/view/v2/release-1/rows/public/",
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

test("isCurrentRunView accepts optional evaluation status with legacy compat", () => {
  assert.equal(isCurrentRunView(validCurrentView()), true);
  assert.equal(
    isCurrentRunView({ ...validCurrentView(), status: "in_progress" }),
    true,
  );
  assert.equal(
    isCurrentRunView({ ...validCurrentView(), status: "complete" }),
    true,
  );
  assert.equal(
    isCurrentRunView({ ...validCurrentView(), status: "paused" }),
    false,
  );
  assert.equal(
    isCurrentRunView({ ...validCurrentView(), status: 1 }),
    false,
  );
});
