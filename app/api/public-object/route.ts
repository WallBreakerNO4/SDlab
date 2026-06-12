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

/**
 * 判断 key 是否对应不可变资源（包含 release_id 的版本化路径）。
 * 不可变资源可以设置长期缓存，因为新版本会使用不同的 release_id。
 */
function isImmutablePublicKey(key: string): boolean {
  // view/current.json 是可变的（指向当前发布版本）
  if (key.endsWith("/view/current.json")) return false;
  // 所有 /view/v2/{releaseId}/... 路径都包含版本号，内容不可变
  return /\/view\/v2\/[^/]+\//.test(key);
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

    // 条件请求：支持 If-None-Match，避免重复传输未变更的内容
    const ifNoneMatch = request.headers.get("If-None-Match");
    if (ifNoneMatch && ifNoneMatch === object.httpEtag) {
      const headers = new Headers();
      headers.set("ETag", object.httpEtag);
      headers.set("Cache-Control", "public, max-age=300");
      return new Response(null, { status: 304, headers });
    }

    const headers = new Headers();
    writeR2HttpMetadata(headers, object);
    // 不可变资源（含 release_id 的版本化路径）使用长期缓存
    // 可变资源（current.json）使用较短的缓存时间
    const cacheControl = isImmutablePublicKey(key)
      ? "public, max-age=31536000, immutable"
      : "public, max-age=300";
    headers.set("Cache-Control", cacheControl);
    headers.set("Content-Length", String(object.size));
    headers.set("ETag", object.httpEtag);
    return new Response(object.body, { status: 200, headers });
  } catch (error) {
    console.error("[api/public-object]", error);
    return jsonError(500, "Failed to load public object");
  }
}
