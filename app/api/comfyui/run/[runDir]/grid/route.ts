import { isValidRunDir } from "@/lib/comfyui-types"
import { createSupabaseAuthClient } from "@/lib/supabase-auth"
import type { ImageCategory, JsonObject, JsonValue, SupabaseRunRow } from "@/lib/supabase-types"

export const runtime = "nodejs"

type RouteContext = {
  params: Promise<{ runDir: string }>
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

function pickXColumn(raw: JsonObject): { type: string | null; description: JsonObject | null } {
  const type = getNonEmptyString(raw.type)
  const description = asJsonObject(raw.description as JsonValue)
  return { type, description }
}

export async function GET(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params
    if (!isValidRunDir(runDir)) {
      return Response.json({ error: "Run not found" }, { status: 404 })
    }

    const supabase = await createSupabaseAuthClient()
    const { data, error } = await supabase
      .from("runs")
      .select("id, run_dir, x_columns, y_indexes, run_json")
      .eq("run_dir", runDir)
      .maybeSingle()
    if (error) {
      return Response.json(
        {
          error: "Failed to load run grid",
        },
        { status: 500 },
      )
    }

    const row = data as (SupabaseRunRow & { id: string }) | null
    if (!row) {
      return Response.json({ error: "Run not found" }, { status: 404 })
    }

    const runJson = asJsonObject(row.run_json)
    const selection = runJson ? asJsonObject(runJson.selection as JsonValue) : null
    if (!selection) {
      return Response.json(
        {
          error: "Failed to load run grid",
        },
        { status: 500 },
      )
    }

    const xColumnsRaw = Array.isArray(row.x_columns) ? row.x_columns : selection.x_columns
    const yIndexesRaw = Array.isArray(row.y_indexes) ? row.y_indexes : selection.y_indexes

    const x_columns = Array.isArray(xColumnsRaw)
      ? xColumnsRaw
          .map((item) => asJsonObject(item as JsonValue))
          .filter((item): item is JsonObject => item !== null)
          .map(pickXColumn)
      : []

    const y_indexes: number[] = Array.isArray(yIndexesRaw)
      ? yIndexesRaw.filter(
          (item): item is number => typeof item === "number" && Number.isFinite(item),
        )
      : []

    const x_count = x_columns.length
    const y_count = y_indexes.length

    // Fetch all blurhash + basic metadata for the entire run.
    // This allows the frontend to show blurhash placeholders instantly
    // without waiting for per-row API calls.
    // PostgREST enforces max_rows (default 1000), so we paginate to
    // guarantee we retrieve every image in the run.
    type BlurhashRow = {
      x_index: number
      y_index: number
      batch_index: number
      category: ImageCategory
      width: number | null
      height: number | null
      blurhash: string | null
    }

    const PAGE_SIZE = 1000
    const allBlurhashRows: BlurhashRow[] = []
    let pageOffset = 0
    let hasMore = true

    while (hasMore) {
      const { data: pageData, error: pageError } = await supabase
        .from("images")
        .select("x_index,y_index,batch_index,category,width,height,blurhash")
        .eq("run_id", row.id)
        .order("y_index", { ascending: true })
        .order("x_index", { ascending: true })
        .order("batch_index", { ascending: true })
        .range(pageOffset, pageOffset + PAGE_SIZE - 1)

      if (pageError) {
        // blurhash is best-effort: stop pagination on error
        break
      }

      const rows = (pageData ?? []) as BlurhashRow[]
      allBlurhashRows.push(...rows)

      if (rows.length < PAGE_SIZE) {
        hasMore = false
      } else {
        pageOffset += PAGE_SIZE
      }
    }

    const blurhash_cells = allBlurhashRows

    return Response.json({
      x_columns,
      y_indexes,
      x_count,
      y_count,
      cells: {},
      blurhash_cells,
    })
  } catch {
    return Response.json(
      {
        error: "Failed to load run grid",
      },
      { status: 500 },
    )
  }
}
