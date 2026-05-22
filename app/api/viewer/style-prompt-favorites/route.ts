import { isValidRunDir } from "@/lib/comfyui-types";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import {
  normalizeStyleKey,
  normalizeStylePromptText,
  STYLE_PROMPT_KEY_MAX_LENGTH,
  STYLE_PROMPT_LABEL_MAX_LENGTH,
  type StylePromptFavorite,
} from "@/lib/style-prompt-favorites";

export const runtime = "nodejs";

type FavoriteRow = StylePromptFavorite & {
  user_id?: string;
};

type CreateFavoriteBody = {
  style_key: string;
  label: string;
  source_run_dir: string | null;
  source_y_index: number | null;
};

type RunYPromptRefRow = {
  style_key: string;
  label: string;
};

function jsonError(status: number, message: string): Response {
  return Response.json({ error: message }, { status });
}

function parseCreateBody(value: unknown): CreateFavoriteBody | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }

  const candidate = value as {
    style_key?: unknown;
    label?: unknown;
    source_run_dir?: unknown;
    source_y_index?: unknown;
  };

  if (typeof candidate.style_key !== "string" || typeof candidate.label !== "string") {
    return null;
  }

  const styleKey = normalizeStyleKey(candidate.style_key);
  const label = normalizeStylePromptText(candidate.label);
  if (
    !styleKey ||
    styleKey.length > STYLE_PROMPT_KEY_MAX_LENGTH ||
    !label ||
    label.length > STYLE_PROMPT_LABEL_MAX_LENGTH
  ) {
    return null;
  }

  const sourceRunDir =
    typeof candidate.source_run_dir === "string"
      ? candidate.source_run_dir
      : null;
  if (sourceRunDir !== null && !isValidRunDir(sourceRunDir)) {
    return null;
  }

  const sourceYIndex =
    typeof candidate.source_y_index === "number" &&
    Number.isInteger(candidate.source_y_index) &&
    candidate.source_y_index >= 0
      ? candidate.source_y_index
      : null;

  return {
    style_key: styleKey,
    label,
    source_run_dir: sourceRunDir,
    source_y_index: sourceYIndex,
  };
}

function toFavorite(row: FavoriteRow): StylePromptFavorite {
  return {
    id: row.id,
    style_key: row.style_key,
    label: row.label,
    source_run_dir: row.source_run_dir,
    source_y_index: row.source_y_index,
    created_at: row.created_at,
    updated_at: row.updated_at,
    last_used_at: row.last_used_at,
  };
}

export async function GET(): Promise<Response> {
  try {
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
      .select(
        "id,style_key,label,source_run_dir,source_y_index,created_at,updated_at,last_used_at",
      )
      .order("last_used_at", { ascending: false, nullsFirst: false })
      .order("created_at", { ascending: false });

    if (error) {
      return jsonError(500, "Failed to load style prompt favorites");
    }

    return Response.json({
      favorites: ((data as FavoriteRow[] | null) ?? []).map(toFavorite),
    });
  } catch (error) {
    console.error("[api/viewer/style-prompt-favorites]", error);
    return jsonError(500, "Failed to load style prompt favorites");
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    const body = parseCreateBody(await request.json());
    if (!body) {
      return jsonError(400, "Invalid style prompt favorite payload");
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
    let styleKey = body.style_key;
    let label = body.label;

    if (body.source_run_dir !== null && body.source_y_index !== null) {
      const { data: refData, error: refError } = await supabase
        .from("run_y_prompt_refs")
        .select("style_key,label")
        .eq("run_dir", body.source_run_dir)
        .eq("y_index", body.source_y_index)
        .maybeSingle();

      if (refError) {
        return jsonError(500, "Failed to save style prompt favorite");
      }

      const ref = refData as RunYPromptRefRow | null;
      if (ref) {
        styleKey = ref.style_key;
        label = ref.label;
      }
    }

    const { data, error } = await supabase
      .from("user_style_prompt_favorites")
      .upsert(
        {
          user_id: user.id,
          style_key: styleKey,
          label,
          source_run_dir: body.source_run_dir,
          source_y_index: body.source_y_index,
          updated_at: now,
        },
        { onConflict: "user_id,style_key" },
      )
      .select(
        "id,style_key,label,source_run_dir,source_y_index,created_at,updated_at,last_used_at",
      )
      .single();

    if (error || !data) {
      return jsonError(500, "Failed to save style prompt favorite");
    }

    return Response.json({ favorite: toFavorite(data as FavoriteRow) });
  } catch (error) {
    console.error("[api/viewer/style-prompt-favorites]", error);
    return jsonError(500, "Failed to save style prompt favorite");
  }
}
