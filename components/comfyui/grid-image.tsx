"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { BlurhashCanvas } from "./blurhash-canvas"

import { type VariantUrls } from "./virtual-grid"

type GridImageProps = {
  thumbVariants: VariantUrls
  blurhash: string | null
  alt: string
}

export function GridImage({ thumbVariants, blurhash, alt }: GridImageProps) {
  const [isLoaded, setIsLoaded] = useState(false)

  return (
    <div className="relative h-full w-full overflow-hidden">
      {blurhash && (
        <BlurhashCanvas
          blurhash={blurhash}
          className={cn(
            "absolute inset-0 h-full w-full object-cover blur-md transition-opacity duration-500",
            isLoaded ? "opacity-0" : "opacity-100"
          )}
        />
      )}
      <picture>
        {thumbVariants.avif ? (
          <source srcSet={thumbVariants.avif} type="image/avif" />
        ) : null}
        {thumbVariants.webp ? (
          <source srcSet={thumbVariants.webp} type="image/webp" />
        ) : null}
        <img
          alt={alt}
          className={cn(
            "relative z-10 h-full w-full object-contain transition-opacity duration-500",
            isLoaded ? "opacity-100" : "opacity-0"
          )}
          data-testid="run-grid-image"
          loading="lazy"
          decoding="async"
          src={thumbVariants.webp ?? thumbVariants.avif ?? ""}
          onLoad={() => setIsLoaded(true)}
        />
      </picture>
    </div>
  )
}
