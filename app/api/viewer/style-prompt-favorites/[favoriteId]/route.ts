import { createSupabaseAuthClient } from "@/lib/supabase-auth";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ favoriteId: string }>;
};

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

export async function PATCH(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { favoriteId } = await context.params;
    if (!UUID_PATTERN.test(favoriteId)) {
      return jsonError(404, "Style prompt favorite not found");
    }

    const supabase = await createSupabaseAuthClient();
    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError || !user) {
      return jsonError(401, "Authentication required");
    }

    const now = new Date().toISOString();
    const { data, error } = await supabase
      .from("user_style_prompt_favorites")
      .update({ last_used_at: now, updated_at: now })
      .eq("id", favoriteId)
      .select("id")
      .maybeSingle();

    if (error) {
      return jsonError(500, "Failed to update style prompt favorite");
    }
    if (!data) {
      return jsonError(404, "Style prompt favorite not found");
    }

    return Response.json({ ok: true });
  } catch (error) {
    console.error("[api/viewer/style-prompt-favorites/:favoriteId]", error);
    return jsonError(500, "Failed to update style prompt favorite");
  }
}

export async function DELETE(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { favoriteId } = await context.params;
    if (!UUID_PATTERN.test(favoriteId)) {
      return jsonError(404, "Style prompt favorite not found");
    }

    const supabase = await createSupabaseAuthClient();
    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError || !user) {
      return jsonError(401, "Authentication required");
    }

    const { data, error } = await supabase
      .from("user_style_prompt_favorites")
      .delete()
      .eq("id", favoriteId)
      .select("id")
      .maybeSingle();

    if (error) {
      return jsonError(500, "Failed to delete style prompt favorite");
    }
    if (!data) {
      return jsonError(404, "Style prompt favorite not found");
    }

    return Response.json({ ok: true });
  } catch (error) {
    console.error("[api/viewer/style-prompt-favorites/:favoriteId]", error);
    return jsonError(500, "Failed to delete style prompt favorite");
  }
}
