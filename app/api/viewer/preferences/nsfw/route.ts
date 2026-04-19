import {
  requireViewerForPreferenceWrite,
  setViewerShowNsfwPreference,
} from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import {
  DEFAULT_SHOW_NSFW,
  parseViewerShowNsfwCookieValue,
  setViewerShowNsfwCookie,
  VIEWER_SHOW_NSFW_COOKIE,
} from "@/lib/viewer-nsfw-cookie";
import { NextResponse } from "next/server";

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

export async function GET(request: Request): Promise<Response> {
  const rawCookie = request.headers.get("cookie");
  const cookieEntry = rawCookie
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${VIEWER_SHOW_NSFW_COOKIE}=`));
  const value = cookieEntry?.slice(VIEWER_SHOW_NSFW_COOKIE.length + 1);
  return Response.json({
    show_nsfw: value === undefined
      ? DEFAULT_SHOW_NSFW
      : parseViewerShowNsfwCookieValue(value),
  });
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

    const response = NextResponse.json({ show_nsfw: body.show_nsfw });
    setViewerShowNsfwCookie(response, body.show_nsfw);
    return response;
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
