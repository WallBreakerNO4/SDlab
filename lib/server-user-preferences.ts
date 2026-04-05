import "server-only";

import type { User } from "@supabase/supabase-js";
import type { createSupabaseAuthClient } from "@/lib/supabase-auth";

export const DEFAULT_SHOW_NSFW = false;

type PreferenceSupabaseClient = Awaited<
  ReturnType<typeof createSupabaseAuthClient>
>;

function isMissingSessionError(error: Error | null): boolean {
  if (!error) {
    return false;
  }

  return error.message.toLowerCase().includes("auth session missing");
}

export async function getViewerShowNsfwPreference(
  supabase: PreferenceSupabaseClient,
): Promise<boolean> {
  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError) {
    if (isMissingSessionError(userError)) {
      return DEFAULT_SHOW_NSFW;
    }
    throw userError;
  }

  if (!user) {
    return DEFAULT_SHOW_NSFW;
  }

  const { data, error } = await supabase
    .from("user_preferences")
    .select("show_nsfw")
    .eq("user_id", user.id)
    .maybeSingle();

  if (error) {
    if (isMissingSessionError(error)) {
      return DEFAULT_SHOW_NSFW;
    }
    throw error;
  }

  return data?.show_nsfw ?? DEFAULT_SHOW_NSFW;
}

export async function requireViewerForPreferenceWrite(
  supabase: PreferenceSupabaseClient,
): Promise<User> {
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error) {
    if (isMissingSessionError(error)) {
      throw new Error("UNAUTHENTICATED");
    }
    throw error;
  }

  if (!user) {
    throw new Error("UNAUTHENTICATED");
  }

  return user;
}

export async function setViewerShowNsfwPreference(
  supabase: PreferenceSupabaseClient,
  options: {
    userId: string;
    showNsfw: boolean;
  },
): Promise<void> {
  const { userId, showNsfw } = options;
  const { error } = await supabase.from("user_preferences").upsert(
    {
      user_id: userId,
      show_nsfw: showNsfw,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "user_id" },
  );

  if (error) {
    throw error;
  }
}
