import { getCloudflareContext } from "@opennextjs/cloudflare";

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
  if (fileName === "display_webp.webp" || fileName === "display_avif.avif") {
    return false;
  }

  return (
    fileName.startsWith("display_") ||
    fileName.startsWith("thumb_")
  );
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

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("Cache-Control", "private, max-age=300");
    headers.set("Content-Length", String(object.size));
    headers.set("ETag", object.httpEtag);
    return new Response(object.body, { status: 200, headers });
  } catch {
    return jsonError(500, "Failed to load private object");
  }
}
