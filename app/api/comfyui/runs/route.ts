import type { RunSummary } from "@/lib/comfyui-types"
import { createClient } from "@/lib/supabase/server"

export const runtime = "nodejs"

function normalizeRunSummaries(data: unknown): RunSummary[] {
  if (!Array.isArray(data)) {
    return []
  }

  const runs: RunSummary[] = []

  for (const row of data) {
    if (!row || typeof row !== "object") {
      continue
    }

    const record = row as Record<string, unknown>

    const run_dir = typeof record.run_dir === "string" ? record.run_dir : null
    const created_at =
      typeof record.created_at === "string" ? record.created_at : null
    const x_count = typeof record.x_count === "number" ? record.x_count : null
    const y_count = typeof record.y_count === "number" ? record.y_count : null
    const total_cells =
      typeof record.total_cells === "number" ? record.total_cells : null

    if (
      run_dir === null ||
      created_at === null ||
      x_count === null ||
      y_count === null ||
      total_cells === null
    ) {
      continue
    }

    const run_id =
      typeof record.run_id === "string" && record.run_id
        ? record.run_id
        : run_dir

    runs.push({
      run_dir,
      run_id,
      created_at,
      x_count,
      y_count,
      total_cells,
    })
  }

  return runs
}

function parseLimitCount(value: string | null): number {
  if (!value) {
    return 50
  }

  const parsed = Number.parseInt(value, 10)

  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 50
  }

  return Math.min(parsed, 200)
}

export async function GET(request: Request): Promise<Response> {
  const headers = {
    "Cache-Control": "private, no-store",
  }

  try {
    const url = new URL(request.url)
    const limit_count = parseLimitCount(url.searchParams.get("limit_count"))
    const cursor_created_at = url.searchParams.get("cursor_created_at")
    const cursor_run_dir = url.searchParams.get("cursor_run_dir")

    const supabase = await createClient()
    const { data, error } = await supabase.rpc("get_run_summaries", {
      limit_count,
      cursor_created_at,
      cursor_run_dir,
    })

    if (error) {
      return Response.json([], { headers })
    }

    return Response.json(normalizeRunSummaries(data), { headers })
  } catch {
    return Response.json([], { headers })
  }
}
