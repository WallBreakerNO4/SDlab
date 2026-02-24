import { isValidRunDir } from "@/lib/comfyui-types"
import { createClient } from "@/lib/supabase/server"

export const runtime = "nodejs"

type RouteContext = {
  params: Promise<{ runDir: string }>
}

type GridMetaRow = {
  x_columns?: unknown
  y_labels?: unknown
  x_count?: unknown
  y_count?: unknown
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

function normalizeYLabels(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }

  const labels: string[] = []
  for (const item of value) {
    labels.push(typeof item === "string" ? item : "")
  }

  return labels
}

function normalizeXColumns(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) {
    return []
  }

  const columns: Array<Record<string, unknown>> = []
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue
    }

    columns.push(item as Record<string, unknown>)
  }

  return columns
}

export async function GET(
  _request: Request,
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

    const supabase = await createClient()
    const { data, error } = await supabase.rpc("get_run_grid_meta", {
      target_run_dir: runDir,
    })

    if (error) {
      return Response.json(
        { error: "Failed to load grid meta" },
        { status: 500, headers: NO_STORE_HEADERS },
      )
    }

    const row = Array.isArray(data) && data.length > 0 ? (data[0] as GridMetaRow) : null
    if (!row) {
      return Response.json(
        { error: "Run not found" },
        { status: 404, headers: NO_STORE_HEADERS },
      )
    }

    const xColumns = normalizeXColumns(row.x_columns)
    const yLabels = normalizeYLabels(row.y_labels)
    const x_count = toFiniteNumber(row.x_count) ?? xColumns.length
    const y_count = toFiniteNumber(row.y_count) ?? yLabels.length

    return Response.json(
      {
        xColumns,
        yLabels,
        x_count,
        y_count,
      },
      { headers: NO_STORE_HEADERS },
    )
  } catch {
    return Response.json(
      { error: "Failed to load grid meta" },
      { status: 500, headers: NO_STORE_HEADERS },
    )
  }
}
