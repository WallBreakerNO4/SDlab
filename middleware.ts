import { type NextRequest, NextResponse } from 'next/server'
import { createServerClient } from '@supabase/ssr'

/**
 * Middleware that refreshes the Supabase auth session on every request.
 *
 * IMPORTANT: This file must NOT import from `lib/supabase-auth.ts` because
 * that module uses `server-only` + `next/headers` which are unavailable in
 * Edge middleware. We create the client inline instead.
 */
export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

  // If Supabase env vars are not configured, skip auth session refresh
  if (!url || !anonKey) {
    return supabaseResponse
  }

  const supabase = createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll()
      },
      setAll(cookiesToSet) {
        // 1. Forward cookies on the request so downstream Server Components
        //    can read the refreshed session.
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value)
        }

        // 2. Re-create the response with the updated request cookies.
        supabaseResponse = NextResponse.next({ request })

        // 3. Set cookies on the response so the browser stores them.
        for (const { name, value, options } of cookiesToSet) {
          supabaseResponse.cookies.set(name, value, options)
        }
      },
    },
  })

  // Calling getUser() triggers token refresh if the access token is expired.
  // We intentionally ignore the result — we only need the side-effect of
  // refreshing cookies.
  await supabase.auth.getUser()

  return supabaseResponse
}

export const config = {
  matcher: [
    /*
     * Match all request paths EXCEPT:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico (favicon)
     * - Public assets with common image/font extensions
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|avif|ico|woff2?)$).*)',
  ],
}
