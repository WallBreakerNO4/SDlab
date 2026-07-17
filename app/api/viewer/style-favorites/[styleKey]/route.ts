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

export async function DELETE(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  // 框架已把 %3A 解码回 ":"；先校验路径参数再鉴权
  const { styleKey } = await context.params;
  if (!isStyleKey(styleKey)) {
    return jsonError(400, "Invalid style key");
  }

  try {
    const supabase = await createSupabaseAuthClient();
    const user = await requireViewerForPreferenceWrite(supabase);

    // user_id + style_key 双条件定位，RLS 保证只删自己的行
    const { error } = await supabase
      .from("user_style_favorites")
      .delete()
      .eq("user_id", user.id)
      .eq("style_key", styleKey);

    if (error) {
      throw error;
    }

    return Response.json({ style_key: styleKey });
  } catch (error) {
    if (error instanceof Error && error.message === "UNAUTHENTICATED") {
      return jsonError(401, "Authentication required");
    }
    return jsonError(500, "Failed to delete style favorite");
  }
}
