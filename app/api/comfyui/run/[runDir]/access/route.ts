import { isValidRunDir } from "@/lib/comfyui-types";
import {
  createRunMediaGrant,
  type ViewerVariant,
} from "@/lib/run-media-grant";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import { getPublicEnv } from "@/lib/env/public";
import {
  DEFAULT_SHOW_NSFW,
  parseViewerShowNsfwCookieValue,
  VIEWER_SHOW_NSFW_COOKIE,
} from "@/lib/viewer-nsfw-cookie";
import { unstable_cache } from "next/cache";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ runDir: string }>;
};

type RunViewIndexRow = {
  release_id: string | null;
  media_access_version: number | null;
};

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

function readViewerVariant(request: Request): ViewerVariant {
  const rawCookie = request.headers.get("cookie");
  const cookieEntry = rawCookie
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${VIEWER_SHOW_NSFW_COOKIE}=`));
  const cookieValue = cookieEntry?.slice(VIEWER_SHOW_NSFW_COOKIE.length + 1);
  const showNsfw =
    cookieValue === undefined
      ? DEFAULT_SHOW_NSFW
      : parseViewerShowNsfwCookieValue(cookieValue);
  return showNsfw ? "auth_nsfw" : "auth_sfw";
}

/**
 * 缓存的 run_view_index 查询。
 * release_id 和 media_access_version 对所有用户相同，因此使用匿名客户端，
 * 独立于用户认证进行缓存（5 分钟 TTL）。
 */
const getRunViewIndex = unstable_cache(
  async (runDir: string): Promise<RunViewIndexRow | null> => {
    const { supabaseUrl, supabasePublishableKey } = getPublicEnv();
    const supabase = createClient(supabaseUrl, supabasePublishableKey, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const { data, error } = await supabase
      .from("run_view_index")
      .select("release_id,media_access_version")
      .eq("run_dir", runDir)
      .maybeSingle();

    if (error || !data) return null;
    return data as RunViewIndexRow;
  },
  ["run-view-index"],
  { revalidate: 300, tags: ["run-view-index"] },
);

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params;
    if (!isValidRunDir(runDir)) {
      return jsonError(404, "Run not found");
    }

    const supabase = await createSupabaseAuthClient();
    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError) {
      return jsonError(401, "Authentication required");
    }
    if (!user) {
      return jsonError(401, "Authentication required");
    }

    // 使用缓存的 run_view_index 查询（独立于用户认证）
    const row = await getRunViewIndex(runDir);
    if (!row?.release_id || typeof row.media_access_version !== "number") {
      return jsonError(404, "Run not found");
    }

    const viewerVariant = readViewerVariant(request);
    // grant TTL 从 15 分钟延长到 24 小时：所有用户查看同一份 release 的图片，
    // 无需每用户独立短时授权。长 TTL 让 CDN 缓存（s-maxage=82800）始终先于
    // grant 过期失效，不违反 TTL 兑底。
    const expiresAt = Math.floor(Date.now() / 1000) + 60 * 60 * 24; // 24 小时
    // sub 从 user.id 改为 release 级共享：同一 release 的所有登录用户拿到
    // 相同 grant → URL 完全一致 → CDN 边缘缓存可跨用户复用。
    // 安全性不降：verifyRunMediaGrant 本就不校验 sub 与请求者 user.id 是否匹配，
    // 只验 HMAC 签名 + exp。爬虫仍需登录才能拿 grant。
    const grant = createRunMediaGrant({
      sub: `release:${row.release_id}:${viewerVariant}`,
      run_dir: runDir,
      release_id: row.release_id,
      viewer_variant: viewerVariant,
      media_access_version: row.media_access_version,
      exp: expiresAt,
    });

    return Response.json({
      run_dir: runDir,
      release_id: row.release_id,
      viewer_variant: viewerVariant,
      grant,
      expires_at: expiresAt,
    });
  } catch (error) {
    console.error("[api/comfyui/run/access]", error);
    return jsonError(
      500,
      error instanceof Error ? error.message : "Failed to load run access",
    );
  }
}
