import { listRunSummaries } from "@/lib/comfyui-fs"
import type { RunSummary } from "@/lib/comfyui-types"

export const runtime = "nodejs"

function normalizeRunSummaries(runs: RunSummary[]): RunSummary[] {
  return runs.map((run) => ({
    run_dir: run.run_dir,
    run_id: run.run_id,
    created_at: run.created_at,
    x_count: run.x_count,
    y_count: run.y_count,
    total_cells: run.total_cells,
  }))
}

export async function GET(): Promise<Response> {
  try {
    const runs = await listRunSummaries()
    return Response.json(normalizeRunSummaries(runs))
  } catch {
    return Response.json([])
  }
}
