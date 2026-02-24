import { createReadStream } from "node:fs"
import { stat } from "node:fs/promises"
import path from "node:path"
import { Readable } from "node:stream"

import { getCloudflareContext } from "@opennextjs/cloudflare"

import { createClient } from "@/lib/supabase/server"

export const runtime = "nodejs"

const NO_STORE_HEADERS = {
  "Cache-Control": "private, no-store, no-cache, must-revalidate",
  Vary: "Cookie, Authorization",
  "X-Content-Type-Options": "nosniff",
} as const

type RouteContext = {
  params: Promise<{ variantId: string }>
}

type ByteRange = { start: number; end: number }

function toNonNegativeSafeInt(value: string): number | null {
  if (!/^[0-9]+$/.test(value)) return null
  const parsed = Number(value)
  if (!Number.isSafeInteger(parsed) || parsed < 0) return null
  return parsed
}

function parseSingleRangeHeader(
  rangeHeader: string | null,
  totalSize: number,
): { range: ByteRange | null; invalid: boolean } {
  if (!rangeHeader) return { range: null, invalid: false }

  const trimmed = rangeHeader.trim()
  if (!trimmed.startsWith("bytes=")) {
    return { range: null, invalid: true }
  }

  const spec = trimmed.slice("bytes=".length).trim()
  if (!spec || spec.includes(",")) {
    return { range: null, invalid: true }
  }

  const dashIndex = spec.indexOf("-")
  if (dashIndex === -1) {
    return { range: null, invalid: true }
  }

  const startPart = spec.slice(0, dashIndex).trim()
  const endPart = spec.slice(dashIndex + 1).trim()

  if (totalSize < 0 || !Number.isFinite(totalSize)) {
    return { range: null, invalid: true }
  }

  if (startPart === "") {
    const suffix = endPart ? toNonNegativeSafeInt(endPart) : null
    if (suffix === null || suffix <= 0) {
      return { range: null, invalid: true }
    }

    if (totalSize === 0) {
      return { range: null, invalid: true }
    }

    if (suffix >= totalSize) {
      return { range: { start: 0, end: totalSize - 1 }, invalid: false }
    }

    return {
      range: { start: totalSize - suffix, end: totalSize - 1 },
      invalid: false,
    }
  }

  const start = toNonNegativeSafeInt(startPart)
  if (start === null) {
    return { range: null, invalid: true }
  }

  if (totalSize === 0) {
    return { range: null, invalid: true }
  }

  if (start >= totalSize) {
    return { range: null, invalid: true }
  }

  if (endPart === "") {
    return { range: { start, end: totalSize - 1 }, invalid: false }
  }

  const endRaw = toNonNegativeSafeInt(endPart)
  if (endRaw === null) {
    return { range: null, invalid: true }
  }

  if (endRaw < start) {
    return { range: null, invalid: true }
  }

  return {
    range: { start, end: Math.min(endRaw, totalSize - 1) },
    invalid: false,
  }
}

function sanitizeFilename(raw: string): string {
  const trimmed = raw.trim()
  const base = trimmed ? trimmed : "download"
  const safe = base.replace(/[^a-zA-Z0-9._-]+/g, "_").replace(/^_+/, "")
  const normalized = safe || "download"
  return normalized.length > 128 ? normalized.slice(0, 128) : normalized
}

function contentDispositionForDownload(filename: string): string {
  return `attachment; filename="${sanitizeFilename(filename)}"`
}

function notFound(): Response {
  return new Response("Not found", { status: 404, headers: NO_STORE_HEADERS })
}

function unauthorized(): Response {
  return new Response("Unauthorized", { status: 401, headers: NO_STORE_HEADERS })
}

function notImplemented(): Response {
  return new Response("Not implemented", { status: 501, headers: NO_STORE_HEADERS })
}

function rangeNotSatisfiable(totalSize: number | null): Response {
  const headers = new Headers(NO_STORE_HEADERS)
  headers.set("Content-Type", "text/plain; charset=utf-8")
  if (typeof totalSize === "number" && Number.isFinite(totalSize) && totalSize >= 0) {
    headers.set("Content-Range", `bytes */${totalSize}`)
  }
  return new Response("Range Not Satisfiable", { status: 416, headers })
}

function responseHeaders(args: {
  contentType: string
  totalSize: number
  range: ByteRange | null
  downloadFilename: string | null
}): Headers {
  const headers = new Headers(NO_STORE_HEADERS)
  headers.set("Content-Type", args.contentType)
  headers.set("Accept-Ranges", "bytes")

  if (args.downloadFilename) {
    headers.set(
      "Content-Disposition",
      contentDispositionForDownload(args.downloadFilename),
    )
  }

  if (args.range) {
    const length = args.range.end - args.range.start + 1
    headers.set("Content-Range", `bytes ${args.range.start}-${args.range.end}/${args.totalSize}`)
    headers.set("Content-Length", String(length))
  } else {
    headers.set("Content-Length", String(args.totalSize))
  }

  return headers
}

function filenameFromR2Key(r2Key: string): string {
  const base = path.posix.basename(r2Key)
  return base || "download"
}

function resolveLocalObjectPath(args: {
  localRoot: string
  bucket: "private" | "public"
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

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { variantId } = await context.params
    if (!variantId) {
      return notFound()
    }

    const url = new URL(request.url)
    const isDownload = url.searchParams.get("download") === "1"

    const supabase = await createClient()
    const { data: userData } = await supabase.auth.getUser()
    if (!userData.user) {
      return unauthorized()
    }

    const { data: variant } = await supabase
      .from("image_variants")
      .select("bucket,r2_key,content_type")
      .eq("id", variantId)
      .maybeSingle()

    if (!variant) {
      return notFound()
    }

    if (variant.bucket !== "private") {
      return notFound()
    }

    const contentType =
      typeof variant.content_type === "string" && variant.content_type
        ? variant.content_type
        : "application/octet-stream"
    const downloadFilename = isDownload
      ? filenameFromR2Key(String(variant.r2_key ?? "download"))
      : null

    const localRoot = process.env.SDSL_LOCAL_R2_DIR
    const canUseLocal =
      typeof localRoot === "string" &&
      !!localRoot &&
      process.env.NODE_ENV !== "production"

    if (canUseLocal) {
      try {
        const localPath = resolveLocalObjectPath({
          localRoot,
          bucket: "private",
          r2Key: String(variant.r2_key),
        })
        if (!localPath) {
          return notFound()
        }

        const fileStat = await stat(localPath)
        if (!fileStat.isFile()) {
          return notFound()
        }

        const totalSize = Number(fileStat.size)
        const parsed = parseSingleRangeHeader(
          request.headers.get("range"),
          totalSize,
        )
        if (parsed.invalid) {
          return rangeNotSatisfiable(totalSize)
        }

        const nodeStream = parsed.range
          ? createReadStream(localPath, {
              start: parsed.range.start,
              end: parsed.range.end,
            })
          : createReadStream(localPath)
        const webStream = Readable.toWeb(nodeStream) as ReadableStream<Uint8Array>

        return new Response(webStream, {
          status: parsed.range ? 206 : 200,
          headers: responseHeaders({
            contentType,
            totalSize,
            range: parsed.range,
            downloadFilename,
          }),
        })
      } catch {
        return notFound()
      }
    }

    let r2Private: R2Bucket | undefined
    try {
      const cf = getCloudflareContext()
      r2Private = (cf?.env as unknown as { SDSL_R2_PRIVATE?: R2Bucket })
        ?.SDSL_R2_PRIVATE
    } catch {
      r2Private = undefined
    }

    if (!r2Private) {
      return notImplemented()
    }

    const head = await r2Private.head(String(variant.r2_key))
    if (!head) {
      return notFound()
    }

    const totalSize = Number(head.size)
    const parsed = parseSingleRangeHeader(
      request.headers.get("range"),
      totalSize,
    )
    if (parsed.invalid) {
      return rangeNotSatisfiable(totalSize)
    }

    const obj = parsed.range
      ? await r2Private.get(String(variant.r2_key), {
          range: {
            offset: parsed.range.start,
            length: parsed.range.end - parsed.range.start + 1,
          },
        })
      : await r2Private.get(String(variant.r2_key))

    if (!obj || !obj.body) {
      return notFound()
    }

    return new Response(obj.body, {
      status: parsed.range ? 206 : 200,
      headers: responseHeaders({
        contentType,
        totalSize,
        range: parsed.range,
        downloadFilename,
      }),
    })
  } catch {
    return new Response("Failed to load media", {
      status: 500,
      headers: NO_STORE_HEADERS,
    })
  }
}
