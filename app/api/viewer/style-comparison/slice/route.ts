import { createRunMediaGrant, type ViewerVariant } from "@/lib/run-media-grant";
import {
  isStyleComparisonSliceResponse,
  parseStyleComparisonSliceBody,
  readViewerVariantFromCookie,
  type StyleComparisonSliceResponse,
} from "@/lib/style-comparison";
import { isStyleKey } from "@/lib/style-favorites";
import { requireViewerForPreferenceWrite } from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import { isValidRunDir } from "@/lib/comfyui-types";

export const runtime = "nodejs";

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

type RunViewRow = {
  run_dir: string;
  release_id: string;
  media_access_version: number;
};

export async function POST(request: Request): Promise<Response> {
  const body = parseStyleComparisonSliceBody(await request.json().catch(() => null));
  if (!body || !body.run_dirs.every(isValidRunDir)) {
    return jsonError(400, "Invalid style comparison slice payload");
  }

  try {
    const supabase = await createSupabaseAuthClient();
    await requireViewerForPreferenceWrite(supabase);

    const { data: favoriteData, error: favoriteError } = await supabase
      .from("user_style_favorites")
      .select("style_key")
      .in("style_key", body.style_keys);
    if (favoriteError) return jsonError(500, "Failed to load style comparison");

    const ownedKeys = new Set(
      (favoriteData ?? []).filter(
        (row): row is { style_key: string } => isRecord(row) && isStyleKey(row.style_key),
      ).map((row) => row.style_key),
    );
    if (ownedKeys.size !== body.style_keys.length) {
      return jsonError(404, "Style favorite not found");
    }

    const { data: placementData, error: placementError } = await supabase
      .from("run_style_items")
      .select("run_dir,style_key,y_index")
      .in("style_key", body.style_keys)
      .in("run_dir", body.run_dirs);
    if (placementError) return jsonError(500, "Failed to load style comparison");

    const placements: Record<string, { run_dir: string; y_index: number }[]> = {};
    for (const styleKey of body.style_keys) placements[styleKey] = [];
    for (const row of placementData ?? []) {
      if (
        !isRecord(row) ||
        !isStyleKey(row.style_key) ||
        typeof row.run_dir !== "string" ||
        !isValidRunDir(row.run_dir) ||
        typeof row.y_index !== "number" ||
        !Number.isInteger(row.y_index) ||
        row.y_index < 0 ||
        !placements[row.style_key]
      ) continue;
      placements[row.style_key].push({ run_dir: row.run_dir, y_index: row.y_index });
    }
    for (const styleKey of body.style_keys) {
      placements[styleKey].sort((a, b) => a.run_dir.localeCompare(b.run_dir));
    }

    const { data: viewData, error: viewError } = await supabase
      .from("run_view_index")
      .select("run_dir,release_id,media_access_version")
      .in("run_dir", body.run_dirs);
    if (viewError) return jsonError(500, "Failed to load style comparison");

    const viewerVariant: ViewerVariant = readViewerVariantFromCookie(request.headers.get("cookie"));
    const expiresAt = Math.floor(Date.now() / 1000) + 60 * 60 * 24;
    const access: RunViewRow[] = (viewData ?? []).filter(
      (row): row is RunViewRow =>
        isRecord(row) &&
        typeof row.run_dir === "string" &&
        isValidRunDir(row.run_dir) &&
        typeof row.release_id === "string" &&
        typeof row.media_access_version === "number" &&
        Number.isInteger(row.media_access_version),
    );

    const payload: StyleComparisonSliceResponse = {
      placements,
      access: access.map((row) => ({
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
