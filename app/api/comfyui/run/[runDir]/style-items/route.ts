import { isValidRunDir } from "@/lib/comfyui-types";
import { isStyleItem } from "@/lib/style-favorites";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ runDir: string }>;
};

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

export async function GET(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params;
    if (!isValidRunDir(runDir)) {
      return jsonError(400, "Invalid run directory");
    }

    // run_style_items 是公开元数据（RLS 放开 anon/authenticated select），
    // 未登录也可读；沿用本目录统一的 auth client，未登录时按 anon 角色查询。
    const supabase = await createSupabaseAuthClient();
    const { data, error } = await supabase
      .from("run_style_items")
      .select("y_index,style_key")
      .eq("run_dir", runDir)
      .order("y_index", { ascending: true });

    if (error) {
      return jsonError(500, "Failed to load style items");
    }

    // 防御性过滤：DB 有 CHECK 约束，正常不会丢行；仅避免异常行破坏响应形态
    const items = (data ?? []).filter(isStyleItem);
    return Response.json(items);
  } catch {
    return jsonError(500, "Failed to load style items");
  }
}
