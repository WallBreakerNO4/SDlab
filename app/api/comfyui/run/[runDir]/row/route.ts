import { isValidRunDir } from "@/lib/comfyui-types";
import { privateObjectUrl, publicObjectUrl } from "@/lib/r2-url";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type { ImageCategory, R2Bucket } from "@/lib/supabase-types";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ runDir: string }>;
};

type DbImageRow = {
  run_dir: string;
  x_index: number;
  y_index: number;
  batch_index: number;
  category: ImageCategory;
  width: number | null;
  height: number | null;
  blurhash: string | null;
  seed: string | number | null;
  prompt_hash: string | null;
  positive_prompt: string | null;
  y_value: string | null;
  original_bucket: R2Bucket | null;
  original_r2_key: string | null;
  thumb_webp_bucket: R2Bucket | null;
  thumb_webp_r2_key: string | null;
  thumb_avif_bucket: R2Bucket | null;
  thumb_avif_r2_key: string | null;
  display_webp_bucket: R2Bucket | null;
  display_webp_r2_key: string | null;
  display_avif_bucket: R2Bucket | null;
  display_avif_r2_key: string | null;
};

type RowMeta = {
  seed: string | null;
  prompt_hash: string | null;
  positive_prompt: string | null;
  y_value: string | null;
};

type VariantUrls = {
  webp?: string;
  avif?: string;
};

type RowItem = {
  batch_index: number;
  category: ImageCategory;
  width: number | null;
  height: number | null;
  blurhash: string | null;
  meta: RowMeta;
  original: string | null;
  thumb: VariantUrls | null;
  display: VariantUrls | null;
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

function parseSeed(value: number | string | null): string | null {
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

function buildMeta(image: DbImageRow): RowMeta {
  return {
    seed: parseSeed(image.seed),
    prompt_hash: getNonEmptyString(image.prompt_hash),
    positive_prompt: getNonEmptyString(image.positive_prompt),
    y_value: getNonEmptyString(image.y_value),
  };
}

function urlFromVariant(bucket: R2Bucket, r2Key: string): string {
  return bucket === "public" ? publicObjectUrl(r2Key) : privateObjectUrl(r2Key);
}

function nullableUrl(
  bucket: R2Bucket | null,
  r2Key: string | null,
): string | null {
  if (!bucket || !r2Key) return null;
  return urlFromVariant(bucket, r2Key);
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

    const { data: imagesData, error: imagesError } = await supabase
      .from("comfyui_row_items")
      .select(
        "run_dir,x_index,y_index,batch_index,category,width,height,blurhash,seed,prompt_hash,positive_prompt,y_value,original_bucket,original_r2_key,thumb_webp_bucket,thumb_webp_r2_key,thumb_avif_bucket,thumb_avif_r2_key,display_webp_bucket,display_webp_r2_key,display_avif_bucket,display_avif_r2_key",
      )
      .eq("run_dir", runDir)
      .eq("y_index", yIndex)
      .order("x_index", { ascending: true })
      .order("batch_index", { ascending: true });

    if (imagesError) {
      return Response.json(
        { error: "Failed to load run row" },
        { status: 500 },
      );
    }

    const images = (imagesData ?? []) as DbImageRow[];
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

      return Response.json({ run_dir: runDir, y_index: yIndex, cells: [] });
    }

    const byXIndex = new Map<number, RowCell>();

    for (const image of images) {
      const meta = buildMeta(image);

      const thumb: VariantUrls = {};
      const display: VariantUrls = {};

      const thumbWebp = nullableUrl(
        image.thumb_webp_bucket,
        image.thumb_webp_r2_key,
      );
      const thumbAvif = nullableUrl(
        image.thumb_avif_bucket,
        image.thumb_avif_r2_key,
      );
      const displayWebp = nullableUrl(
        image.display_webp_bucket,
        image.display_webp_r2_key,
      );
      const displayAvif = nullableUrl(
        image.display_avif_bucket,
        image.display_avif_r2_key,
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
        original: nullableUrl(image.original_bucket, image.original_r2_key),
        thumb: Object.keys(thumb).length > 0 ? thumb : null,
        display: Object.keys(display).length > 0 ? display : null,
      };

      const existing = byXIndex.get(image.x_index);
      if (existing) {
        existing.items.push(item);
      } else {
        byXIndex.set(image.x_index, {
          x_index: image.x_index,
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

    return Response.json({ run_dir: runDir, y_index: yIndex, cells });
  } catch {
    return Response.json({ error: "Failed to load run row" }, { status: 500 });
  }
}
