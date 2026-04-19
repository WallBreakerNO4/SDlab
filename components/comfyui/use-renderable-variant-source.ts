"use client";

import { useEffect, useState } from "react";

import {
  loadPrivateImageObjectUrl,
  readCachedPrivateImageObjectUrl,
} from "@/lib/private-image-cache";

import { getPreferredVariantSource } from "./virtual-grid-utils";
import type { VariantSources } from "./virtual-grid-types";

type UseRenderableVariantSourceOptions = {
  variants: VariantSources | null;
  currentUserId: string | null;
  cacheOnly?: boolean;
};

export function useRenderableVariantSource({
  variants,
  currentUserId,
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
      ? preferredVariant.url ?? null
      : currentUserId &&
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
    if (!preferredVariant || preferredVariant.bucket !== "private" || !currentUserId) {
      return;
    }

    const userId = currentUserId;
    const variant = preferredVariant;
    let active = true;
    let objectUrlToRevoke: string | null = null;
    const controller = new AbortController();
    const variantCacheKey = variant.cache_key;

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
          : variant.url
            ? await loadPrivateImageObjectUrl({
                userId,
                cacheKey: variantCacheKey,
                url: variant.url,
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
  }, [cacheKey, cacheOnly, currentUserId, preferredVariant]);

  return {
    src,
    cacheKey,
    loading,
  } as const;
}
