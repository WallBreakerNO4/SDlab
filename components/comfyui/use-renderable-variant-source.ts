"use client";

import { useEffect, useState } from "react";

import {
  loadPrivateImageObjectUrl,
  PrivateImageLoadError,
  readCachedPrivateImageObjectUrl,
} from "@/lib/private-image-cache";
import { privateObjectProxyUrl, publicObjectUrl } from "@/lib/r2-url";

import { getPreferredVariantSource } from "./virtual-grid-utils";
import type { VariantSources } from "./virtual-grid-types";
import type { RunViewAccess } from "@/app/models/[runDir]/model-detail-types";

// 模块级 objectURL 缓存：cacheKey → objectURL。
// 跨组件挂载/卸载周期持久化，让组件重挂载时能同步拿到 src，
// 避免 blurhash 闪现。由 VirtualGrid 卸载时统一清理。
const objectUrlCache = new Map<string, string>();

/** 清理所有缓存的 objectURL 并清空缓存。在 VirtualGrid 卸载时调用。 */
export function clearPrivateObjectUrlCache() {
  objectUrlCache.forEach((url) => URL.revokeObjectURL(url));
  objectUrlCache.clear();
}

type UseRenderableVariantSourceOptions = {
  variants: VariantSources | null;
  currentUserId: string | null;
  grant: string | null;
  onRefreshViewAccess: () => Promise<RunViewAccess | null>;
  cacheOnly?: boolean;
};

export function useRenderableVariantSource({
  variants,
  currentUserId,
  grant,
  onRefreshViewAccess,
  cacheOnly = false,
}: UseRenderableVariantSourceOptions) {
  const preferredVariant = getPreferredVariantSource(variants);
  const cacheKey = preferredVariant?.cache_key ?? null;
  const [privateState, setPrivateState] = useState<{
    cacheKey: string;
    src: string | null;
    loading: boolean;
  } | null>(() => {
    // 组件重挂载时同步查模块级缓存，命中则直接拿到 src，不显示 blurhash
    if (cacheKey) {
      const cachedUrl = objectUrlCache.get(cacheKey);
      if (cachedUrl) {
        return { cacheKey, src: cachedUrl, loading: false };
      }
    }
    return null;
  });
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
    const controller = new AbortController();
    const variantCacheKey = variant.cache_key;
    const accessGrant = grant;

    /** 将 objectURL 存入模块级缓存，revoke 被替换的旧值。 */
    function storeObjectUrl(key: string, url: string | null) {
      if (!url) return;
      const prev = objectUrlCache.get(key);
      if (prev && prev !== url) {
        URL.revokeObjectURL(prev);
      }
      objectUrlCache.set(key, url);
    }

    async function load() {
      // 模块级缓存命中：同步使用，跳过异步加载，避免 blurhash 闪现
      const cachedUrl = objectUrlCache.get(variantCacheKey);
      if (cachedUrl) {
        setPrivateState({
          cacheKey: variantCacheKey,
          src: cachedUrl,
          loading: false,
        });
        return;
      }

      setPrivateState({
        cacheKey: variantCacheKey,
        src: null,
        loading: true,
      });

      try {
        const objectUrl = cacheOnly
          ? await readCachedPrivateImageObjectUrl(userId, variantCacheKey)
          : variant.key
            ? await loadPrivateImageObjectUrl({
                userId,
                cacheKey: variantCacheKey,
                url: privateObjectProxyUrl(variant.key, accessGrant),
                signal: controller.signal,
              })
            : null;

        if (!active) {
          // 组件已卸载，但把结果存入缓存供下次重挂载使用
          storeObjectUrl(variantCacheKey, objectUrl);
          return;
        }

        storeObjectUrl(variantCacheKey, objectUrl);
        setPrivateState({
          cacheKey: variantCacheKey,
          src: objectUrl,
          loading: false,
        });
      } catch (error) {
        if (
          !cacheOnly &&
          variant.key &&
          error instanceof PrivateImageLoadError &&
          error.status === 403
        ) {
          try {
            const refreshedAccess = await onRefreshViewAccess();
            if (refreshedAccess?.grant && active) {
              const objectUrl = await loadPrivateImageObjectUrl({
                userId,
                cacheKey: variantCacheKey,
                url: privateObjectProxyUrl(variant.key, refreshedAccess.grant),
                signal: controller.signal,
              });

              if (!active) {
                storeObjectUrl(variantCacheKey, objectUrl);
                return;
              }

              storeObjectUrl(variantCacheKey, objectUrl);
              setPrivateState({
                cacheKey: variantCacheKey,
                src: objectUrl,
                loading: false,
              });
              return;
            }
          } catch {
            // Fall through to the normal failed-image state below.
          }
        }

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
      // 不 revoke objectURL，保留在模块级缓存中供组件重挂载时同步复用。
      // 缓存在 VirtualGrid 卸载时统一清理。
    };
  }, [
    cacheKey,
    cacheOnly,
    currentUserId,
    grant,
    onRefreshViewAccess,
    preferredVariant,
  ]);

  return {
    src,
    cacheKey,
    loading,
  } as const;
}
