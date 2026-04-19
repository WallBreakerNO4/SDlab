import { createHash, createHmac } from "node:crypto";

import { getCloudflareContext } from "@opennextjs/cloudflare";

const ALLOWED_PREFIX = "runs/";
const ALLOWED_VARIANTS_PREFIXES = ["display_", "thumb_"];
const ALLOWED_EXTENSIONS = [".webp", ".avif"];
const DEFAULT_SIGNED_URL_TTL_SECONDS = 300;
const SIGNED_URL_SERVICE = "s3";
const SIGNED_URL_REGION = "auto";

type PrivateSigningConfig = {
  accessKeyId: string;
  secretAccessKey: string;
  endpoint: string;
  bucketName: string;
  ttlSeconds: number;
};

export type PrivateSignedObjectUrl = {
  url: string;
  expiresAt: string;
  ttlSeconds: number;
};

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

function awsPercentEncode(value: string): string {
  return encodeURIComponent(value).replace(
    /[!'()*]/g,
    (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`,
  );
}

function encodeCanonicalPath(path: string): string {
  return path
    .split("/")
    .map((segment) => awsPercentEncode(segment))
    .join("/");
}

function readRuntimeEnv(name: string): string | null {
  try {
    const { env } = getCloudflareContext();
    const raw = (env as unknown as Record<string, unknown>)[name];
    if (typeof raw === "string") {
      const trimmed = raw.trim();
      if (trimmed.length > 0) {
        return trimmed;
      }
    }
  } catch {}

  const raw = process.env[name];
  if (!raw) {
    return null;
  }

  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function parsePositiveInt(raw: string | null): number | null {
  if (!raw || !/^[0-9]+$/.test(raw)) {
    return null;
  }

  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    return null;
  }

  return parsed;
}

function getPrivateSigningConfig(): PrivateSigningConfig {
  const accessKeyId = readRuntimeEnv("R2_ACCESS_KEY_ID");
  const secretAccessKey = readRuntimeEnv("R2_SECRET_ACCESS_KEY");
  const endpoint = readRuntimeEnv("R2_ENDPOINT");
  const bucketName = readRuntimeEnv("R2_PRIVATE_BUCKET");

  if (!accessKeyId || !secretAccessKey || !endpoint || !bucketName) {
    throw new Error(
      "Missing private image signing configuration: R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_PRIVATE_BUCKET are required",
    );
  }

  const ttlSeconds =
    parsePositiveInt(readRuntimeEnv("R2_SIGNED_URL_TTL_SECONDS")) ??
    DEFAULT_SIGNED_URL_TTL_SECONDS;

  return {
    accessKeyId,
    secretAccessKey,
    endpoint,
    bucketName,
    ttlSeconds,
  };
}

function sha256Hex(input: string): string {
  return createHash("sha256").update(input).digest("hex");
}

function hmac(key: Buffer | string, value: string): Buffer {
  return createHmac("sha256", key).update(value).digest();
}

function buildSigningKey(secretAccessKey: string, dateStamp: string): Buffer {
  const kDate = hmac(`AWS4${secretAccessKey}`, dateStamp);
  const kRegion = hmac(kDate, SIGNED_URL_REGION);
  const kService = hmac(kRegion, SIGNED_URL_SERVICE);
  return hmac(kService, "aws4_request");
}

function formatAmzDate(date: Date): { amzDate: string; dateStamp: string } {
  const iso = date.toISOString().replace(/[-:]/g, "");
  const amzDate = `${iso.slice(0, 8)}T${iso.slice(9, 15)}Z`;
  return {
    amzDate,
    dateStamp: amzDate.slice(0, 8),
  };
}

function buildSignedQueryString(
  params: Array<[string, string]>,
  signature?: string,
): string {
  const entries = [...params];
  if (signature) {
    entries.push(["X-Amz-Signature", signature]);
  }

  return entries
    .sort(([aKey, aValue], [bKey, bValue]) => {
      if (aKey === bKey) {
        return aValue.localeCompare(bValue);
      }
      return aKey.localeCompare(bKey);
    })
    .map(
      ([key, value]) => `${awsPercentEncode(key)}=${awsPercentEncode(value)}`,
    )
    .join("&");
}

function buildSignedPrivateObjectUrl(
  config: PrivateSigningConfig,
  r2Key: string,
  now: Date = new Date(),
): string {
  const endpoint = new URL(config.endpoint);
  const { amzDate, dateStamp } = formatAmzDate(now);
  const credentialScope = `${dateStamp}/${SIGNED_URL_REGION}/${SIGNED_URL_SERVICE}/aws4_request`;
  const canonicalUri = encodeCanonicalPath(`/${config.bucketName}/${r2Key}`);
  const signedHeaders = "host";
  const canonicalHeaders = `host:${endpoint.host}\n`;

  const queryParams: Array<[string, string]> = [
    ["X-Amz-Algorithm", "AWS4-HMAC-SHA256"],
    ["X-Amz-Credential", `${config.accessKeyId}/${credentialScope}`],
    ["X-Amz-Date", amzDate],
    ["X-Amz-Expires", String(config.ttlSeconds)],
    ["X-Amz-SignedHeaders", signedHeaders],
  ];

  const canonicalQueryString = buildSignedQueryString(queryParams);
  const canonicalRequest = [
    "GET",
    canonicalUri,
    canonicalQueryString,
    canonicalHeaders,
    signedHeaders,
    "UNSIGNED-PAYLOAD",
  ].join("\n");

  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    credentialScope,
    sha256Hex(canonicalRequest),
  ].join("\n");

  const signingKey = buildSigningKey(config.secretAccessKey, dateStamp);
  const signature = createHmac("sha256", signingKey)
    .update(stringToSign)
    .digest("hex");

  const finalQueryString = buildSignedQueryString(queryParams, signature);
  return `${endpoint.origin}${canonicalUri}?${finalQueryString}`;
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
  return privateObjectUrlWithMetadata(r2Key).url;
}

export function privateObjectUrlWithMetadata(
  r2Key: string,
  now: Date = new Date(),
): PrivateSignedObjectUrl {
  validateR2Key(r2Key);
  validateVariantFileName(r2Key);

  const signingConfig = getPrivateSigningConfig();
  return {
    url: buildSignedPrivateObjectUrl(signingConfig, r2Key, now),
    expiresAt: new Date(
      now.getTime() + signingConfig.ttlSeconds * 1000,
    ).toISOString(),
    ttlSeconds: signingConfig.ttlSeconds,
  };
}

export function privateSignedUrlResponseMaxAgeSeconds(): number {
  const signingConfig = getPrivateSigningConfig();
  return Math.max(1, signingConfig.ttlSeconds - 15);
}

export function privateSignedUrlTtlSeconds(): number {
  return getPrivateSigningConfig().ttlSeconds;
}
