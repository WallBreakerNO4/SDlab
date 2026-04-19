import { NextResponse, type NextRequest } from 'next/server'
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { getPublicEnv } from '@/lib/env/public'

export const runtime = 'nodejs'

const AUTH_ERROR_QUERY_PARAM = 'auth_error'

function sanitizeNextPath(next: string | null): string {
  if (!next || !next.startsWith('/') || next.startsWith('//')) {
    return '/'
  }

  return next
}

function buildRedirectUrl(request: NextRequest, authError?: string): URL {
  const nextPath = sanitizeNextPath(request.nextUrl.searchParams.get('next'))
  const redirectUrl = new URL(nextPath, request.url)

  redirectUrl.searchParams.delete(AUTH_ERROR_QUERY_PARAM)

  if (authError) {
    redirectUrl.searchParams.set(AUTH_ERROR_QUERY_PARAM, authError)
  }

  return redirectUrl
}

function readCallbackErrorCode(request: NextRequest): string | null {
  const errorCode =
    request.nextUrl.searchParams.get('error_code') ??
    request.nextUrl.searchParams.get('error')

  if (!errorCode) {
    return null
  }

  if (errorCode === 'access_denied') {
    return 'oauth_cancelled'
  }

  return 'oauth_callback_failed'
}

/**
 * OAuth callback route for Supabase Auth (PKCE flow).
 *
 * After the user authenticates with an external provider (GitHub, etc.),
 * they are redirected here with a `code` query parameter. We exchange it
 * for a session and redirect to the origin page (or homepage).
 */
export async function GET(request: NextRequest) {
  const callbackError = readCallbackErrorCode(request)
  if (callbackError) {
    return NextResponse.redirect(buildRedirectUrl(request, callbackError))
  }

  const code = request.nextUrl.searchParams.get('code')

  if (!code) {
    return NextResponse.redirect(
      buildRedirectUrl(request, 'oauth_callback_failed'),
    )
  }

  let url: string
  let anonKey: string
  try {
    const publicEnv = getPublicEnv()
    url = publicEnv.supabaseUrl
    anonKey = publicEnv.supabasePublishableKey
  } catch {
    console.error('[auth/callback] Missing Supabase env vars')
    return NextResponse.redirect(buildRedirectUrl(request, 'auth_not_configured'))
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
    return NextResponse.redirect(
      buildRedirectUrl(request, 'oauth_callback_failed'),
    )
  }

  return NextResponse.redirect(buildRedirectUrl(request))
}
