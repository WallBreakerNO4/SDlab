import { isValidRunDir } from "@/lib/comfyui-types"
import { createClient } from "@/lib/supabase/server"

export const runtime = "nodejs"

type RouteContext = {
  params: Promise<{ runDir: string }>
}

type GridMetaRow = {
  x_columns?: unknown
}

type GridChunkRow = {
  x_index?: unknown
  y_index?: unknown
  status?: unknown
  blurhash?: unknown
  seed?: unknown
  prompt_hash?: unknown
  positive_prompt?: unknown
  generation_params?: unknown
  items?: unknown
}

const NO_STORE_HEADERS = {
  "Cache-Control": "private, no-store",
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value
  }

  if (typeof value === "string") {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }

  return null
}

function parseRangeParams(url: URL): { y_from: number; y_to: number } | null {
  const rawYFrom = url.searchParams.get("y_from")
  const rawYTo = url.searchParams.get("y_to")

  const parsedYFrom = toFiniteNumber(rawYFrom ?? "0")
  const parsedYTo = toFiniteNumber(rawYTo ?? (parsedYFrom === null ? "29" : String(parsedYFrom + 29)))

  if (parsedYFrom === null || parsedYTo === null) {
    return null
  }

  if (!Number.isInteger(parsedYFrom) || !Number.isInteger(parsedYTo)) {
    return null
  }

  if (parsedYFrom < 0 || parsedYTo < parsedYFrom) {
    return null
  }

  if (parsedYTo - parsedYFrom + 1 > 40) {
    return null
  }

  return { y_from: parsedYFrom, y_to: parsedYTo }
}

function normalizePublicBaseUrl(value: string | undefined): string {
  const raw = (value ?? "").trim()
  if (!raw) {
    return ""
  }

  return raw.replace(/\/+$/, "")
}

function buildVisibleXIndexMap(xColumns: unknown): Map<number, number> {
  const map = new Map<number, number>()
  if (!Array.isArray(xColumns)) {
    return map
  }

  for (const item of xColumns) {
    if (!item || typeof item !== "object") {
      continue
    }

    const record = item as Record<string, unknown>
    const original = toFiniteNumber(record.original_x_index)
    const visible = toFiniteNumber(record.visible_x_index)
    if (original === null || visible === null) {
      continue
    }

    if (!Number.isInteger(original) || !Number.isInteger(visible)) {
      continue
    }

    map.set(original, visible)
  }

  return map
}

function variantToSrc(
  variant: unknown,
  publicBaseUrl: string,
): string | null {
  if (!variant || typeof variant !== "object") {
    return null
  }

  const record = variant as Record<string, unknown>
  const bucket = typeof record.bucket === "string" ? record.bucket : null
  const r2Key = typeof record.r2_key === "string" ? record.r2_key : null
  const variantId = typeof record.variant_id === "string" ? record.variant_id : null

  if (bucket === "public" && publicBaseUrl && r2Key) {
    return `${publicBaseUrl}/${r2Key}`
  }

  if (bucket === "private" && variantId) {
    return `/api/media/variant/${variantId}`
  }

  return null
}

function originalDownloadUrl(original: unknown): string | null {
  if (!original || typeof original !== "object") {
    return null
  }

  const record = original as Record<string, unknown>
  const variantId = typeof record.variant_id === "string" ? record.variant_id : null

  if (!variantId) {
    return null
  }

  return `/api/media/variant/${variantId}?download=1`
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params
    if (!runDir || !isValidRunDir(runDir)) {
      return Response.json(
        { error: "Invalid runDir" },
        { status: 400, headers: NO_STORE_HEADERS },
      )
    }

    const url = new URL(request.url)
    const range = parseRangeParams(url)
    if (!range) {
      return Response.json(
        { error: "Invalid y range" },
        { status: 400, headers: NO_STORE_HEADERS },
      )
    }

    const supabase = await createClient()
    const { data: metaData, error: metaError } = await supabase.rpc("get_run_grid_meta", {
      target_run_dir: runDir,
    })

    if (metaError) {
      return Response.json(
        { error: "Failed to load grid chunk" },
        { status: 500, headers: NO_STORE_HEADERS },
      )
    }

    const metaRow = Array.isArray(metaData) && metaData.length > 0
      ? (metaData[0] as GridMetaRow)
      : null
    if (!metaRow) {
      return Response.json(
        { error: "Run not found" },
        { status: 404, headers: NO_STORE_HEADERS },
      )
    }

    const xIndexMap = buildVisibleXIndexMap(metaRow.x_columns)
    const publicBaseUrl = normalizePublicBaseUrl(process.env.NEXT_PUBLIC_R2_PUBLIC_BASE_URL)

    const { data: chunkData, error: chunkError } = await supabase.rpc("get_run_grid_chunk", {
      target_run_dir: runDir,
      y_from: range.y_from,
      y_to: range.y_to,
    })

    if (chunkError) {
      return Response.json(
        { error: "Failed to load grid chunk" },
        { status: 500, headers: NO_STORE_HEADERS },
      )
    }

    const rows = Array.isArray(chunkData) ? (chunkData as GridChunkRow[]) : []
    const cells = rows
      .map((row) => {
        const originalX = toFiniteNumber(row.x_index)
        const y = toFiniteNumber(row.y_index)

        if (
          originalX === null ||
          y === null ||
          !Number.isInteger(originalX) ||
          !Number.isInteger(y)
        ) {
          return null
        }

        const visibleX = xIndexMap.get(originalX)
        if (visibleX === undefined) {
          return null
        }

        const rawItems = Array.isArray(row.items) ? row.items : []
        const items = rawItems
          .map((item) => {
            if (!item || typeof item !== "object") {
              return null
            }

            const record = item as Record<string, unknown>
            const batchIndex = toFiniteNumber(record.batch_index)
            if (batchIndex === null || !Number.isInteger(batchIndex)) {
              return null
            }

            return {
              batch_index: batchIndex,
              thumb_src: variantToSrc(record.thumb, publicBaseUrl),
              display_src: variantToSrc(record.display, publicBaseUrl),
              original_download_url: originalDownloadUrl(record.original),
            }
          })
          .filter((item): item is NonNullable<typeof item> => item !== null)

        return {
          x: visibleX,
          y,
          status: typeof row.status === "string" ? row.status : "missing",
          blurhash: typeof row.blurhash === "string" ? row.blurhash : null,
          seed: toFiniteNumber(row.seed),
          prompt_hash: typeof row.prompt_hash === "string" ? row.prompt_hash : null,
          positive_prompt:
            typeof row.positive_prompt === "string" ? row.positive_prompt : null,
          generation_params:
            row.generation_params && typeof row.generation_params === "object"
              ? row.generation_params
              : {},
          items,
        }
      })
      .filter((cell): cell is NonNullable<typeof cell> => cell !== null)

    return Response.json(
      {
        y_from: range.y_from,
        y_to: range.y_to,
        cells,
      },
      { headers: NO_STORE_HEADERS },
    )
  } catch {
    return Response.json(
      { error: "Failed to load grid chunk" },
      { status: 500, headers: NO_STORE_HEADERS },
    )
  }
}
