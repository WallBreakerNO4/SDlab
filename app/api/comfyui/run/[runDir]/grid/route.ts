import { isValidRunDir } from "@/lib/comfyui-types"
import { createSupabaseAuthClient } from "@/lib/supabase-auth"
import type { JsonObject, JsonValue, SupabaseRunRow } from "@/lib/supabase-types"

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
      .select("run_dir, run_json")
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

    const row = data as SupabaseRunRow | null
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

    return Response.json({
      x_columns,
      y_indexes,
      x_count,
      y_count,
      cells: {},
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
