import {
  isStyleFavoriteLabel,
  isStyleKey,
  type StyleFavoriteEntry,
  type StyleFavoriteRunRef,
  type StyleFavoritesResponse,
  type StyleKey,
} from "@/lib/style-favorites";
import { requireViewerForPreferenceWrite } from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";

export const runtime = "nodejs";

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

type FavoriteRow = {
  style_key: StyleKey;
  label: string;
  created_at: string;
};

type RunStyleItemRow = {
  run_dir: string;
  style_key: StyleKey;
  y_index: number;
};

// 防御性过滤：DB 有 CHECK 约束，正常不会丢行；仅避免异常行破坏响应形态
function isFavoriteRow(value: unknown): value is FavoriteRow {
  if (!isRecord(value)) return false;
  return (
    isStyleKey(value.style_key) &&
    typeof value.label === "string" &&
    typeof value.created_at === "string"
  );
}

function isRunStyleItemRow(value: unknown): value is RunStyleItemRow {
  if (!isRecord(value)) return false;
  return (
    typeof value.run_dir === "string" &&
    isStyleKey(value.style_key) &&
    typeof value.y_index === "number" &&
    Number.isInteger(value.y_index) &&
    value.y_index >= 0
  );
}

function getModelName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function parseUpsertBody(
  value: unknown,
): { style_key: StyleKey; label: string } | null {
  if (!isRecord(value)) return null;
  if (!isStyleKey(value.style_key)) return null;
  if (!isStyleFavoriteLabel(value.label)) return null;
  return { style_key: value.style_key, label: value.label };
}

export async function GET(): Promise<Response> {
  try {
    const supabase = await createSupabaseAuthClient();
    await requireViewerForPreferenceWrite(supabase);

    // RLS 限定只能读到当前用户自己的收藏行
    const { data: favoriteData, error: favoritesError } = await supabase
      .from("user_style_favorites")
      .select("style_key,label,created_at")
      .order("created_at", { ascending: false });

    if (favoritesError) {
      return jsonError(500, "Failed to load style favorites");
    }

    const favorites = (favoriteData ?? []).filter(isFavoriteRow);
    if (favorites.length === 0) {
      const empty: StyleFavoritesResponse = { favorites: [] };
      return Response.json(empty);
    }

    // 按 style_key 集反查 run_style_items，得到每个收藏在哪些 run 中可用
    const styleKeys = [...new Set(favorites.map((row) => row.style_key))];
    const { data: runItemData, error: runItemsError } = await supabase
      .from("run_style_items")
      .select("run_dir,style_key,y_index")
      .in("style_key", styleKeys);

    if (runItemsError) {
      return jsonError(500, "Failed to load style favorites");
    }

    const runItems = (runItemData ?? []).filter(isRunStyleItemRow);
    const runDirs = [...new Set(runItems.map((row) => row.run_dir))];

    // run_list_items 提供模型显示名；查不到（或为空）时 name 置 null
    const nameByRunDir = new Map<string, string | null>();
    if (runDirs.length > 0) {
      const { data: runListData, error: runListError } = await supabase
        .from("run_list_items")
        .select("run_dir,model_name")
        .in("run_dir", runDirs);

      if (runListError) {
        return jsonError(500, "Failed to load style favorites");
      }

      for (const row of runListData ?? []) {
        if (!isRecord(row) || typeof row.run_dir !== "string") continue;
        if (nameByRunDir.has(row.run_dir)) continue;
        nameByRunDir.set(row.run_dir, getModelName(row.model_name));
      }
    }

    const runsByStyleKey = new Map<StyleKey, StyleFavoriteRunRef[]>();
    for (const item of runItems) {
      const ref: StyleFavoriteRunRef = {
        run_dir: item.run_dir,
        name: nameByRunDir.get(item.run_dir) ?? null,
        y_index: item.y_index,
      };
      const refs = runsByStyleKey.get(item.style_key);
      if (refs) {
        refs.push(ref);
      } else {
        runsByStyleKey.set(item.style_key, [ref]);
      }
    }

    const entries: StyleFavoriteEntry[] = favorites.map((row) => ({
      ...row,
      runs: (runsByStyleKey.get(row.style_key) ?? []).sort((a, b) =>
        a.run_dir.localeCompare(b.run_dir),
      ),
    }));

    const payload: StyleFavoritesResponse = { favorites: entries };
    return Response.json(payload);
  } catch (error) {
    if (error instanceof Error && error.message === "UNAUTHENTICATED") {
      return jsonError(401, "Authentication required");
    }
    return jsonError(500, "Failed to load style favorites");
  }
}

export async function PUT(request: Request): Promise<Response> {
  // 先验证请求体再鉴权（spec 边界）
  const body = parseUpsertBody(await request.json().catch(() => null));
  if (!body) {
    return jsonError(400, "Invalid style favorite payload");
  }

  try {
    const supabase = await createSupabaseAuthClient();
    const user = await requireViewerForPreferenceWrite(supabase);

    // 行内带 user_id，RLS 保证只写自己的行；
    // 冲突走 ON CONFLICT DO UPDATE，依赖 user_style_favorites 的 update policy
    const { error } = await supabase.from("user_style_favorites").upsert(
      {
        user_id: user.id,
        style_key: body.style_key,
        label: body.label,
      },
      { onConflict: "user_id,style_key" },
    );

    if (error) {
      throw error;
    }

    return Response.json({ style_key: body.style_key, label: body.label });
  } catch (error) {
    if (error instanceof Error && error.message === "UNAUTHENTICATED") {
      return jsonError(401, "Authentication required");
    }
    return jsonError(500, "Failed to update style favorite");
  }
}
