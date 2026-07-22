import {
  decodeStyleComparisonCursor,
  encodeStyleComparisonCursor,
  isStyleComparisonResponse,
  parseStyleComparisonLimit,
  type StyleComparisonResponse,
} from "@/lib/style-comparison";
import { isStyleKey } from "@/lib/style-favorites";
import { requireViewerForPreferenceWrite } from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import { getCachedPublishedRuns } from "@/lib/style-comparison-server";

export const runtime = "nodejs";

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const limit = parseStyleComparisonLimit(url.searchParams.get("limit"));
  if (limit === null) return jsonError(400, "Invalid style comparison limit");

  const cursorRaw = url.searchParams.get("cursor");
  const cursor = decodeStyleComparisonCursor(cursorRaw);
  if (cursorRaw && !cursor) return jsonError(400, "Invalid style comparison cursor");

  try {
    const supabase = await createSupabaseAuthClient();
    await requireViewerForPreferenceWrite(supabase);

    let query = supabase
      .from("user_style_favorites")
      .select("style_key,label,created_at")
      .order("created_at", { ascending: false })
      .order("style_key", { ascending: false })
      .limit(limit + 1);
    if (cursor) {
      query = query.or(
        `created_at.lt.${cursor.created_at},and(created_at.eq.${cursor.created_at},style_key.lt.${cursor.style_key})`,
      );
    }
    const { data, error } = await query;
    if (error) return jsonError(500, "Failed to load style comparison");

    const rows = (data ?? []).filter(
      (row): row is { style_key: string; label: string; created_at: string } =>
        isRecord(row) &&
        isStyleKey(row.style_key) &&
        typeof row.label === "string" &&
        typeof row.created_at === "string",
    );
    const hasMore = rows.length > limit;
    const favorites = rows.slice(0, limit);
    const last = favorites[favorites.length - 1];
    const payload: StyleComparisonResponse = {
      favorites,
      next_cursor:
        hasMore && last
          ? encodeStyleComparisonCursor({ created_at: last.created_at, style_key: last.style_key })
          : null,
    };
    if (!cursor) payload.models = await getCachedPublishedRuns();

    // Keep this assertion close to the public boundary while allowing Supabase rows
    // to be defensively filtered above.
    if (!isStyleComparisonResponse(payload)) return jsonError(500, "Failed to load style comparison");
    return Response.json(payload);
  } catch (error) {
    if (error instanceof Error && error.message === "UNAUTHENTICATED") {
      return jsonError(401, "Authentication required");
    }
    return jsonError(500, "Failed to load style comparison");
  }
}
