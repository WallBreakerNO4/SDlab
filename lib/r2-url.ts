/**
 * R2 URL 构建工具
 * 
 * 约束：
 * 1. 仅允许以 `runs/` 开头的 key
 * 2. 公开链接仅允许 `display_*` 或 `thumb_*` 变体
 * 3. 拒绝 `original_png` 进入公开链接
 * 4. 使用分段 encode 避免破坏路径结构
 */

const ALLOWED_PREFIX = "runs/";
const DISALLOWED_VARIANT = "original_png";
const ALLOWED_VARIANTS_PREFIXES = ["display_", "thumb_"];

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

/**
 * 获取公开直链 URL
 * 仅限 display_* 和 thumb_* 变体，拒绝 original_png
 */
export function publicObjectUrl(r2Key: string): string {
  validateR2Key(r2Key);

  const baseUrl = process.env.R2_PUBLIC_BASE_URL;
  if (!baseUrl) {
    throw new Error("R2_PUBLIC_BASE_URL is not defined");
  }

  // 变体校验
  const segments = r2Key.split("/");
  const fileName = segments[segments.length - 1];

  if (fileName.includes(DISALLOWED_VARIANT)) {
    throw new Error(`Access denied: "${DISALLOWED_VARIANT}" is not allowed in public URLs`);
  }

  const isAllowedVariant = ALLOWED_VARIANTS_PREFIXES.some((prefix) =>
    fileName.startsWith(prefix)
  );

  if (!isAllowedVariant) {
    throw new Error(
      `Access denied: Only variants starting with ${ALLOWED_VARIANTS_PREFIXES.join(
        " or "
      )} are allowed in public URLs`
    );
  }

  const normalizedBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return `${normalizedBase}/${encodePathSegments(r2Key)}`;
}

/**
 * 获取站内代理私有 URL
 * 返回格式：/api/r2/private/<r2_key>
 */
export function privateObjectUrl(r2Key: string): string {
  validateR2Key(r2Key);
  
  // 私有代理不限制变体，但依然要求 runs/ 前缀
  return `/api/r2/private/${encodePathSegments(r2Key)}`;
}
