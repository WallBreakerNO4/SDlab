import { getCloudflareContext } from "@opennextjs/cloudflare";

import { writeR2HttpMetadata } from "@/lib/r2-response";

export const runtime = "nodejs";

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

function isAllowedPublicObjectKey(key: string): boolean {
  if (!key.startsWith("runs/") || !key.endsWith(".json")) {
    return false;
  }

  if (key.endsWith("/view/current.json")) {
    return true;
  }

  if (/^runs\/[^/]+\/view\/v2\/[^/]+\/bootstrap\.sfw\.json$/.test(key)) {
    return true;
  }

  return /^runs\/[^/]+\/view\/v2\/[^/]+\/rows\/public\/\d+\.json$/.test(key);
}

export async function GET(request: Request): Promise<Response> {
  try {
    const url = new URL(request.url);
    const key = url.searchParams.get("key")?.trim();
    if (!key || !isAllowedPublicObjectKey(key)) {
      return jsonError(400, "Invalid public object request");
    }

    const { env } = getCloudflareContext();
    const object = await env.R2_PUBLIC_BUCKET.get(key);
    if (!object) {
      return jsonError(404, "Object not found");
    }

    const headers = new Headers();
    writeR2HttpMetadata(headers, object);
    headers.set("Cache-Control", "public, max-age=300");
    headers.set("Content-Length", String(object.size));
    headers.set("ETag", object.httpEtag);
    return new Response(object.body, { status: 200, headers });
  } catch (error) {
    console.error("[api/public-object]", error);
    return jsonError(500, "Failed to load public object");
  }
}
