import type { NextResponse } from "next/server";

export const VIEWER_SHOW_NSFW_COOKIE = "sdslab_show_nsfw";
export const DEFAULT_SHOW_NSFW = false;

export function parseViewerShowNsfwCookieValue(
  raw: string | null | undefined,
): boolean {
  return raw === "1";
}

export function serializeViewerShowNsfwCookieValue(showNsfw: boolean): string {
  return showNsfw ? "1" : "0";
}

export function setViewerShowNsfwCookie(
  response: NextResponse,
  showNsfw: boolean,
): void {
  response.cookies.set(VIEWER_SHOW_NSFW_COOKIE, serializeViewerShowNsfwCookieValue(showNsfw), {
    httpOnly: false,
    sameSite: "lax",
    secure: true,
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
}
