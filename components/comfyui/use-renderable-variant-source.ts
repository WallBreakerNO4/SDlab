"use client";

import { useEffect, useState } from "react";

import {
  loadPrivateImageObjectUrl,
  readCachedPrivateImageObjectUrl,
} from "@/lib/private-image-cache";
import { privateObjectProxyUrl, publicObjectUrl } from "@/lib/r2-url";

import { getPreferredVariantSource } from "./virtual-grid-utils";
import type { VariantSources } from "./virtual-grid-types";

type UseRenderableVariantSourceOptions = {
  variants: VariantSources | null;
  currentUserId: string | null;
  grant: string | null;
  cacheOnly?: boolean;
};

export function useRenderableVariantSource({
  variants,
  currentUserId,
  grant,
  cacheOnly = false,
}: UseRenderableVariantSourceOptions) {
  const preferredVariant = getPreferredVariantSource(variants);
  const cacheKey = preferredVariant?.cache_key ?? null;
  const [privateState, setPrivateState] = useState<{
    cacheKey: string;
    src: string | null;
    loading: boolean;
  } | null>(null);
  const isPrivateVariant = preferredVariant?.bucket === "private";
  const src =
    preferredVariant?.bucket === "public"
      ? publicObjectUrl(preferredVariant.key)
      : currentUserId &&
          grant &&
          cacheKey &&
          privateState?.cacheKey === cacheKey
        ? privateState.src
        : null;
  const loading =
    isPrivateVariant &&
    currentUserId !== null &&
    cacheKey !== null &&
    privateState?.cacheKey === cacheKey
      ? privateState.loading
      : false;

  useEffect(() => {
    if (
      !preferredVariant ||
      preferredVariant.bucket !== "private" ||
      !currentUserId ||
      !grant
    ) {
      return;
    }

    const userId = currentUserId;
    const variant = preferredVariant;
    let active = true;
    let objectUrlToRevoke: string | null = null;
    const controller = new AbortController();
    const variantCacheKey = variant.cache_key;
    const accessGrant = grant;

    async function load() {
      setPrivateState({
        cacheKey: variantCacheKey,
        src: null,
        loading: true,
      });

      try {
        const objectUrl = cacheOnly
          ? await readCachedPrivateImageObjectUrl(
              userId,
              variantCacheKey,
            )
            : variant.key
            ? await loadPrivateImageObjectUrl({
                userId,
                cacheKey: variantCacheKey,
                url: privateObjectProxyUrl(variant.key, accessGrant),
                signal: controller.signal,
              })
            : null;

        if (!active) {
          if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
          }
          return;
        }

        objectUrlToRevoke = objectUrl;
        setPrivateState({
          cacheKey: variantCacheKey,
          src: objectUrl,
          loading: false,
        });
      } catch {
        if (!active) {
          return;
        }
        setPrivateState({
          cacheKey: variantCacheKey,
          src: null,
          loading: false,
        });
      }
    }

    void load();

    return () => {
      active = false;
      controller.abort();
      if (objectUrlToRevoke) {
        URL.revokeObjectURL(objectUrlToRevoke);
      }
    };
  }, [cacheKey, cacheOnly, currentUserId, grant, preferredVariant]);

  return {
    src,
    cacheKey,
    loading,
  } as const;
}
