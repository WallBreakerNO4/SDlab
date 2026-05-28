import createMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { getPublicEnv } from "@/lib/env/public";
import { routing } from "./i18n/routing";

const intlMiddleware = createMiddleware(routing);

function shouldRunIntlMiddleware(pathname: string): boolean {
  return !(
    pathname.startsWith("/api/") ||
    pathname === "/auth/callback" ||
    pathname.startsWith("/auth/callback/")
  );
}

async function refreshSupabaseSession(
  request: NextRequest,
  initialResponse: NextResponse,
  createResponse: () => NextResponse,
): Promise<NextResponse> {
  let response = initialResponse;

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
        response = createResponse();
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  await supabase.auth.getUser();
  return response;
}

/**
 * Middleware that handles i18n routing and refreshes the Supabase auth session.
 *
 * IMPORTANT: This file must NOT import from `lib/supabase-auth.ts` because
 * that module uses `server-only` + `next/headers` which are unavailable in
 * Edge middleware. We create the client inline instead.
 */
export async function middleware(request: NextRequest) {
  const runIntl = shouldRunIntlMiddleware(request.nextUrl.pathname);
  const createResponse = () =>
    runIntl ? intlMiddleware(request) : NextResponse.next({ request });
  const intlResponse = createResponse();

  if (runIntl && intlResponse.status !== 200) {
    return intlResponse;
  }

  return refreshSupabaseSession(request, intlResponse, createResponse);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon|api/private-object(?:/|$)|api/public-object(?:/|$)|api/telemetry/web-vitals(?:/|$)|api/comfyui/runs(?:/|$)|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
