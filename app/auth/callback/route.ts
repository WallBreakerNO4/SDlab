import { NextResponse } from 'next/server'
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export const runtime = 'nodejs'

/**
 * OAuth callback route for Supabase Auth (PKCE flow).
 *
 * After the user authenticates with an external provider (GitHub, etc.),
 * they are redirected here with a `code` query parameter. We exchange it
 * for a session and redirect to the origin page (or homepage).
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const next = searchParams.get('next') ?? '/'

  if (!code) {
    // No code — redirect to homepage
    return NextResponse.redirect(`${origin}${next}`)
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

  if (!url || !anonKey) {
    console.error('[auth/callback] Missing Supabase env vars')
    return NextResponse.redirect(`${origin}${next}`)
  }

  const cookieStore = await cookies()

  const supabase = createServerClient(url, anonKey, {
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
          // Ignored — middleware will handle on next request
        }
      },
    },
  })

  const { error } = await supabase.auth.exchangeCodeForSession(code)

  if (error) {
    console.error('[auth/callback] Code exchange failed:', error.message)
    return NextResponse.redirect(`${origin}${next}`)
  }

  return NextResponse.redirect(`${origin}${next}`)
}
