import createMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { getPublicEnv } from "@/lib/env/public";
import { routing } from "./i18n/routing";

const intlMiddleware = createMiddleware(routing);

// 已本地化的页面路径模式（不含 locale 前缀），用于白名单匹配
const LOCALIZED_PATH_PATTERNS: RegExp[] = [
  /^\/$/,                    // 首页
  /^\/info/,                 // 信息页
  /^\/privacy-policy/,       // 隐私政策
  /^\/prompts/,              // Prompt 法典
  /^\/models\//,             // 模型详情页
];

const LOCALE_PREFIX_RE = /^\/(zh|en)(\/|$)/;

/**
 * 白名单机制：只对明确做了国际化的页面进行 locale 前缀跳转。
 * 其余路径（sitemap.xml、robots.txt、/api/*、/auth/* 等）原样放行，
 * 不再需要逐个加入黑名单。
 */
function shouldRunIntlMiddleware(pathname: string): boolean {
  // 1. 已带 locale 前缀的路径 → 交给 i18n 中间件校验 locale 有效性
  if (LOCALE_PREFIX_RE.test(pathname)) return true;

  // 2. 已知的本地化页面（无前缀）→ 交给 i18n 中间件添加前缀并重定向
  if (LOCALIZED_PATH_PATTERNS.some((p) => p.test(pathname))) return true;

  // 3. 其他所有路径 → 跳过 i18n 处理
  return false;
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
