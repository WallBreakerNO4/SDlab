import createMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { getPublicEnv } from "@/lib/env/public";
import { routing } from "./i18n/routing";

const intlMiddleware = createMiddleware(routing);

/**
 * Middleware that handles i18n routing and refreshes the Supabase auth session.
 *
 * IMPORTANT: This file must NOT import from `lib/supabase-auth.ts` because
 * that module uses `server-only` + `next/headers` which are unavailable in
 * Edge middleware. We create the client inline instead.
 */
export async function middleware(request: NextRequest) {
  // 1. Handle i18n routing first (redirects, locale detection)
  const intlResponse = intlMiddleware(request);
  if (intlResponse.status !== 200) {
    return intlResponse;
  }

  // 2. Continue with Supabase auth session refresh
  let response = intlResponse;

  let url: string;
  let anonKey: string;
  try {
    const publicEnv = getPublicEnv();
    url = publicEnv.supabaseUrl;
    anonKey = publicEnv.supabasePublishableKey;
  } catch {
    return response;
  }

  const supabase = createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  await supabase.auth.getUser();
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon|api/private-object(?:/|$)|api/public-object(?:/|$)|api/telemetry/web-vitals(?:/|$)|api/comfyui/runs(?:/|$)|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
