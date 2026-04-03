"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { BlurhashCanvas } from "./blurhash-canvas";

import type { VariantUrls } from "./virtual-grid";

type GridImageProps = {
  thumbVariants: VariantUrls | null;
  blurhash: string | null;
  alt: string;
  /** When true, show only the blurhash with a lock overlay instead of the real image. */
  locked?: boolean;
  /** Callback when the locked overlay is clicked. */
  onLockedClick?: () => void;
};

export function GridImage({
  thumbVariants,
  blurhash,
  alt,
  locked,
  onLockedClick,
}: GridImageProps) {
  const [isLoaded, setIsLoaded] = useState(false);

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

  const src = thumbVariants?.webp ?? thumbVariants?.avif;

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
          {thumbVariants?.avif ? (
            <source srcSet={thumbVariants.avif} type="image/avif" />
          ) : null}
          {thumbVariants?.webp ? (
            <source srcSet={thumbVariants.webp} type="image/webp" />
          ) : null}
          <img
            alt={alt}
            className={cn(
              "relative z-10 h-full w-full object-contain transition-opacity duration-500",
              isLoaded ? "opacity-100" : "opacity-0",
            )}
            data-testid="run-grid-image"
            decoding="async"
            src={src}
            onLoad={() => setIsLoaded(true)}
          />
        </picture>
      ) : null}
    </div>
  );
}
