import { isValidRunDir } from "@/lib/comfyui-types";
import {
  privateObjectUrlWithMetadata,
  privateSignedUrlResponseMaxAgeSeconds,
  privateSignedUrlTtlSeconds,
  publicObjectUrl,
} from "@/lib/r2-url";
import { buildVisibleRunGridColumns } from "@/lib/run-grid-visibility";
import { getViewerShowNsfwPreference } from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type {
  ImageCategory,
  R2Bucket,
  SupabaseRunGridItemRow,
} from "@/lib/supabase-types";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ runDir: string }>;
};

type RowMeta = {
  seed: string | null;
  prompt_hash: string | null;
  positive_prompt: string | null;
  y_value: string | null;
};

type VariantUrls = {
  bucket: R2Bucket;
  cache_key: string;
  url?: string;
};

type VariantSources = {
  webp?: VariantUrls;
  avif?: VariantUrls;
};

type RowItem = {
  batch_index: number;
  category: ImageCategory;
  width: number | null;
  height: number | null;
  blurhash: string | null;
  meta: RowMeta;
  thumb: VariantSources | null;
  display: VariantSources | null;
};

type RowCell = {
  x_index: number;
  y_index: number;
  items: RowItem[];
};

function getNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function parseNonNegativeInt(raw: string | null): number | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!/^[0-9]+$/.test(trimmed)) return null;
  const n = Number(trimmed);
  if (!Number.isSafeInteger(n) || n < 0) return null;
  return n;
}

function parseSeed(value: number | string | null | undefined): string | null {
  if (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Number.isInteger(value)
  ) {
    return String(value);
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return /^-?\d+$/.test(trimmed) ? trimmed : null;
  }
  return null;
}

function buildMeta(image: SupabaseRunGridItemRow): RowMeta {
  return {
    seed: parseSeed(image.seed),
    prompt_hash: getNonEmptyString(image.prompt_hash),
    positive_prompt: getNonEmptyString(image.positive_prompt),
    y_value: getNonEmptyString(image.y_value),
  };
}

function nullableResolvedVariant(
  bucket: R2Bucket | null | undefined,
  r2Key: string | null | undefined,
  cacheKey: string | null | undefined,
  signedAt: Date,
): VariantUrls | null {
  if (!bucket && !r2Key && !cacheKey) return null;
  if (!bucket || !r2Key || !cacheKey) {
    throw new Error("Invalid row variant payload");
  }

  if (bucket === "public") {
    return {
      bucket,
      cache_key: cacheKey,
      url: publicObjectUrl(r2Key),
    };
  }

  const signed = privateObjectUrlWithMetadata(r2Key, signedAt);
  return {
    bucket,
    cache_key: cacheKey,
    url: signed.url,
  };
}

function nullableCachedVariant(
  bucket: R2Bucket | null | undefined,
  r2Key: string | null | undefined,
  cacheKey: string | null | undefined,
): VariantUrls | null {
  if (!bucket && !r2Key && !cacheKey) return null;
  if (!bucket || !r2Key || !cacheKey) {
    throw new Error("Invalid display cache payload");
  }

  return {
    bucket,
    cache_key: cacheKey,
    ...(bucket === "public" ? { url: publicObjectUrl(r2Key) } : {}),
  };
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params;
    if (!isValidRunDir(runDir)) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const url = new URL(request.url);
    const yIndex = parseNonNegativeInt(url.searchParams.get("y_index"));
    if (yIndex === null) {
      return Response.json({ error: "Invalid y_index" }, { status: 400 });
    }

    const supabase = await createSupabaseAuthClient();
    const showNsfw = await getViewerShowNsfwPreference(supabase);
    const signingAt = new Date();
    const signedUrlTtlSeconds = privateSignedUrlTtlSeconds();
    const responseMaxAge = privateSignedUrlResponseMaxAgeSeconds();
    const responseHeaders = {
      "Cache-Control": `private, max-age=${responseMaxAge}`,
      Vary: "Cookie",
    };

    const { data: runMeta, error: runMetaError } = await supabase
      .from("runs")
      .select("x_columns")
      .eq("run_dir", runDir)
      .maybeSingle();

    if (runMetaError) {
      return Response.json(
        { error: "Failed to load run row" },
        { status: 500 },
      );
    }

    if (!runMeta) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const visibleColumns = buildVisibleRunGridColumns(runMeta.x_columns, {
      showNsfw,
    });

    if (visibleColumns.allowedOriginalXIndexes.length === 0) {
      return Response.json(
        { run_dir: runDir, y_index: yIndex, signed_url_expires_at: null, cells: [] },
        { headers: responseHeaders },
      );
    }

    const { data: imagesData, error: imagesError } = await supabase
      .from("run_grid_items")
      .select(
        "run_dir,x_index,y_index,batch_index,category,width,height,blurhash,seed,prompt_hash,positive_prompt,y_value,thumb_webp_bucket,thumb_webp_r2_key,thumb_webp_cache_key,thumb_avif_bucket,thumb_avif_r2_key,thumb_avif_cache_key,display_webp_bucket,display_webp_r2_key,display_webp_cache_key,display_avif_bucket,display_avif_r2_key,display_avif_cache_key",
      )
      .eq("run_dir", runDir)
      .eq("y_index", yIndex)
      .in("x_index", visibleColumns.allowedOriginalXIndexes)
      .order("x_index", { ascending: true })
      .order("batch_index", { ascending: true });

    if (imagesError) {
      return Response.json(
        { error: "Failed to load run row" },
        { status: 500 },
      );
    }

    const images = (imagesData as SupabaseRunGridItemRow[] | null) ?? [];
    if (images.length === 0) {
      const { data: runRow, error: runError } = await supabase
        .from("runs")
        .select("run_dir")
        .eq("run_dir", runDir)
        .maybeSingle();

      if (runError) {
        return Response.json(
          { error: "Failed to load run row" },
          { status: 500 },
        );
      }

      if (!runRow) {
        return Response.json({ error: "Run not found" }, { status: 404 });
      }

      return Response.json(
        { run_dir: runDir, y_index: yIndex, signed_url_expires_at: null, cells: [] },
        { headers: responseHeaders },
      );
    }

    const byXIndex = new Map<number, RowCell>();

    for (const image of images) {
      const meta = buildMeta(image);

      const thumb: VariantSources = {};
      const display: VariantSources = {};

      const thumbWebp = nullableResolvedVariant(
        image.thumb_webp_bucket,
        image.thumb_webp_r2_key,
        image.thumb_webp_cache_key,
        signingAt,
      );
      const thumbAvif = nullableResolvedVariant(
        image.thumb_avif_bucket,
        image.thumb_avif_r2_key,
        image.thumb_avif_cache_key,
        signingAt,
      );
      const displayWebp = nullableCachedVariant(
        image.display_webp_bucket,
        image.display_webp_r2_key,
        image.display_webp_cache_key,
      );
      const displayAvif = nullableCachedVariant(
        image.display_avif_bucket,
        image.display_avif_r2_key,
        image.display_avif_cache_key,
      );

      if (thumbWebp) thumb.webp = thumbWebp;
      if (thumbAvif) thumb.avif = thumbAvif;
      if (displayWebp) display.webp = displayWebp;
      if (displayAvif) display.avif = displayAvif;

      const item: RowItem = {
        batch_index: image.batch_index,
        category: image.category,
        width: image.width,
        height: image.height,
        blurhash: image.blurhash,
        meta,
        thumb: Object.keys(thumb).length > 0 ? thumb : null,
        display: Object.keys(display).length > 0 ? display : null,
      };

      const remappedXIndex = visibleColumns.remapOriginalXIndex(image.x_index);
      if (remappedXIndex === null) {
        continue;
      }

      const existing = byXIndex.get(remappedXIndex);
      if (existing) {
        existing.items.push(item);
      } else {
        byXIndex.set(remappedXIndex, {
          x_index: remappedXIndex,
          y_index: yIndex,
          items: [item],
        });
      }
    }

    const cells = Array.from(byXIndex.values())
      .sort((a, b) => a.x_index - b.x_index)
      .map((cell) => ({
        ...cell,
        items: [...cell.items].sort((a, b) => a.batch_index - b.batch_index),
      }));

    return Response.json(
      {
        run_dir: runDir,
        y_index: yIndex,
        signed_url_expires_at: new Date(
          signingAt.getTime() + signedUrlTtlSeconds * 1000,
        ).toISOString(),
        cells,
      },
      {
        headers: responseHeaders,
      },
    );
  } catch {
    return Response.json({ error: "Failed to load run row" }, { status: 500 });
  }
}
