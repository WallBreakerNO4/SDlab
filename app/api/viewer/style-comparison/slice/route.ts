import { createRunMediaGrant, type ViewerVariant } from "@/lib/run-media-grant";
import {
  buildStyleComparisonPlacements,
  isStyleComparisonSliceResponse,
  normalizeStyleComparisonSliceRpcResult,
  ownsAllRequestedStyleKeys,
  parseStyleComparisonSliceBody,
  readViewerVariantFromCookie,
  type StyleComparisonSliceResponse,
} from "@/lib/style-comparison";
import { requireViewerForPreferenceWrite } from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import { isValidRunDir } from "@/lib/comfyui-types";

export const runtime = "nodejs";

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}
export async function POST(request: Request): Promise<Response> {
  const body = parseStyleComparisonSliceBody(await request.json().catch(() => null));
  if (!body || !body.run_dirs.every(isValidRunDir)) {
    return jsonError(400, "Invalid style comparison slice payload");
  }

  try {
    const supabase = await createSupabaseAuthClient();
    await requireViewerForPreferenceWrite(supabase);
    const viewerVariant: ViewerVariant = readViewerVariantFromCookie(
      request.headers.get("cookie"),
    );

    const { data, error } = await supabase.rpc("get_style_comparison_slice", {
      p_style_keys: body.style_keys,
      p_run_dirs: body.run_dirs,
      p_include_nsfw: viewerVariant === "auth_nsfw",
    });
    if (error) return jsonError(500, "Failed to load style comparison");

    const rpcResult = normalizeStyleComparisonSliceRpcResult(data, body);
    if (!rpcResult) return jsonError(500, "Failed to load style comparison");
    if (!ownsAllRequestedStyleKeys(rpcResult, body.style_keys)) {
      return jsonError(404, "Style favorite not found");
    }

    const placements = buildStyleComparisonPlacements(
      body.style_keys,
      rpcResult.placements,
    );

    const expiresAt = Math.floor(Date.now() / 1000) + 60 * 60 * 24;

    const payload: StyleComparisonSliceResponse = {
      placements,
      access: rpcResult.runs.map((row) => ({
        run_dir: row.run_dir,
        release_id: row.release_id,
        viewer_variant: viewerVariant,
        grant: createRunMediaGrant({
          sub: `release:${row.release_id}:${viewerVariant}`,
          run_dir: row.run_dir,
          release_id: row.release_id,
          viewer_variant: viewerVariant,
          media_access_version: row.media_access_version,
          exp: expiresAt,
        }),
        expires_at: expiresAt,
      })),
    };

    if (!isStyleComparisonSliceResponse(payload)) {
      return jsonError(500, "Failed to load style comparison");
    }
    return Response.json(payload);
  } catch (error) {
    if (error instanceof Error && error.message === "UNAUTHENTICATED") {
      return jsonError(401, "Authentication required");
    }
    return jsonError(500, "Failed to load style comparison");
  }
}
