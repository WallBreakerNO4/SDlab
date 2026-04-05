import {
  getViewerShowNsfwPreference,
  requireViewerForPreferenceWrite,
  setViewerShowNsfwPreference,
} from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";

export const runtime = "nodejs";

function parseBody(value: unknown): { show_nsfw: boolean } | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }

  const candidate = (value as { show_nsfw?: unknown }).show_nsfw;
  if (typeof candidate !== "boolean") {
    return null;
  }

  return { show_nsfw: candidate };
}

export async function GET(): Promise<Response> {
  try {
    const supabase = await createSupabaseAuthClient();
    const showNsfw = await getViewerShowNsfwPreference(supabase);

    return Response.json({ show_nsfw: showNsfw });
  } catch {
    return Response.json(
      { error: "Failed to load viewer preference" },
      { status: 500 },
    );
  }
}

export async function PATCH(request: Request): Promise<Response> {
  try {
    const body = parseBody(await request.json());
    if (!body) {
      return Response.json(
        { error: "Invalid viewer preference payload" },
        { status: 400 },
      );
    }

    const supabase = await createSupabaseAuthClient();
    const user = await requireViewerForPreferenceWrite(supabase);

    await setViewerShowNsfwPreference(supabase, {
      userId: user.id,
      showNsfw: body.show_nsfw,
    });

    return Response.json({ show_nsfw: body.show_nsfw });
  } catch (error) {
    if (error instanceof Error && error.message === "UNAUTHENTICATED") {
      return Response.json(
        { error: "Authentication required" },
        { status: 401 },
      );
    }

    return Response.json(
      { error: "Failed to update viewer preference" },
      { status: 500 },
    );
  }
}
