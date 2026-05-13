import { getCloudflareContext } from "@opennextjs/cloudflare";

import { writeR2HttpMetadata } from "@/lib/r2-response";
import { verifyRunMediaGrant } from "@/lib/run-media-grant";

export const runtime = "nodejs";

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

function isAllowedPrivateObjectKey(
  key: string,
  claims: ReturnType<typeof verifyRunMediaGrant>,
): boolean {
  if (!claims) {
    return false;
  }

  if (!key.startsWith(`runs/${claims.run_dir}/`)) {
    return false;
  }

  if (
    key.startsWith(
      `runs/${claims.run_dir}/view/v2/${claims.release_id}/rows/${claims.viewer_variant}/`,
    )
  ) {
    return key.endsWith(".json");
  }

  if (
    claims.viewer_variant === "auth_nsfw" &&
    key === `runs/${claims.run_dir}/view/v2/${claims.release_id}/bootstrap.nsfw.json`
  ) {
    return true;
  }

  const fileName = key.split("/").pop() ?? "";
  const isAllowedVariantFile =
    (fileName.startsWith("display_") || fileName.startsWith("thumb_")) &&
    (fileName.endsWith(".webp") || fileName.endsWith(".avif"));
  return isAllowedVariantFile;
}

export async function GET(request: Request): Promise<Response> {
  try {
    const url = new URL(request.url);
    const key = url.searchParams.get("key")?.trim();
    const grant = url.searchParams.get("grant")?.trim();
    if (!key || !grant) {
      return jsonError(400, "Invalid private object request");
    }

    const claims = verifyRunMediaGrant(grant);
    if (!isAllowedPrivateObjectKey(key, claims)) {
      return jsonError(403, "Access denied");
    }

    const { env } = getCloudflareContext();
    const object = await env.R2_PRIVATE_BUCKET.get(key);
    if (!object) {
      return jsonError(404, "Object not found");
    }

    const ifNoneMatch = request.headers.get("If-None-Match");
    if (ifNoneMatch && ifNoneMatch === object.httpEtag) {
      const headers = new Headers();
      headers.set("ETag", object.httpEtag);
      return new Response(null, { status: 304, headers });
    }

    const headers = new Headers();
    writeR2HttpMetadata(headers, object);
    const isJson = key.endsWith(".json");
    headers.set(
      "Cache-Control",
      isJson ? "private, max-age=300" : "private, max-age=0, no-cache",
    );
    headers.set("Content-Length", String(object.size));
    headers.set("ETag", object.httpEtag);
    return new Response(object.body, { status: 200, headers });
  } catch (error) {
    console.error("[api/private-object]", error);
    return jsonError(500, "Failed to load private object");
  }
}
