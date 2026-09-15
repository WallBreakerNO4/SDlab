import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { normalizeEvaluationStatus } from "../lib/comfyui-types";

const migrationDirectory = join(process.cwd(), "supabase", "migrations");

function readStatusMigration(): string {
  const migration = readdirSync(migrationDirectory).find((name) =>
    name.endsWith("_add_run_list_items_status_and_published_at.sql"),
  );
  assert.ok(migration, "run_list_items status migration must exist");
  return readFileSync(join(migrationDirectory, migration), "utf8");
}

test("run_list_items migration adds status, generated_cells and published_at with backfill", () => {
  const sql = readStatusMigration();

  assert.match(sql, /alter table public\.run_list_items/i);
  assert.match(sql, /add column if not exists status text/i);
  assert.match(sql, /add column if not exists generated_cells integer/i);
  assert.match(sql, /add column if not exists published_at timestamptz/i);
  assert.match(sql, /set status = 'complete'[\s\S]*where status is null/i);
  assert.match(
    sql,
    /set generated_cells = total_cells[\s\S]*where generated_cells is null/i,
  );
  assert.match(
    sql,
    /set published_at = created_at[\s\S]*where published_at is null/i,
  );
  assert.match(sql, /alter column status set default 'complete'/i);
  assert.match(sql, /alter column status set not null/i);
  assert.match(sql, /alter column generated_cells set not null/i);
  assert.match(sql, /alter column published_at set not null/i);
  assert.match(sql, /check \(status in \('in_progress', 'complete'\)\)/i);
  assert.match(
    sql,
    /create index if not exists run_list_items_published_at_desc_idx[\s\S]*published_at desc/i,
  );
});

test("homepage run list orders by published_at and normalizes evaluation status", () => {
  const runList = readFileSync(
    join(process.cwd(), "lib", "run-list.ts"),
    "utf8",
  );

  assert.match(runList, /\.order\("published_at", \{ ascending: false \}\)/);
  assert.match(runList, /normalizeEvaluationStatus\(row\.status\)/);
});

test("evaluation status normalization treats missing or unknown values as complete", () => {
  assert.equal(normalizeEvaluationStatus("in_progress"), "in_progress");
  assert.equal(normalizeEvaluationStatus("complete"), "complete");
  assert.equal(normalizeEvaluationStatus(null), "complete");
  assert.equal(normalizeEvaluationStatus(undefined), "complete");
  assert.equal(normalizeEvaluationStatus("weird"), "complete");
});
