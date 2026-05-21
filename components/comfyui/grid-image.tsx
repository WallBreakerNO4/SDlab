"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { BlurhashCanvas } from "./blurhash-canvas";
import { useRenderableVariantSource } from "./use-renderable-variant-source";
import { getPreferredVariantSource } from "./virtual-grid-utils";

import type { VariantSources } from "./virtual-grid";

type GridImageProps = {
  thumbVariants: VariantSources | null;
  blurhash: string | null;
  alt: string;
  currentUserId: string | null;
  grant: string | null;
  /** When true, show only the blurhash with a lock overlay instead of the real image. */
  locked?: boolean;
  /** Callback when the locked overlay is clicked. */
  onLockedClick?: () => void;
  onImageLoaded?: (cacheKey: string) => void;
  /** Global set of already-loaded image cache keys, persisted across re-renders. */
  globallyLoadedKeys?: Set<string>;
};

export function GridImage({
  thumbVariants,
  blurhash,
  alt,
  currentUserId,
  grant,
  locked,
  onLockedClick,
  onImageLoaded,
  globallyLoadedKeys,
}: GridImageProps) {
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const preferredVariant = getPreferredVariantSource(thumbVariants);
  const { src, cacheKey: privateCacheKey } =
    useRenderableVariantSource({
      variants: thumbVariants,
      currentUserId,
      grant,
    });
  const isGloballyLoaded =
    privateCacheKey && globallyLoadedKeys
      ? globallyLoadedKeys.has(privateCacheKey)
      : false;
  const isLoaded = src !== null && (loadedSrc === src || isGloballyLoaded);

  if (locked) {
    return (
      <div className="relative h-full w-full overflow-hidden">
        {blurhash ? (
          <BlurhashCanvas
            blurhash={blurhash}
            className="absolute inset-0 h-full w-full object-cover blur-md"
          />
        ) : (
          <div className="bg-muted/60 absolute inset-0" />
        )}
        <button
          type="button"
          className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-1"
          aria-label="需要登录才能查看"
          onClick={onLockedClick}
        >
          <svg
            className="text-foreground/70 size-6"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
          <span className="text-foreground/70 text-[10px] font-medium">
            需要登录
          </span>
        </button>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full overflow-hidden">
      {blurhash && (
        <BlurhashCanvas
          blurhash={blurhash}
          className={cn(
            "absolute inset-0 h-full w-full object-cover blur-md transition-opacity duration-500",
            isLoaded ? "opacity-0" : "opacity-100",
          )}
        />
      )}
      {src ? (
        <picture>
          <img
            alt={alt}
            className={cn(
              "relative z-10 h-full w-full object-contain transition-opacity duration-500",
              isLoaded ? "opacity-100" : "opacity-0",
            )}
            data-testid="run-grid-image"
            decoding="async"
            src={src}
            onLoad={() => {
              setLoadedSrc(src);
              const cacheKey =
                privateCacheKey ??
                preferredVariant?.cache_key ??
                null;
              if (cacheKey) {
                globallyLoadedKeys?.add(cacheKey);
                onImageLoaded?.(cacheKey);
              }
            }}
          />
        </picture>
      ) : null}
    </div>
  );
}
