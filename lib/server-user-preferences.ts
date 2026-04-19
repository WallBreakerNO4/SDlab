import "server-only";

import type { User } from "@supabase/supabase-js";
import type { createSupabaseAuthClient } from "@/lib/supabase-auth";

type PreferenceSupabaseClient = Awaited<
  ReturnType<typeof createSupabaseAuthClient>
>;

function isMissingSessionError(error: Error | null): boolean {
  if (!error) {
    return false;
  }

  return error.message.toLowerCase().includes("auth session missing");
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
