import { getCloudflareContext } from "@opennextjs/cloudflare";

import { writeR2HttpMetadata } from "@/lib/r2-response";
import { verifyRunMediaGrant } from "@/lib/run-media-grant";
import { buildPrivateObjectCacheUrl } from "@/lib/style-comparison";

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

    const { env, ctx } = getCloudflareContext();
    const cacheStorage = (globalThis as typeof globalThis & {
      caches?: { default?: Cache };
    }).caches;
    const edgeCache = cacheStorage?.default;
    const cacheRequest = new Request(buildPrivateObjectCacheUrl(request.url));

    // Authorization is deliberately completed before this lookup. The cache key
    // omits the grant, but it can only be reached by a request with a valid grant.
    if (edgeCache) {
      const cached = await edgeCache.match(cacheRequest);
      if (cached) {
        const ifNoneMatch = request.headers.get("If-None-Match");
        const cachedEtag = cached.headers.get("ETag");
        if (ifNoneMatch && cachedEtag && ifNoneMatch === cachedEtag) {
          const headers = new Headers();
          headers.set("ETag", cachedEtag);
          return new Response(null, { status: 304, headers });
        }
        return cached;
      }
    }

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
    // 启用边缘缓存：s-maxage=82800 (23 小时) < grant TTL 24 小时，
    // 保证 CDN 缓存先于 grant 过期失效，不违反 TTL 兑底。
    // grant 共享化后同一 release 的所有用户 URL 一致，边缘缓存跨用户复用。
    // max-age 较短让浏览器在 SWR 窗口内主动重验证，避免持有过于陈旧的图。
    headers.set(
      "Cache-Control",
      isJson
        ? "max-age=300, s-maxage=82800"
        : "max-age=3600, s-maxage=82800, stale-while-revalidate=86400",
    );
    headers.set("Content-Length", String(object.size));
    headers.set("ETag", object.httpEtag);
    const response = new Response(object.body, { status: 200, headers });
    if (edgeCache) {
      // Cache API writes are intentionally detached from the response path.
      ctx.waitUntil(edgeCache.put(cacheRequest, response.clone()));
    }
    return response;
  } catch (error) {
    console.error("[api/private-object]", error);
    return jsonError(500, "Failed to load private object");
  }
}
