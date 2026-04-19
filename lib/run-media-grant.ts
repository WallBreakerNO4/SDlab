import { createHmac, timingSafeEqual } from "node:crypto";
import { getServerEnv } from "@/lib/env/server";

export type ViewerVariant = "auth_sfw" | "auth_nsfw";

export type RunMediaGrantClaims = {
  sub: string;
  run_dir: string;
  release_id: string;
  viewer_variant: ViewerVariant;
  media_access_version: number;
  exp: number;
};

function requireGrantSecret(): string {
  return getServerEnv().runMediaGrantSecret;
}

function toBase64Url(value: Buffer | string): string {
  const buffer = Buffer.isBuffer(value) ? value : Buffer.from(value, "utf-8");
  return buffer
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function fromBase64Url(value: string): Buffer {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padding = normalized.length % 4 === 0 ? "" : "=".repeat(4 - (normalized.length % 4));
  return Buffer.from(`${normalized}${padding}`, "base64");
}

function sign(payload: string): string {
  return toBase64Url(createHmac("sha256", requireGrantSecret()).update(payload).digest());
}

export function createRunMediaGrant(claims: RunMediaGrantClaims): string {
  const payload = JSON.stringify(claims);
  const encodedPayload = toBase64Url(payload);
  const signature = sign(encodedPayload);
  return `${encodedPayload}.${signature}`;
}

export function verifyRunMediaGrant(token: string): RunMediaGrantClaims | null {
  const [encodedPayload, encodedSignature] = token.split(".");
  if (!encodedPayload || !encodedSignature) {
    return null;
  }

  const expectedSignature = sign(encodedPayload);
  const actualBuffer = Buffer.from(encodedSignature);
  const expectedBuffer = Buffer.from(expectedSignature);
  if (actualBuffer.length !== expectedBuffer.length) {
    return null;
  }
  if (!timingSafeEqual(actualBuffer, expectedBuffer)) {
    return null;
  }

  try {
    const payload = JSON.parse(fromBase64Url(encodedPayload).toString("utf-8")) as Partial<RunMediaGrantClaims>;
    if (
      typeof payload.sub !== "string" ||
      typeof payload.run_dir !== "string" ||
      typeof payload.release_id !== "string" ||
      (payload.viewer_variant !== "auth_sfw" && payload.viewer_variant !== "auth_nsfw") ||
      typeof payload.media_access_version !== "number" ||
      typeof payload.exp !== "number"
    ) {
      return null;
    }

    if (payload.exp * 1000 <= Date.now()) {
      return null;
    }

    return payload as RunMediaGrantClaims;
  } catch {
    return null;
  }
}
