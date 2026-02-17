import { discoverRunDirs, loadRunGridIndex } from "@/lib/comfyui-fs"
import { assertAllowedRunDir } from "@/lib/comfyui-path"
import type { GridCell, GridCellKey, RunDir } from "@/lib/comfyui-types"

export const runtime = "nodejs"

type RouteContext = {
  params: Promise<{ runDir: string }>
}

type GridIndexCellPayload = {
  status: GridCell["status"]
  x_index: number
  y_index: number
  local_image_path: string | null
  local_image_paths?: string[]
  seed: number | null
  prompt_hash: string | null
  positive_prompt?: string
  generation_params?: {
    width: number | null
    height: number | null
    steps: number | null
    cfg: number | null
    sampler_name: string | null
  }
}

function isErrnoException(error: unknown): error is NodeJS.ErrnoException {
  return typeof error === "object" && error !== null && "code" in error
}

function isNotFoundError(error: unknown): boolean {
  if (error instanceof Error) {
    if (
      error.message === "runDir must not be empty" ||
      error.message === "Invalid runDir format" ||
      error.message === "runDir is not in allowlist"
    ) {
      return true
    }
  }

  return isErrnoException(error) && error.code === "ENOENT"
}

function toGridIndexCellPayload(cell: GridCell): GridIndexCellPayload {
  const payload: GridIndexCellPayload = {
    status: cell.status,
    x_index: cell.x_index,
    y_index: cell.y_index,
    local_image_path: cell.local_image_path,
    seed: cell.seed,
    prompt_hash: cell.prompt_hash,
  }

  if (cell.positive_prompt) {
    payload.positive_prompt = cell.positive_prompt
  }

  if (Array.isArray(cell.local_image_paths) && cell.local_image_paths.length > 0) {
    payload.local_image_paths = cell.local_image_paths
  }

  if (cell.generation_params) {
    payload.generation_params = {
      width: cell.generation_params.width,
      height: cell.generation_params.height,
      steps: cell.generation_params.steps,
      cfg: cell.generation_params.cfg,
      sampler_name: cell.generation_params.sampler_name,
    }
  }

  return payload
}

export async function GET(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params
    const allowedRunDirs = new Set<RunDir>(await discoverRunDirs())
    const safeRunDir = assertAllowedRunDir(runDir, allowedRunDirs)
    const { grid } = await loadRunGridIndex(safeRunDir)

    const cells = Object.fromEntries(
      Object.entries(grid.cells).map(([key, cell]) => [
        key as GridCellKey,
        toGridIndexCellPayload(cell),
      ]),
    )

    return Response.json({
      xLabels: grid.xLabels,
      yLabels: grid.yLabels,
      x_count: grid.x_count,
      y_count: grid.y_count,
      cells,
    })
  } catch (error) {
    if (isNotFoundError(error)) {
      return Response.json({ error: "Run not found" }, { status: 404 })
    }

    return Response.json(
      {
        error: "Failed to load run grid",
      },
      { status: 500 },
    )
  }
}
