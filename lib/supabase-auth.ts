import 'server-only'

import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

/**
 * Server-side Supabase client for authentication purposes.
 *
 * Uses the **anon key** (not service role) so that requests are subject to RLS.
 * Cookie-based session handling allows `getUser()` to validate the current
 * visitor's JWT.
 *
 * NOTE: This is separate from `supabase-server.ts` which uses the service role
 * key to bypass RLS for backend data access.
 */
export async function createSupabaseAuthClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

  if (!url || !anonKey) {
    throw new Error(
      'Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY environment variables',
    )
  }

  const cookieStore = await cookies()

  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll()
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options)
          }
        } catch {
          // setAll can throw when called from a Server Component (read-only
          // cookie store). This is expected — the middleware handles session
          // refresh on the next request.
        }
      },
    },
  })
}
