import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const migrationDirectory = join(process.cwd(), "supabase", "migrations");

function readRpcMigration(): string {
  const migration = readdirSync(migrationDirectory).find((name) =>
    name.endsWith("_add_style_comparison_rpcs.sql"),
  );
  assert.ok(migration, "style comparison RPC migration must exist");
  return readFileSync(join(migrationDirectory, migration), "utf8");
}

test("slice RPC keeps auth, bounds and joins inside one security-invoker function", () => {
  const sql = readRpcMigration();

  assert.match(sql, /create or replace function public\.get_style_comparison_slice\s*\(/i);
  assert.match(sql, /security invoker/i);
  assert.match(sql, /set search_path\s*=\s*''/i);
  assert.match(sql, /auth\.uid\(\)/i);
  assert.match(sql, /cardinality\(p_style_keys\)[\s\S]*40/i);
  assert.match(sql, /cardinality\(p_run_dirs\)[\s\S]*12/i);
  assert.match(
    sql,
    /run_dir\s*!~\s*'\^\[a-z0-9\]\+\(-\[a-z0-9\]\+\)\*\$'/i,
  );
  assert.match(sql, /public\.user_style_favorites/i);
  assert.match(sql, /public\.run_style_items/i);
  assert.match(sql, /public\.run_view_index/i);
  assert.match(
    sql,
    /revoke execute on function public\.get_style_comparison_slice\(text\[\], text\[\]\) from public, anon/i,
  );
  assert.match(
    sql,
    /grant execute on function public\.get_style_comparison_slice\(text\[\], text\[\]\) to authenticated/i,
  );
});

test("public model catalog RPC joins all model metadata and has explicit grants", () => {
  const sql = readRpcMigration();

  assert.match(sql, /create or replace function public\.get_style_comparison_models\s*\(/i);
  assert.match(sql, /public\.run_view_index/i);
  assert.match(sql, /public\.run_list_items/i);
  assert.match(sql, /public\.runs/i);
  assert.match(
    sql,
    /revoke execute on function public\.get_style_comparison_models\(\) from public/i,
  );
  assert.match(
    sql,
    /grant execute on function public\.get_style_comparison_models\(\) to anon, authenticated/i,
  );
});

test("repository includes an EXPLAIN ANALYZE BUFFERS acceptance script", () => {
  const sql = readFileSync(
    join(process.cwd(), "supabase", "tests", "style_comparison_rpc_explain.sql"),
    "utf8",
  );
  assert.match(sql, /explain\s*\(analyze,\s*buffers\)/i);
  assert.match(sql, /1 x 1/i);
  assert.match(sql, /40 x 12/i);
  assert.match(sql, /-v viewer_id/i);
  assert.match(sql, /jsonb_array_length[\s\S]*placements[\s\S]*480/i);
});

test("Worker query boundaries use one RPC and keep the model cache at 300 seconds", () => {
  const sliceRoute = readFileSync(
    join(
      process.cwd(),
      "app",
      "api",
      "viewer",
      "style-comparison",
      "slice",
      "route.ts",
    ),
    "utf8",
  );
  const modelLoader = readFileSync(
    join(process.cwd(), "lib", "style-comparison-server.ts"),
    "utf8",
  );

  assert.equal(sliceRoute.match(/\.rpc\(/g)?.length, 1);
  assert.doesNotMatch(sliceRoute, /\.from\(/);
  assert.match(sliceRoute, /requireViewerForPreferenceWrite\(supabase\)/);
  assert.equal(modelLoader.match(/\.rpc\(/g)?.length, 1);
  assert.doesNotMatch(modelLoader, /\.from\(/);
  assert.match(modelLoader, /revalidate:\s*300/);
});
