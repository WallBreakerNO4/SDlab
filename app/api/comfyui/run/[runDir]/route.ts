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

function getNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function parseModelMetadata(rawModel: unknown) {
  const model = asJsonObject(rawModel as JsonValue)
  if (!model) return null

  const description = asJsonObject(model.description as JsonValue)
  const links = asJsonObject(model.links as JsonValue)

  return {
    name: getNonEmptyString(model.name),
    description: description ? {
      zh: getNonEmptyString(description.zh),
      en: getNonEmptyString(description.en),
    } : null,
    links: links ? {
      homepage: getNonEmptyString(links.homepage),
      huggingface: getNonEmptyString(links.huggingface),
      civitai: getNonEmptyString(links.civitai),
    } : null,
  }
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
      .select("run_id, run_dir, created_at, x_columns, y_indexes, x_count, y_count, total_cells, run_json")
      .eq("run_dir", runDir)
      .maybeSingle()

    if (error) {
      return Response.json(
        {
          error: "Failed to load run detail",
        },
        { status: 500 },
      )
    }

    const row = data as SupabaseRunRow | null
    if (!row) {
      return Response.json({ error: "Run not found" }, { status: 404 })
    }

    const runJson = asJsonObject(row.run_json)
    const runId = getNonEmptyString(row.run_id) ?? (runJson ? getNonEmptyString(runJson.run_id) : null)
    const selection = runJson ? asJsonObject(runJson.selection as JsonValue) : null
    const modelMetadata = runJson ? parseModelMetadata(runJson.model) : null

    const xColumnsRaw = Array.isArray(row.x_columns) ? row.x_columns : selection?.x_columns
    const yIndexesRaw = Array.isArray(row.y_indexes) ? row.y_indexes : selection?.y_indexes

    const x_columns: JsonObject[] = Array.isArray(xColumnsRaw)
      ? xColumnsRaw
          .map((item) => asJsonObject(item as JsonValue))
          .filter((item): item is JsonObject => item !== null)
      : []

    const y_indexes: number[] = Array.isArray(yIndexesRaw)
      ? yIndexesRaw.filter((item): item is number => typeof item === "number")
      : []

    const totalCellsFromRow = getNumber(row.total_cells)
    const totalCellsFromJson = getNumber(selection?.total_cells)
    const total_cells = totalCellsFromRow ?? totalCellsFromJson ?? x_columns.length * y_indexes.length

    if (!runId) {
      return Response.json(
        {
          error: "Failed to load run detail",
        },
        { status: 500 },
      )
    }

    const xLabels = x_columns.map((col, index) => {
      const desc = asJsonObject(col.description as JsonValue)
      const zh = desc ? getNonEmptyString(desc.zh) : null
      return zh ?? `X${index}`
    })

    const yLabels = y_indexes.map((yIndex) => `Y${yIndex}`)

    return Response.json({
      run: {
        run_id: runId,
        created_at: row.created_at,
        run_dir: row.run_dir,
        selection: {
          total_cells,
        },
        model: modelMetadata,
      },
      xLabels,
      yLabels,
      x_columns,
      y_indexes,
    })
  } catch {
    return Response.json(
      {
        error: "Failed to load run detail",
      },
      { status: 500 },
    )
  }
}
