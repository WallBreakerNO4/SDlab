import { createBrowserClient } from '@supabase/ssr'
import { getPublicEnv } from '@/lib/env/public'

export function createSupabaseBrowserClient() {
  const { supabaseUrl, supabasePublishableKey } = getPublicEnv()

  return createBrowserClient(supabaseUrl, supabasePublishableKey)
}
