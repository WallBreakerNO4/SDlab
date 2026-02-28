import { createHash } from "node:crypto"

import { AwsClient } from "aws4fetch"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

const CACHE_CONTROL = "private, max-age=0, no-cache"
const ALLOWED_PREFIX = "runs/"

type RouteContext = {
  params: Promise<{ r2Key: string[] }>
}

function hash12(input: string): string {
  return createHash("sha256").update(input).digest("hex").slice(0, 12)
}

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status })
}

function isLikelyEncodedSlash(segment: string): boolean {
  return /%2f/i.test(segment) || /%5c/i.test(segment)
}

function decodeAndValidateSegments(rawSegments: string[]): string[] {
  if (!Array.isArray(rawSegments) || rawSegments.length === 0) {
    throw new Error("invalid_r2_key")
  }

  const decoded: string[] = []
  for (const raw of rawSegments) {
    if (typeof raw !== "string" || raw.length === 0) {
      throw new Error("invalid_r2_key")
    }

    if (raw.includes("\u0000") || isLikelyEncodedSlash(raw)) {
      throw new Error("invalid_r2_key")
    }

    let part: string
    try {
      part = decodeURIComponent(raw)
    } catch {
      throw new Error("invalid_r2_key")
    }

    if (
      part.length === 0 ||
      part === "." ||
      part === ".." ||
      part.includes("/") ||
      part.includes("\\") ||
      part.includes("\u0000")
    ) {
      throw new Error("invalid_r2_key")
    }

    decoded.push(part)
  }

  return decoded
}

function encodePathSegments(segments: string[]): string {
  return segments.map((s) => encodeURIComponent(s)).join("/")
}

function validatePrivateImageKey(r2Key: string): void {
  if (!r2Key.startsWith(ALLOWED_PREFIX)) {
    throw new Error("not_found")
  }

  const fileName = r2Key.split("/").at(-1) ?? ""
  const fileLower = fileName.toLowerCase()

  const isOriginalPng = fileLower.startsWith("original_png") && fileLower.endsWith(".png")

  const isAllowedVariant =
    (fileLower.startsWith("display_") || fileLower.startsWith("thumb_")) &&
    (fileLower.endsWith(".avif") || fileLower.endsWith(".webp"))

  if (!isOriginalPng && !isAllowedVariant) {
    throw new Error("not_found")
  }
}

function getR2Config(): {
  endpoint: string
  accessKeyId: string
  secretAccessKey: string
  bucket: string
} {
  const endpoint = process.env.R2_ENDPOINT
  const accessKeyId = process.env.R2_ACCESS_KEY_ID
  const secretAccessKey = process.env.R2_SECRET_ACCESS_KEY
  const bucket = process.env.R2_PRIVATE_BUCKET

  if (!endpoint || !accessKeyId || !secretAccessKey || !bucket) {
    throw new Error("r2_not_configured")
  }

  return { endpoint, accessKeyId, secretAccessKey, bucket }
}

async function proxyPrivateObject(request: Request, context: RouteContext): Promise<Response> {
  const { r2Key: rawSegments } = await context.params

  let decodedSegments: string[]
  try {
    decodedSegments = decodeAndValidateSegments(rawSegments)
  } catch {
    return jsonError(400, "Invalid key")
  }

  const r2KeyDecoded = decodedSegments.join("/")

  try {
    validatePrivateImageKey(r2KeyDecoded)
  } catch (error) {
    if (error instanceof Error && error.message === "not_found") {
      return jsonError(404, "Not found")
    }
    return jsonError(400, "Invalid key")
  }

  const keyId = hash12(r2KeyDecoded)

  let cfg: ReturnType<typeof getR2Config>
  try {
    cfg = getR2Config()
  } catch {
    return jsonError(500, "R2 not configured")
  }

  let url: URL
  try {
    url = new URL(cfg.endpoint)
  } catch {
    return jsonError(500, "R2 not configured")
  }

  const encodedKey = encodePathSegments(decodedSegments)
  url.pathname = `/${encodeURIComponent(cfg.bucket)}/${encodedKey}`

  const aws = new AwsClient({
    accessKeyId: cfg.accessKeyId,
    secretAccessKey: cfg.secretAccessKey,
    service: "s3",
    region: "auto",
  })

  const method = request.method.toUpperCase()
  if (method !== "GET" && method !== "HEAD") {
    return new Response(null, { status: 405 })
  }

  try {
    const upstream = await aws.fetch(url.toString(), {
      method,
      headers: {
        ...(request.headers.get("range")
          ? { range: request.headers.get("range") as string }
          : {}),
      },
    })

    if (upstream.status === 404) {
      return jsonError(404, "Not found")
    }

    if (!upstream.ok) {
      console.error(`[r2-private] upstream error status=${upstream.status} key=${keyId}`)
      return jsonError(502, "Upstream error")
    }

    const contentType = upstream.headers.get("content-type") ?? "application/octet-stream"
    const contentLength = upstream.headers.get("content-length")
    const etag = upstream.headers.get("etag")
    const lastModified = upstream.headers.get("last-modified")
    const acceptRanges = upstream.headers.get("accept-ranges")

    const headers = new Headers()
    headers.set("Content-Type", contentType)
    headers.set("Cache-Control", CACHE_CONTROL)
    if (contentLength) headers.set("Content-Length", contentLength)
    if (etag) headers.set("ETag", etag)
    if (lastModified) headers.set("Last-Modified", lastModified)
    if (acceptRanges) headers.set("Accept-Ranges", acceptRanges)

    return new Response(method === "HEAD" ? null : upstream.body, {
      status: 200,
      headers,
    })
  } catch (error) {
    const errName = error instanceof Error ? error.name : "unknown"
    console.error(`[r2-private] request failed err=${errName} key=${keyId}`)
    return jsonError(502, "Upstream error")
  }
}

export async function GET(request: Request, context: RouteContext): Promise<Response> {
  return proxyPrivateObject(request, context)
}

export async function HEAD(request: Request, context: RouteContext): Promise<Response> {
  return proxyPrivateObject(request, context)
}
