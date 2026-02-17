import { discoverRunDirs, loadRunGridIndex } from "@/lib/comfyui-fs"
import { assertAllowedRunDir } from "@/lib/comfyui-path"
import type { RunDir } from "@/lib/comfyui-types"

export const runtime = "nodejs"

type RouteContext = {
  params: Promise<{ runDir: string }>
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

export async function GET(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params
    const allowedRunDirs = new Set<RunDir>(await discoverRunDirs())
    const safeRunDir = assertAllowedRunDir(runDir, allowedRunDirs)
    const { runDetail, grid } = await loadRunGridIndex(safeRunDir)

    return Response.json({
      run: runDetail,
      xLabels: grid.xLabels,
      yLabels: grid.yLabels,
    })
  } catch (error) {
    if (isNotFoundError(error)) {
      return Response.json({ error: "Run not found" }, { status: 404 })
    }

    return Response.json(
      {
        error: "Failed to load run detail",
      },
      { status: 500 },
    )
  }
}
