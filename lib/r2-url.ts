const ALLOWED_PREFIX = "runs/";

function encodePathSegments(path: string): string {
  return path
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

function validateR2Key(r2Key: string): void {
  if (!r2Key.startsWith(ALLOWED_PREFIX)) {
    throw new Error(`Invalid R2 key: Must start with "${ALLOWED_PREFIX}"`);
  }
}

function readPublicBaseUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_R2_PUBLIC_BASE_URL;
  if (!baseUrl) {
    throw new Error("NEXT_PUBLIC_R2_PUBLIC_BASE_URL is not defined");
  }
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

export function publicObjectUrl(r2Key: string): string {
  validateR2Key(r2Key);
  return `${readPublicBaseUrl()}/${encodePathSegments(r2Key)}`;
}

export function privateObjectProxyUrl(r2Key: string, grant: string): string {
  validateR2Key(r2Key);
  const url = new URL("/api/private-object", "http://localhost");
  url.searchParams.set("key", r2Key);
  url.searchParams.set("grant", grant);
  return `${url.pathname}${url.search}`;
}
