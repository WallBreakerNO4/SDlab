import "server-only";

import { unstable_cache } from "next/cache";
import { createClient } from "@supabase/supabase-js";

import { getPublicEnv } from "@/lib/env/public";
import type { StyleComparisonModel, StyleComparisonXColumn } from "@/lib/style-comparison";

type PublishedRun = { run_dir: string; release_id: string };
type RunListRow = { run_dir: string; created_at: string; model_name: string | null };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readXColumns(value: unknown): StyleComparisonXColumn[] {
  if (!Array.isArray(value)) return [];
  return value.map((raw, index) => {
    if (!isRecord(raw)) return { x_index: index, type: null, description: null };
    const description = isRecord(raw.description)
      ? {
          zh: typeof raw.description.zh === "string" ? raw.description.zh : null,
          en: typeof raw.description.en === "string" ? raw.description.en : null,
        }
      : null;
    return {
      x_index: index,
      type: typeof raw.type === "string" ? raw.type : null,
      description,
    };
  });
}

async function loadPublishedRuns(): Promise<StyleComparisonModel[]> {
  const { supabaseUrl, supabasePublishableKey } = getPublicEnv();
  const supabase = createClient(supabaseUrl, supabasePublishableKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const published: PublishedRun[] = [];
  for (let offset = 0; ; offset += 1000) {
    const { data, error } = await supabase
      .from("run_view_index")
      .select("run_dir,release_id")
      .order("run_dir", { ascending: true })
      .range(offset, offset + 999);
    if (error) throw error;
    const rows = (data ?? []).filter(
      (row): row is PublishedRun =>
        isRecord(row) && typeof row.run_dir === "string" && typeof row.release_id === "string",
    );
    published.push(...rows);
    if (rows.length < 1000) break;
  }
  const runDirs = [...new Set(published.map((row) => row.run_dir))];
  if (runDirs.length === 0) return [];

  const [{ data: listData, error: listError }, { data: runsData, error: runsError }] = await Promise.all([
    supabase.from("run_list_items").select("run_dir,created_at,model_name").in("run_dir", runDirs),
    supabase.from("runs").select("run_dir,x_columns").in("run_dir", runDirs),
  ]);
  if (listError || runsError) throw listError ?? runsError;

  const listByRun = new Map<string, RunListRow>();
  for (const row of listData ?? []) {
    if (!isRecord(row) || typeof row.run_dir !== "string" || typeof row.created_at !== "string") continue;
    listByRun.set(row.run_dir, {
      run_dir: row.run_dir,
      created_at: row.created_at,
      model_name: typeof row.model_name === "string" ? row.model_name : null,
    });
  }
  const xColumnsByRun = new Map<string, StyleComparisonXColumn[]>();
  for (const row of runsData ?? []) {
    if (!isRecord(row) || typeof row.run_dir !== "string") continue;
    xColumnsByRun.set(row.run_dir, readXColumns(row.x_columns));
  }
  return published
    .map((row) => {
      const list = listByRun.get(row.run_dir);
      return {
        run_dir: row.run_dir,
        name: list?.model_name ?? null,
        created_at: list?.created_at ?? "",
        x_columns: xColumnsByRun.get(row.run_dir) ?? [],
      } satisfies StyleComparisonModel;
    })
    .sort((a, b) => b.created_at.localeCompare(a.created_at) || a.run_dir.localeCompare(b.run_dir));
}

export const getCachedPublishedRuns = unstable_cache(loadPublishedRuns, ["style-comparison-models"], {
  revalidate: 300,
  tags: ["style-comparison-models"],
});
