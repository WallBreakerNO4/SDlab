import { isValidRunDir } from "@/lib/comfyui-types"
import { createClient } from "@/lib/supabase/server"

export const runtime = "nodejs"

type RouteContext = {
  params: Promise<{ runDir: string }>
}

function isNotFoundError(error: unknown): boolean {
  if (error instanceof Error) {
    if (
      error.message === "runDir must not be empty" ||
      error.message === "Invalid runDir format"
    ) {
      return true
    }
  }

  return false
}

function coerceNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value
  }

  if (typeof value === "string") {
    const trimmed = value.trim()
    if (!trimmed) return null

    const parsed = Number(trimmed)
    if (Number.isFinite(parsed)) return parsed
  }

  return null
}

export async function GET(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params
    if (!runDir) {
      throw new Error("runDir must not be empty")
    }

    if (!isValidRunDir(runDir)) {
      throw new Error("Invalid runDir format")
    }

    const supabase = await createClient()
    const { data, error } = await supabase
      .from("runs")
      .select("run_id, created_at, run_dir, run_json")
      .eq("run_dir", runDir)
      .maybeSingle()

    if (error) {
      throw error
    }

    if (!data) {
      return Response.json(
        { error: "Run not found" },
        {
          status: 404,
          headers: {
            "Cache-Control": "private, no-store",
          },
        },
      )
    }

    const selection =
      typeof data.run_json === "object" && data.run_json !== null
        ? (data.run_json as Record<string, unknown>).selection
        : null
    const totalCells =
      typeof selection === "object" && selection !== null
        ? coerceNumber((selection as Record<string, unknown>).total_cells)
        : null

    return Response.json({
      run: {
        run_id: data.run_id,
        created_at: data.created_at,
        run_dir: data.run_dir,
        selection: {
          total_cells: totalCells ?? 0,
        },
      },
    },
    {
      headers: {
        "Cache-Control": "private, no-store",
      },
    })
  } catch (error) {
    if (isNotFoundError(error)) {
      return Response.json(
        { error: "Run not found" },
        {
          status: 404,
          headers: {
            "Cache-Control": "private, no-store",
          },
        },
      )
    }

    return Response.json(
      {
        error: "Failed to load run",
      },
      {
        status: 500,
        headers: {
          "Cache-Control": "private, no-store",
        },
      },
    )
  }
}
