import { listRunSummaries } from "@/lib/comfyui-fs"
import type { RunSummary } from "@/lib/comfyui-types"
import {
  createSupabaseServiceClient,
  SupabaseServiceConfigError,
} from "@/lib/supabase-server"

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
    createSupabaseServiceClient()
    const runs = await listRunSummaries()
    return Response.json(normalizeRunSummaries(runs))
  } catch (error: unknown) {
    if (error instanceof SupabaseServiceConfigError) {
      return Response.json(
        { error: error.message },
        {
          status: 500,
        },
      )
    }
    return Response.json([])
  }
}
