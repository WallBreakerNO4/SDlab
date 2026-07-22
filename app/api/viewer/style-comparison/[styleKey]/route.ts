import { type StyleComparisonDetailResponse } from "@/lib/style-comparison";
import { getCachedPublishedRuns } from "@/lib/style-comparison-server";
import { isStyleKey } from "@/lib/style-favorites";
import { requireViewerForPreferenceWrite } from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ styleKey: string }>;
};

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

export async function GET(_request: Request, context: RouteContext): Promise<Response> {
  const { styleKey } = await context.params;
  if (!isStyleKey(styleKey)) return jsonError(404, "Style favorite not found");

  try {
    const supabase = await createSupabaseAuthClient();
    await requireViewerForPreferenceWrite(supabase);
    const { data, error } = await supabase
      .from("user_style_favorites")
      .select("style_key,label,created_at")
      .eq("style_key", styleKey)
      .maybeSingle();
    if (error) return jsonError(500, "Failed to load style comparison");
    if (!data || typeof data.style_key !== "string" || typeof data.label !== "string" || typeof data.created_at !== "string") {
      return jsonError(404, "Style favorite not found");
    }

    const payload: StyleComparisonDetailResponse = {
      favorite: { style_key: data.style_key, label: data.label, created_at: data.created_at },
      models: await getCachedPublishedRuns(),
    };
    return Response.json(payload);
  } catch (error) {
    if (error instanceof Error && error.message === "UNAUTHENTICATED") {
      return jsonError(401, "Authentication required");
    }
    return jsonError(500, "Failed to load style comparison");
  }
}
