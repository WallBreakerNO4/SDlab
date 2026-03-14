const ALLOWED_PREFIX = "runs/";
const ALLOWED_VARIANTS_PREFIXES = ["display_", "thumb_"];
const ALLOWED_EXTENSIONS = [".webp", ".avif"];

/**
 * 分段进行 URL 编码，保留斜杠
 */
function encodePathSegments(path: string): string {
  return path
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

/**
 * 校验 R2 Key 是否符合基本安全约束
 */
function validateR2Key(r2Key: string): void {
  if (!r2Key.startsWith(ALLOWED_PREFIX)) {
    throw new Error(`Invalid R2 key: Must start with "${ALLOWED_PREFIX}"`);
  }
}

function validateVariantFileName(r2Key: string): void {
  const segments = r2Key.split("/");
  const fileName = segments[segments.length - 1];
  const isAllowedVariant = ALLOWED_VARIANTS_PREFIXES.some((prefix) =>
    fileName.startsWith(prefix),
  );
  const hasAllowedExtension = ALLOWED_EXTENSIONS.some((extension) =>
    fileName.endsWith(extension),
  );

  if (!isAllowedVariant || !hasAllowedExtension) {
    throw new Error(
      `Access denied: Only ${ALLOWED_VARIANTS_PREFIXES.join("/")} variants with ${ALLOWED_EXTENSIONS.join("/")} are allowed`,
    );
  }
}

export function publicObjectUrl(r2Key: string): string {
  validateR2Key(r2Key);
  validateVariantFileName(r2Key);

  const baseUrl = process.env.R2_PUBLIC_BASE_URL;
  if (!baseUrl) {
    throw new Error("R2_PUBLIC_BASE_URL is not defined");
  }

  const normalizedBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return `${normalizedBase}/${encodePathSegments(r2Key)}`;
}

export function privateObjectUrl(r2Key: string): string {
  validateR2Key(r2Key);
  validateVariantFileName(r2Key);

  return `/api/r2/private/${encodePathSegments(r2Key)}`;
}
