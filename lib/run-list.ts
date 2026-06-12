import "server-only";

import { unstable_cache } from "next/cache";
import { createClient } from "@supabase/supabase-js";

import type { RunAssetSummary, RunSummary } from "@/lib/comfyui-types";
import { getPublicEnv } from "@/lib/env/public";
import { publicObjectUrl } from "@/lib/r2-url";
import type {
  JsonObject,
  JsonValue,
  SupabaseRunListItemRow,
} from "@/lib/supabase-types";

function asJsonObject(value: JsonValue | null | undefined): JsonObject | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }

  return value as JsonObject;
}

function getNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function getNonNegativeInteger(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    return null;
  }

  return value;
}

function readModelMetadata(row: SupabaseRunListItemRow) {
  return {
    name: getNonEmptyString(row.model_name),
    description: {
      zh: getNonEmptyString(row.model_description_zh),
      en: getNonEmptyString(row.model_description_en),
    },
    links: {
      homepage: getNonEmptyString(row.model_homepage),
      huggingface: getNonEmptyString(row.model_huggingface),
      civitai: getNonEmptyString(row.model_civitai),
    },
  };
}

function toPublicUrl(r2Key: unknown): string | null {
  const key = getNonEmptyString(r2Key);
  if (!key) {
    return null;
  }

  return publicObjectUrl(key);
}

function readAssetProjection(
  value: JsonValue | null | undefined,
): RunAssetSummary | null {
  const raw = asJsonObject(value);
  if (!raw) {
    return null;
  }

  const thumbWebp = toPublicUrl(raw.thumb_webp_r2_key);
  const thumbAvif = toPublicUrl(raw.thumb_avif_r2_key);
  const displayWebp = toPublicUrl(raw.display_webp_r2_key);
  const displayAvif = toPublicUrl(raw.display_avif_r2_key);

  const thumb =
    thumbWebp || thumbAvif
      ? {
          webp: thumbWebp ?? undefined,
          avif: thumbAvif ?? undefined,
        }
      : null;
  const display =
    displayWebp || displayAvif
      ? {
          webp: displayWebp ?? undefined,
          avif: displayAvif ?? undefined,
        }
      : null;

  return {
    width: getNonNegativeInteger(raw.width),
    height: getNonNegativeInteger(raw.height),
    blurhash: getNonEmptyString(raw.blurhash),
    blurhash_width: getNonNegativeInteger(raw.blurhash_width),
    blurhash_height: getNonNegativeInteger(raw.blurhash_height),
    thumb,
    display,
  };
}

function readHomepageCards(
  value: JsonValue | null | undefined,
): RunAssetSummary[] | null {
  if (!Array.isArray(value)) {
    return null;
  }

  const cards = value
    .map((item) => readAssetProjection(item as JsonValue))
    .filter((item): item is RunAssetSummary => item !== null);

  return cards.length > 0 ? cards : null;
}

export async function loadRunSummariesUncached(): Promise<RunSummary[]> {
  const { supabaseUrl, supabasePublishableKey } = getPublicEnv();

  const supabase = createClient(supabaseUrl, supabasePublishableKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  });
  const { data, error } = await supabase
    .from("run_list_items")
    .select(
      "run_id, run_dir, created_at, x_count, y_count, total_cells, model_name, model_description_zh, model_description_en, model_homepage, model_huggingface, model_civitai, cover, homepage_cards",
    )
    .order("created_at", { ascending: false })
    .limit(50);

  if (error) {
    throw new Error(`Failed to load runs: ${error.message}`);
  }

  const rows = (data as SupabaseRunListItemRow[] | null) ?? [];
  const runs: RunSummary[] = [];

  for (const row of rows) {
    const runId = getNonEmptyString(row.run_id);
    const xCount = getNonNegativeInteger(row.x_count);
    const yCount = getNonNegativeInteger(row.y_count);
    const totalCells = getNonNegativeInteger(row.total_cells);

    if (!runId || xCount === null || yCount === null || totalCells === null) {
      throw new Error(
        `Invalid run_list_items row for run_dir=${row.run_dir}`,
      );
    }

    const cover = readAssetProjection(
      row.cover as JsonValue | null | undefined,
    );
    const homepageCards = readHomepageCards(
      row.homepage_cards as JsonValue | null | undefined,
    );

    runs.push({
      run_id: runId,
      created_at: row.created_at,
      run_dir: row.run_dir,
      x_count: xCount,
      y_count: yCount,
      total_cells: totalCells,
      model: readModelMetadata(row),
      assets:
        cover || homepageCards
          ? {
              cover,
              homepage_cards: homepageCards,
            }
          : null,
    });
  }

  return runs;
}

export const listRunSummaries = unstable_cache(
  loadRunSummariesUncached,
  ["run-list-summaries"],
  { revalidate: 300, tags: ["run-list"] },
);
