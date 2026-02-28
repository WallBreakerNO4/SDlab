import 'server-only'

import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

/**
 * Server-side Supabase client with cookie-based session handling.
 *
 * Uses the **anon key** so that requests are subject to RLS.
 * When no user session exists, queries run as the `anon` role.
 * When a user is logged in (cookie JWT), queries run as `authenticated`.
 *
 * Used by both API routes (data queries) and the R2 private proxy (auth check).
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
