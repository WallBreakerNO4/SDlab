import type { RunSummary } from "@/lib/comfyui-types";
import { privateObjectUrl, publicObjectUrl } from "@/lib/r2-url";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type {
  R2Bucket,
  SupabaseRunAssetRow,
  SupabaseRunAssetVariantRow,
  SupabaseRunRow,
} from "@/lib/supabase-types";

export const runtime = "nodejs";

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

function readModelMetadata(row: SupabaseRunRow) {
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

function urlFromVariant(bucket: R2Bucket, r2Key: string): string {
  return bucket === "public" ? publicObjectUrl(r2Key) : privateObjectUrl(r2Key);
}

function buildVariantUrls(variants: SupabaseRunAssetVariantRow[]): {
  thumb: { webp?: string; avif?: string } | null;
  display: { webp?: string; avif?: string } | null;
} {
  const thumb: { webp?: string; avif?: string } = {};
  const display: { webp?: string; avif?: string } = {};

  for (const variant of variants) {
    const r2Key = getNonEmptyString(variant.r2_key);
    if (!r2Key) {
      continue;
    }

    const url = urlFromVariant(variant.bucket, r2Key);

    if (variant.variant === "thumb_webp") thumb.webp = url;
    if (variant.variant === "thumb_avif") thumb.avif = url;
    if (variant.variant === "display_webp") display.webp = url;
    if (variant.variant === "display_avif") display.avif = url;
  }

  return {
    thumb: Object.keys(thumb).length > 0 ? thumb : null,
    display: Object.keys(display).length > 0 ? display : null,
  };
}

function buildRunAssets(
  rows: SupabaseRunAssetRow[],
  variantsByAssetId: Map<string, SupabaseRunAssetVariantRow[]>,
): NonNullable<RunSummary["assets"]> | null {
  const coverRows = rows
    .filter((row) => row.asset_role === "cover")
    .sort((a, b) => a.asset_index - b.asset_index);
  const homepageRows = rows
    .filter((row) => row.asset_role === "homepage_card")
    .sort((a, b) => a.asset_index - b.asset_index);

  const toAssetSummary = (row: SupabaseRunAssetRow) => {
    const assetId = getNonEmptyString(row.id);
    const variants = assetId ? (variantsByAssetId.get(assetId) ?? []) : [];
    const urls = buildVariantUrls(variants);

    return {
      width: row.width ?? null,
      height: row.height ?? null,
      blurhash: getNonEmptyString(row.blurhash),
      blurhash_width: row.blurhash_width ?? null,
      blurhash_height: row.blurhash_height ?? null,
      thumb: urls.thumb,
      display: urls.display,
    };
  };

  const cover = coverRows[0] ? toAssetSummary(coverRows[0]) : null;
  const homepageCards = homepageRows.map(toAssetSummary);

  if (!cover && homepageCards.length === 0) {
    return null;
  }

  return {
    cover,
    homepage_cards: homepageCards.length > 0 ? homepageCards : null,
  };
}

export async function GET(): Promise<Response> {
  try {
    const supabase = await createSupabaseAuthClient();
    const { data, error } = await supabase
      .from("runs")
      .select(
        "id, run_id, run_dir, created_at, x_count, y_count, total_cells, model_name, model_description_zh, model_description_en, model_homepage, model_huggingface, model_civitai",
      )
      .order("created_at", { ascending: false });

    if (error) {
      return Response.json(
        {
          error: "Failed to load runs",
        },
        { status: 500 },
      );
    }

    const rows = (data as SupabaseRunRow[] | null) ?? [];
    const runIds = rows
      .map((row) => getNonEmptyString(row.id))
      .filter((value): value is string => Boolean(value));
    const summarizedAssetsByRunId = new Map<
      string,
      NonNullable<RunSummary["assets"]>
    >();

    if (runIds.length > 0) {
      const { data: runAssetsData, error: runAssetsError } = await supabase
        .from("run_assets")
        .select(
          "id, run_id, asset_role, asset_index, source_path, source_sha256, width, height, blurhash, blurhash_width, blurhash_height, metadata",
        )
        .in("run_id", runIds)
        .in("asset_role", ["cover", "homepage_card"])
        .order("asset_index", { ascending: true });

      if (runAssetsError) {
        return Response.json(
          {
            error: "Failed to load runs",
          },
          { status: 500 },
        );
      }

      const runAssets = (runAssetsData as SupabaseRunAssetRow[] | null) ?? [];
      const assetIds = runAssets
        .map((row) => getNonEmptyString(row.id))
        .filter((value): value is string => Boolean(value));
      const variantsByAssetId = new Map<string, SupabaseRunAssetVariantRow[]>();
      const runAssetsByRunId = new Map<string, SupabaseRunAssetRow[]>();

      if (assetIds.length > 0) {
        const { data: runAssetVariantsData, error: runAssetVariantsError } =
          await supabase
            .from("run_asset_variants")
            .select("id, run_asset_id, variant, bucket, r2_key, content_type")
            .in("run_asset_id", assetIds);

        if (runAssetVariantsError) {
          return Response.json(
            {
              error: "Failed to load runs",
            },
            { status: 500 },
          );
        }

        const runAssetVariants =
          (runAssetVariantsData as SupabaseRunAssetVariantRow[] | null) ?? [];

        for (const row of runAssetVariants) {
          const runAssetId = getNonEmptyString(row.run_asset_id);
          if (!runAssetId) {
            continue;
          }

          const existing = variantsByAssetId.get(runAssetId);
          if (existing) {
            existing.push(row);
          } else {
            variantsByAssetId.set(runAssetId, [row]);
          }
        }
      }

      for (const row of runAssets) {
        const runId = getNonEmptyString(row.run_id);
        if (!runId) {
          continue;
        }

        const existing = runAssetsByRunId.get(runId);
        if (existing) {
          existing.push(row);
        } else {
          runAssetsByRunId.set(runId, [row]);
        }
      }

      for (const [runId, assetRows] of runAssetsByRunId.entries()) {
        runAssetsByRunId.set(
          runId,
          assetRows.sort((a, b) => a.asset_index - b.asset_index),
        );
      }

      for (const [runId, assetRows] of runAssetsByRunId.entries()) {
        const assets = buildRunAssets(assetRows, variantsByAssetId);
        if (assets) {
          summarizedAssetsByRunId.set(runId, assets);
        }
      }
    }

    const runs: RunSummary[] = [];
    for (const row of rows) {
      const runId = getNonEmptyString(row.run_id);
      const xCount = getNonNegativeInteger(row.x_count);
      const yCount = getNonNegativeInteger(row.y_count);
      const totalCells = getNonNegativeInteger(row.total_cells);

      if (!runId || xCount === null || yCount === null || totalCells === null) {
        return Response.json(
          {
            error: "Failed to load runs",
          },
          { status: 500 },
        );
      }

      runs.push({
        run_id: runId,
        created_at: row.created_at,
        run_dir: row.run_dir,
        x_count: xCount,
        y_count: yCount,
        total_cells: totalCells,
        model: readModelMetadata(row),
        assets: row.id ? (summarizedAssetsByRunId.get(row.id) ?? null) : null,
      });
    }

    return Response.json(runs);
  } catch {
    return Response.json(
      {
        error: "Failed to load runs",
      },
      { status: 500 },
    );
  }
}
