import { createReadStream } from "node:fs"
import { stat } from "node:fs/promises"
import path from "node:path"
import { Readable } from "node:stream"

import { getCloudflareContext } from "@opennextjs/cloudflare"

export const runtime = "nodejs"

const CACHE_CONTROL = "public, max-age=31536000, immutable"

type RouteContext = {
  params: Promise<{ r2Key: string[] }>
}

function notFound(): Response {
  return new Response("Not found", { status: 404 })
}

function unsupported(): Response {
  return new Response("Unsupported media type", { status: 415 })
}

function notImplemented(): Response {
  return new Response("Not implemented", { status: 501 })
}

function isValidPathSegments(segments: string[]): boolean {
  if (segments.length === 0) return false

  for (const seg of segments) {
    if (!seg) return false
    if (seg === "." || seg === "..") return false
    if (seg.includes("\\")) return false
    if (seg.includes("\u0000")) return false
  }

  return true
}

function isUrlEncodedPathname(request: Request): boolean {
  const pathname = new URL(request.url).pathname
  return pathname.includes("%")
}

function contentTypeFromExt(r2Key: string): string | null {
  const ext = path.posix.extname(r2Key).toLowerCase()
  if (ext === ".avif") return "image/avif"
  if (ext === ".webp") return "image/webp"
  if (ext === ".png") return "image/png"
  if (ext === ".json") return "application/json; charset=utf-8"
  return null
}

function resolveLocalObjectPath(args: {
  localRoot: string
  bucket: "public"
  r2Key: string
}): string | null {
  const bucketRoot = path.resolve(args.localRoot, args.bucket)
  const filePath = path.resolve(bucketRoot, args.r2Key)

  const expectedPrefix = bucketRoot.endsWith(path.sep)
    ? bucketRoot
    : `${bucketRoot}${path.sep}`
  if (!filePath.startsWith(expectedPrefix)) {
    return null
  }

  return filePath
}

function responseHeaders(contentType: string): Headers {
  const headers = new Headers()
  headers.set("Content-Type", contentType)
  headers.set("Cache-Control", CACHE_CONTROL)
  headers.set("X-Content-Type-Options", "nosniff")
  return headers
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { r2Key: r2KeySegments } = await context.params

    if (!isValidPathSegments(r2KeySegments)) {
      return notFound()
    }

    if (isUrlEncodedPathname(request)) {
      return notFound()
    }

    const r2Key = r2KeySegments.join("/")
    const contentType = contentTypeFromExt(r2Key)
    if (!contentType) {
      return unsupported()
    }

    const localRoot = process.env.SDSL_LOCAL_R2_DIR
    const canUseLocal =
      typeof localRoot === "string" &&
      !!localRoot &&
      process.env.NODE_ENV !== "production"

    if (canUseLocal) {
      try {
        const localPath = resolveLocalObjectPath({
          localRoot,
          bucket: "public",
          r2Key,
        })
        if (!localPath) {
          return notFound()
        }

        const fileStat = await stat(localPath)
        if (!fileStat.isFile()) {
          return notFound()
        }

        const nodeStream = createReadStream(localPath)
        const webStream = Readable.toWeb(nodeStream) as ReadableStream<Uint8Array>
        return new Response(webStream, {
          headers: responseHeaders(contentType),
        })
      } catch {
        return notFound()
      }
    }

    let r2Public: R2Bucket | undefined
    try {
      const cf = getCloudflareContext()
      r2Public = (cf?.env as unknown as { SDSL_R2_PUBLIC?: R2Bucket })
        ?.SDSL_R2_PUBLIC
    } catch {
      r2Public = undefined
    }

    if (!r2Public) {
      return notImplemented()
    }

    const obj = await r2Public.get(r2Key)
    if (!obj || !obj.body) {
      return notFound()
    }

    return new Response(obj.body, {
      headers: responseHeaders(contentType),
    })
  } catch {
    return new Response("Failed to load media", { status: 500 })
  }
}
