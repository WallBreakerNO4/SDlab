import { createReadStream } from "node:fs"
import { stat } from "node:fs/promises"
import path from "node:path"
import { Readable } from "node:stream"

import { DEFAULT_COMFYUI_OUTPUTS_ROOT, discoverRunDirs } from "@/lib/comfyui-fs"
import {
  assertAllowedRunDir,
  assertSafeRelativeImagePath,
  resolvePathUnderRoot,
} from "@/lib/comfyui-path"
import type { RunDir } from "@/lib/comfyui-types"

export const runtime = "nodejs"

const CACHE_CONTROL = "public, max-age=86400"

type RouteContext = {
  params: Promise<{ runDir: string; imagePath: string[] }>
}

function isErrnoException(error: unknown): error is NodeJS.ErrnoException {
  return typeof error === "object" && error !== null && "code" in error
}

function contentTypeFromExt(imagePath: string): string {
  const ext = path.extname(imagePath).toLowerCase()

  if (ext === ".png") {
    return "image/png"
  }
  if (ext === ".jpg" || ext === ".jpeg") {
    return "image/jpeg"
  }
  if (ext === ".webp") {
    return "image/webp"
  }
  if (ext === ".gif") {
    return "image/gif"
  }

  return "application/octet-stream"
}

function isNotFoundError(error: unknown): boolean {
  if (error instanceof Error) {
    if (
      error.message === "runDir must not be empty" ||
      error.message === "Invalid runDir format" ||
      error.message === "runDir is not in allowlist" ||
      error.message === "imagePath must not be empty" ||
      error.message === "imagePath must not contain null bytes" ||
      error.message === "imagePath must not contain URL-encoded characters" ||
      error.message === "imagePath must not contain backslashes" ||
      error.message === "imagePath must be relative" ||
      error.message === "imagePath must not contain a drive letter" ||
      error.message === "imagePath must not contain empty segments" ||
      error.message === "imagePath must not contain dot segments" ||
      error.message === "imagePath escapes the expected relative scope" ||
      error.message === "Resolved path escapes root"
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
    const { runDir, imagePath } = await context.params
    const allowedRunDirs = new Set<RunDir>(await discoverRunDirs())
    const safeRunDir = assertAllowedRunDir(runDir, allowedRunDirs)

    const relativeImagePath = assertSafeRelativeImagePath(imagePath.join("/"))
    const runRoot = path.join(DEFAULT_COMFYUI_OUTPUTS_ROOT, safeRunDir)
    const absoluteImagePath = resolvePathUnderRoot(runRoot, relativeImagePath)

    const imageStat = await stat(absoluteImagePath)
    if (!imageStat.isFile()) {
      return Response.json({ error: "Image not found" }, { status: 404 })
    }

    const nodeStream = createReadStream(absoluteImagePath)
    const webStream = Readable.toWeb(nodeStream) as ReadableStream<Uint8Array>

    return new Response(webStream, {
      headers: {
        "Content-Type": contentTypeFromExt(relativeImagePath),
        "Cache-Control": CACHE_CONTROL,
      },
    })
  } catch (error) {
    if (isNotFoundError(error)) {
      return Response.json({ error: "Image not found" }, { status: 404 })
    }

    return Response.json({ error: "Failed to load image" }, { status: 500 })
  }
}
