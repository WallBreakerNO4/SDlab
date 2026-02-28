import { isValidRunDir } from "@/lib/comfyui-types"
import { privateObjectUrl, publicObjectUrl } from "@/lib/r2-url"
import {
  createSupabaseServiceClient,
  SupabaseServiceConfigError,
} from "@/lib/supabase-server"
import type {
  ImageCategory,
  ImageVariantName,
  JsonObject,
  JsonValue,
  R2Bucket,
} from "@/lib/supabase-types"

export const runtime = "nodejs"

type RouteContext = {
  params: Promise<{ runDir: string }>
}

type DbImageVariantRow = {
  variant: ImageVariantName
  bucket: R2Bucket
  r2_key: string
  content_type: string
  width: number | null
  height: number | null
}

type DbImageRow = {
  x_index: number
  y_index: number
  batch_index: number
  category: ImageCategory
  width: number | null
  height: number | null
  blurhash: string | null
  metadata: JsonValue
  image_variants: DbImageVariantRow[] | null
}

type RowMeta = {
  seed: number | null
  prompt_hash: string | null
  positive_prompt: string | null
  y_value: string | null
}

type VariantUrls = {
  webp?: string
  avif?: string
}

type RowItem = {
  batch_index: number
  category: ImageCategory
  width: number | null
  height: number | null
  blurhash: string | null
  meta: RowMeta
  original: string | null
  thumb: VariantUrls | null
  display: VariantUrls | null
}

type RowCell = {
  x_index: number
  y_index: number
  items: RowItem[]
}

function asJsonObject(value: JsonValue): JsonObject | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null
  }
  return value as JsonObject
}

function getNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function getFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function parseNonNegativeInt(raw: string | null): number | null {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!/^[0-9]+$/.test(trimmed)) return null
  const n = Number(trimmed)
  if (!Number.isSafeInteger(n) || n < 0) return null
  return n
}

function buildMeta(metadata: JsonValue): RowMeta {
  const obj = asJsonObject(metadata)
  if (!obj) {
    return { seed: null, prompt_hash: null, positive_prompt: null, y_value: null }
  }

  return {
    seed: getFiniteNumber(obj.seed),
    prompt_hash: getNonEmptyString(obj.prompt_hash),
    positive_prompt: getNonEmptyString(obj.positive_prompt),
    y_value: getNonEmptyString(obj.y_value),
  }
}

function urlFromVariant(bucket: R2Bucket, r2Key: string): string {
  return bucket === "public" ? publicObjectUrl(r2Key) : privateObjectUrl(r2Key)
}

function applyVariantUrl(
  acc: { thumb: VariantUrls; display: VariantUrls },
  variant: ImageVariantName,
  url: string,
): void {
  if (variant === "thumb_webp") acc.thumb.webp = url
  if (variant === "thumb_avif") acc.thumb.avif = url
  if (variant === "display_webp") acc.display.webp = url
  if (variant === "display_avif") acc.display.avif = url
}

export async function GET(request: Request, context: RouteContext): Promise<Response> {
  try {
    const { runDir } = await context.params
    if (!isValidRunDir(runDir)) {
      return Response.json({ error: "Run not found" }, { status: 404 })
    }

    const url = new URL(request.url)
    const yIndex = parseNonNegativeInt(url.searchParams.get("y_index"))
    if (yIndex === null) {
      return Response.json({ error: "Invalid y_index" }, { status: 400 })
    }

    const supabase = createSupabaseServiceClient()

    const { data: runRow, error: runError } = await supabase
      .from("runs")
      .select("id")
      .eq("run_dir", runDir)
      .maybeSingle()

    if (runError) {
      return Response.json({ error: "Failed to load run row" }, { status: 500 })
    }

    const rawRunId = (runRow as { id?: unknown } | null)?.id
    const runId = typeof rawRunId === "string" ? rawRunId : null
    if (!runId) {
      return Response.json({ error: "Run not found" }, { status: 404 })
    }

    const { data: imagesData, error: imagesError } = await supabase
      .from("images")
      .select(
        "x_index,y_index,batch_index,category,width,height,blurhash,metadata,image_variants(variant,bucket,r2_key,content_type,width,height)",
      )
      .eq("run_id", runId)
      .eq("y_index", yIndex)
      .order("x_index", { ascending: true })
      .order("batch_index", { ascending: true })

    if (imagesError) {
      return Response.json({ error: "Failed to load run row" }, { status: 500 })
    }

    const images = (imagesData ?? []) as DbImageRow[]

    const byXIndex = new Map<number, RowCell>()

    for (const image of images) {
      const variants = Array.isArray(image.image_variants) ? image.image_variants : []

      const urlsAcc = { thumb: {} as VariantUrls, display: {} as VariantUrls }
      let originalUrl: string | null = null
      for (const v of variants) {
        if (v.variant === "original_png") {
          originalUrl = urlFromVariant(v.bucket, v.r2_key)
          continue
        }

        if (
          v.variant !== "thumb_webp" &&
          v.variant !== "thumb_avif" &&
          v.variant !== "display_webp" &&
          v.variant !== "display_avif"
        ) {
          continue
        }

        const urlValue = urlFromVariant(v.bucket, v.r2_key)
        applyVariantUrl(urlsAcc, v.variant, urlValue)
      }

      const meta = buildMeta(image.metadata)

      const item: RowItem = {
        batch_index: image.batch_index,
        category: image.category,
        width: image.width,
        height: image.height,
        blurhash: image.blurhash,
        meta,
        original: originalUrl,
        thumb: Object.keys(urlsAcc.thumb).length > 0 ? urlsAcc.thumb : null,
        display: Object.keys(urlsAcc.display).length > 0 ? urlsAcc.display : null,
      }

      const existing = byXIndex.get(image.x_index)
      if (existing) {
        existing.items.push(item)
      } else {
        byXIndex.set(image.x_index, { x_index: image.x_index, y_index: yIndex, items: [item] })
      }
    }

    const cells = Array.from(byXIndex.values())
      .sort((a, b) => a.x_index - b.x_index)
      .map((cell) => ({
        ...cell,
        items: [...cell.items].sort((a, b) => a.batch_index - b.batch_index),
      }))

    return Response.json({ run_dir: runDir, y_index: yIndex, cells })
  } catch (error) {
    if (error instanceof SupabaseServiceConfigError) {
      return Response.json({ error: error.message }, { status: 500 })
    }

    return Response.json({ error: "Failed to load run row" }, { status: 500 })
  }
}
