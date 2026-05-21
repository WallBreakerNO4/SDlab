"use client";

const PRIVATE_IMAGE_CACHE_NAME_PREFIX = "sd-style-lab:private-images:v1:";
const PRIVATE_IMAGE_CACHE_REQUEST_PATH = "/__private-image-cache__/";

export class PrivateImageLoadError extends Error {
  constructor(public readonly status: number) {
    super(`Failed to load private image: ${status}`);
    this.name = "PrivateImageLoadError";
  }
}

function buildCacheName(userId: string): string {
  return `${PRIVATE_IMAGE_CACHE_NAME_PREFIX}${userId}`;
}

function buildCacheRequestUrl(cacheKey: string): string {
  return new URL(
    `${PRIVATE_IMAGE_CACHE_REQUEST_PATH}${encodeURIComponent(cacheKey)}`,
    window.location.origin,
  ).toString();
}

async function openUserCache(userId: string): Promise<Cache | null> {
  if (
    typeof window === "undefined" ||
    typeof window.caches === "undefined" ||
    userId.trim().length === 0
  ) {
    return null;
  }

  return window.caches.open(buildCacheName(userId));
}

async function createObjectUrlFromResponse(response: Response): Promise<string> {
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function readCachedPrivateImageObjectUrl(
  userId: string,
  cacheKey: string,
): Promise<string | null> {
  const cache = await openUserCache(userId);
  if (!cache) {
    return null;
  }

  const response = await cache.match(buildCacheRequestUrl(cacheKey));
  if (!response) {
    return null;
  }

  return createObjectUrlFromResponse(response);
}

export async function loadPrivateImageObjectUrl(params: {
  userId: string;
  cacheKey: string;
  url: string;
  signal?: AbortSignal;
}): Promise<string> {
  const { userId, cacheKey, url, signal } = params;
  const cache = await openUserCache(userId);
  const cacheRequestUrl = buildCacheRequestUrl(cacheKey);

  if (cache) {
    const cached = await cache.match(cacheRequestUrl);
    if (cached) {
      return createObjectUrlFromResponse(cached);
    }
  }

  const response = await fetch(url, {
    mode: "cors",
    credentials: "same-origin",
    signal,
  });

  if (!response.ok) {
    throw new PrivateImageLoadError(response.status);
  }

  if (cache) {
    await cache.put(cacheRequestUrl, response.clone());
  }

  return createObjectUrlFromResponse(response);
}

export async function clearAllPrivateImageCaches(): Promise<void> {
  if (typeof window === "undefined" || typeof window.caches === "undefined") {
    return;
  }

  const cacheNames = await window.caches.keys();
  await Promise.all(
    cacheNames
      .filter((cacheName) =>
        cacheName.startsWith(PRIVATE_IMAGE_CACHE_NAME_PREFIX),
      )
      .map((cacheName) => window.caches.delete(cacheName)),
  );
}
