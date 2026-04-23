import "server-only";

type R2HttpMetadataLike = {
  contentType?: unknown;
  contentLanguage?: unknown;
  contentDisposition?: unknown;
  contentEncoding?: unknown;
  cacheControl?: unknown;
  cacheExpiry?: unknown;
};

type R2ObjectWithMetadata = {
  httpMetadata?: R2HttpMetadataLike | null;
};

function setStringHeader(
  headers: Headers,
  name: string,
  value: unknown,
): void {
  if (typeof value !== "string") {
    return;
  }

  const trimmed = value.trim();
  if (trimmed.length > 0) {
    headers.set(name, trimmed);
  }
}

function setExpiresHeader(headers: Headers, value: unknown): void {
  if (value instanceof Date) {
    headers.set("Expires", value.toUTCString());
    return;
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length > 0) {
      headers.set("Expires", trimmed);
    }
  }
}

export function writeR2HttpMetadata(
  headers: Headers,
  object: R2ObjectWithMetadata,
): void {
  // Avoid object.writeHttpMetadata(headers): OpenNext local R2 proxy cannot serialize Headers.
  const metadata = object.httpMetadata;
  if (!metadata) {
    return;
  }

  setStringHeader(headers, "Content-Type", metadata.contentType);
  setStringHeader(headers, "Content-Language", metadata.contentLanguage);
  setStringHeader(headers, "Content-Disposition", metadata.contentDisposition);
  setStringHeader(headers, "Content-Encoding", metadata.contentEncoding);
  setStringHeader(headers, "Cache-Control", metadata.cacheControl);
  setExpiresHeader(headers, metadata.cacheExpiry);
}
