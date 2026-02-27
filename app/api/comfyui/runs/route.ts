import type { RunSummary } from "@/lib/comfyui-types"
import {
  createSupabaseServiceClient,
  SupabaseServiceConfigError,
} from "@/lib/supabase-server"
import type { JsonObject, JsonValue, SupabaseRunRow } from "@/lib/supabase-types"


export const runtime = "nodejs"

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

function getNonNegativeInteger(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    return null
  }
  return value
}

function getArrayLength(value: unknown): number | null {
  return Array.isArray(value) ? value.length : null
}


export async function GET(): Promise<Response> {
  try {
    const supabase = createSupabaseServiceClient()
    const { data, error } = await supabase
      .from("runs")
      .select("run_dir, created_at, run_json")
      .order("created_at", { ascending: false })

    if (error) {
      return Response.json(
        {
          error: "Failed to load runs",
        },
        { status: 500 },
      )
    }

    const rows = ((data as SupabaseRunRow[] | null) ?? [])
    const runs: RunSummary[] = rows.map((row) => {
      const runJson = asJsonObject(row.run_json)
      const runIdFromJson = runJson ? getNonEmptyString(runJson.run_id) : null
      const selection = runJson ? asJsonObject(runJson.selection) : null

      const x_count =
        getNonNegativeInteger(selection?.x_count) ??
        getArrayLength(selection?.x_columns) ??
        getArrayLength(selection?.x_indexes) ??
        0

      const y_count =
        getNonNegativeInteger(selection?.y_count) ??
        getArrayLength(selection?.y_indexes) ??
        0

      const total_cells =
        getNonNegativeInteger(selection?.total_cells) ?? x_count * y_count

      return {
        run_id: runIdFromJson ?? row.run_dir,
        created_at: row.created_at,
        run_dir: row.run_dir,
        x_count,
        y_count,
        total_cells,
      }
    })

    return Response.json(runs)
  } catch (error: unknown) {
    if (error instanceof SupabaseServiceConfigError) {
      return Response.json(
        { error: error.message },
        {
          status: 500,
        },
      )
    }

    return Response.json(
      {
        error: "Failed to load runs",
      },
      { status: 500 },
    )
  }

}
