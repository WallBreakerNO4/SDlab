import "server-only";

import { unstable_cache } from "next/cache";
import { createClient } from "@supabase/supabase-js";

import { getPublicEnv } from "@/lib/env/public";
import {
  normalizeStyleComparisonModelsRpcRows,
  type StyleComparisonModel,
} from "@/lib/style-comparison";

async function loadPublishedRuns(): Promise<StyleComparisonModel[]> {
  const { supabaseUrl, supabasePublishableKey } = getPublicEnv();
  const supabase = createClient(supabaseUrl, supabasePublishableKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await supabase.rpc("get_style_comparison_models");
  if (error) throw error;
  const models = normalizeStyleComparisonModelsRpcRows(data);
  if (!models) throw new Error("Invalid style comparison model catalog response");
  return models;
}

export const getCachedPublishedRuns = unstable_cache(loadPublishedRuns, ["style-comparison-models"], {
  revalidate: 300,
  tags: ["style-comparison-models"],
});
