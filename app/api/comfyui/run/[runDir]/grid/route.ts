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
      .select("id, run_dir, run_json")
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

    const xColumnsRaw = selection.x_columns
    const yIndexesRaw = selection.y_indexes

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

    // Fetch all blurhash + basic metadata for the entire run in one query.
    // This allows the frontend to show blurhash placeholders instantly
    // without waiting for per-row API calls.
    type BlurhashRow = {
      x_index: number
      y_index: number
      batch_index: number
      category: ImageCategory
      width: number | null
      height: number | null
      blurhash: string | null
    }

    const { data: blurhashData, error: blurhashError } = await supabase
      .from("images")
      .select("x_index,y_index,batch_index,category,width,height,blurhash")
      .eq("run_id", row.id)
      .order("y_index", { ascending: true })
      .order("x_index", { ascending: true })
      .order("batch_index", { ascending: true })

    // blurhash is best-effort: if the query fails, return grid without it
    const blurhash_cells: BlurhashRow[] = blurhashError ? [] : ((blurhashData ?? []) as BlurhashRow[])

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
