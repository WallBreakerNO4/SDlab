import { createHash } from "node:crypto";

import { getCloudflareContext } from "@opennextjs/cloudflare";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CACHE_CONTROL = "private, max-age=0, no-cache";
const ALLOWED_PREFIX = "runs/";

type RouteContext = {
  params: Promise<{ r2Key: string[] }>;
};

function hash12(input: string): string {
  return createHash("sha256").update(input).digest("hex").slice(0, 12);
}

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

function isLikelyEncodedSlash(segment: string): boolean {
  return /%2f/i.test(segment) || /%5c/i.test(segment);
}

function decodeAndValidateSegments(rawSegments: string[]): string[] {
  if (!Array.isArray(rawSegments) || rawSegments.length === 0) {
    throw new Error("invalid_r2_key");
  }

  const decoded: string[] = [];
  for (const raw of rawSegments) {
    if (typeof raw !== "string" || raw.length === 0) {
      throw new Error("invalid_r2_key");
    }

    if (raw.includes("\u0000") || isLikelyEncodedSlash(raw)) {
      throw new Error("invalid_r2_key");
    }

    let part: string;
    try {
      part = decodeURIComponent(raw);
    } catch {
      throw new Error("invalid_r2_key");
    }

    if (
      part.length === 0 ||
      part === "." ||
      part === ".." ||
      part.includes("/") ||
      part.includes("\\") ||
      part.includes("\u0000")
    ) {
      throw new Error("invalid_r2_key");
    }

    decoded.push(part);
  }

  return decoded;
}

function validatePrivateImageKey(r2Key: string): void {
  if (!r2Key.startsWith(ALLOWED_PREFIX)) {
    throw new Error("not_found");
  }

  const fileName = r2Key.split("/").at(-1) ?? "";
  const fileLower = fileName.toLowerCase();

  const isAllowedVariant =
    (fileLower.startsWith("display_") || fileLower.startsWith("thumb_")) &&
    (fileLower.endsWith(".avif") || fileLower.endsWith(".webp"));

  if (!isAllowedVariant) {
    throw new Error("not_found");
  }
}

async function proxyPrivateObject(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  // --- Auth check: private images require authenticated user ---
  try {
    const supabase = await createSupabaseAuthClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      return jsonError(401, "Authentication required");
    }
  } catch {
    return jsonError(401, "Authentication required");
  }

  const { r2Key: rawSegments } = await context.params;

  let decodedSegments: string[];
  try {
    decodedSegments = decodeAndValidateSegments(rawSegments);
  } catch {
    return jsonError(400, "Invalid key");
  }

  const r2KeyDecoded = decodedSegments.join("/");

  try {
    validatePrivateImageKey(r2KeyDecoded);
  } catch (error) {
    if (error instanceof Error && error.message === "not_found") {
      return jsonError(404, "Not found");
    }
    return jsonError(400, "Invalid key");
  }

  const keyId = hash12(r2KeyDecoded);

  const method = request.method.toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    return new Response(null, { status: 405 });
  }

  try {
    const { env } = getCloudflareContext();
    const bucket = env.R2_PRIVATE_BUCKET;

    if (method === "HEAD") {
      const head = await bucket.head(r2KeyDecoded);
      if (!head) {
        return jsonError(404, "Not found");
      }

      const headers = new Headers();
      head.writeHttpMetadata(headers);
      headers.set("ETag", head.httpEtag);
      headers.set("Cache-Control", CACHE_CONTROL);
      headers.set("Content-Length", String(head.size));

      return new Response(null, { status: 200, headers });
    }

    const object = await bucket.get(r2KeyDecoded, {
      range: request.headers,
      onlyIf: request.headers,
    });

    if (object === null) {
      return jsonError(404, "Not found");
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("ETag", object.httpEtag);
    headers.set("Cache-Control", CACHE_CONTROL);

    // R2 conditional request failed (e.g. If-None-Match matched) — no body
    if (!("body" in object)) {
      return new Response(null, { status: 304, headers });
    }

    const status = request.headers.has("range") ? 206 : 200;
    headers.set("Content-Length", String(object.size));

    return new Response(object.body, { status, headers });
  } catch (error) {
    const errName = error instanceof Error ? error.name : "unknown";
    console.error(`[r2-private] request failed err=${errName} key=${keyId}`);
    return jsonError(502, "Upstream error");
  }
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  return proxyPrivateObject(request, context);
}

export async function HEAD(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  return proxyPrivateObject(request, context);
}
