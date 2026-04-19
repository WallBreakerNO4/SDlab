import { isValidRunDir } from "@/lib/comfyui-types";
import {
  createRunMediaGrant,
  type ViewerVariant,
} from "@/lib/run-media-grant";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import {
  DEFAULT_SHOW_NSFW,
  parseViewerShowNsfwCookieValue,
  VIEWER_SHOW_NSFW_COOKIE,
} from "@/lib/viewer-nsfw-cookie";

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

    const { data, error } = await supabase
      .from("run_view_index")
      .select("release_id,media_access_version")
      .eq("run_dir", runDir)
      .maybeSingle();

    if (error) {
      return jsonError(500, "Failed to load run access");
    }

    const row = data as RunViewIndexRow | null;
    if (!row?.release_id || typeof row.media_access_version !== "number") {
      return jsonError(404, "Run not found");
    }

    const viewerVariant = readViewerVariant(request);
    const grant = createRunMediaGrant({
      sub: user.id,
      run_dir: runDir,
      release_id: row.release_id,
      viewer_variant: viewerVariant,
      media_access_version: row.media_access_version,
      exp: Math.floor(Date.now() / 1000) + 60 * 15,
    });

    return Response.json({
      run_dir: runDir,
      release_id: row.release_id,
      viewer_variant: viewerVariant,
      grant,
    });
  } catch {
    return jsonError(500, "Failed to load run access");
  }
}
