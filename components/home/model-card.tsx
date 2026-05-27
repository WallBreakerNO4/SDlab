"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { BlurhashCanvas } from "@/components/comfyui/blurhash-canvas";
import { Card, CardContent } from "@/components/ui/card";
import { Link } from "@/i18n/navigation";

import type { RunAssetSummary, RunSummary } from "@/lib/comfyui-types";

function resolvePreferredImageSource(
  asset: RunAssetSummary | null | undefined,
) {
  if (!asset) return null;

  const display = asset.display;
  if (display?.avif || display?.webp) {
    return {
      avifSrc: display.avif ?? null,
      webpSrc: display.webp ?? null,
      imgSrc: display.webp ?? display.avif ?? null,
    };
  }

  const thumb = asset.thumb;
  if (thumb?.avif || thumb?.webp) {
    return {
      avifSrc: thumb.avif ?? null,
      webpSrc: thumb.webp ?? null,
      imgSrc: thumb.webp ?? thumb.avif ?? null,
    };
  }

  return null;
}

function CardImage({
  src,
  avif,
  webp,
  alt,
  blurhash,
  blurhashWidth,
  blurhashHeight,
  imgClassName,
}: {
  src?: string | null;
  avif?: string | null;
  webp?: string | null;
  alt: string;
  blurhash?: string | null;
  blurhashWidth?: number | null;
  blurhashHeight?: number | null;
  imgClassName?: string;
}) {
  const [isLoaded, setIsLoaded] = useState(false);

  return (
    <>
      {blurhash ? (
        <BlurhashCanvas
          blurhash={blurhash}
          width={blurhashWidth || 32}
          height={blurhashHeight || 32}
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ease-out ${isLoaded ? "opacity-0" : "opacity-100"
            }`}
        />
      ) : null}
      {src ? (
        <picture>
          {avif && <source srcSet={avif} type="image/avif" />}
          {webp && <source srcSet={webp} type="image/webp" />}
          <img
            ref={(node) => {
              if (node?.complete) {
                setIsLoaded(true);
              }
            }}
            src={src}
            alt={alt}
            className={`${imgClassName || ""} ${isLoaded ? "opacity-100" : "opacity-0"
              }`}
            loading="lazy"
            onLoad={() => setIsLoaded(true)}
          />
        </picture>
      ) : null}
    </>
  );
}

function ExpandableDescription({ text }: { text: string }) {
  const t = useTranslations("modelCard");
  const [isExpanded, setIsExpanded] = useState(false);
  const [isTruncated, setIsTruncated] = useState(false);
  const textRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (textRef.current) {
      setIsTruncated(
        textRef.current.scrollHeight > textRef.current.clientHeight,
      );
    }
  }, [text]);

  return (
    <div className="relative">
      <p
        ref={textRef}
        className={`text-sm text-muted-foreground/70 leading-relaxed ${isExpanded ? "pb-6" : "line-clamp-2"
          }`}
      >
        {text}
      </p>
      {isTruncated && (
        <div
          className={`absolute bottom-0 right-0 flex items-center justify-end ${isExpanded
            ? ""
            : "w-20 h-6 bg-linear-to-r from-transparent via-card/90 to-card"
            }`}
        >
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setIsExpanded((prev) => !prev);
            }}
            className="flex items-center justify-center p-1 text-muted-foreground hover:text-primary transition-colors focus:outline-none cursor-pointer"
            title={isExpanded ? t("collapse") : t("expand")}
          >
            {isExpanded ? (
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m18 15-6-6-6 6" />
              </svg>
            ) : (
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

function getFullResUrl(
  asset: RunAssetSummary | null | undefined,
): string | null {
  if (!asset) return null;
  return (
    asset.display?.webp ??
    asset.display?.avif ??
    asset.thumb?.webp ??
    asset.thumb?.avif ??
    null
  );
}

function HorizontalScrollList({
  assets,
  onImageClick,
}: {
  assets: RunAssetSummary[];
  onImageClick: (url: string) => void;
}) {
  const t = useTranslations("modelCard");
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTimeout = useRef<NodeJS.Timeout | null>(null);

  const copyCount = Math.max(5, Math.ceil(20 / Math.max(assets.length, 1)));
  const displayAssets = Array.from({ length: copyCount }, () => assets).flat();
  const middleCopyIndex = Math.floor(copyCount / 2);

  useEffect(() => {
    if (scrollRef.current && assets.length > 0) {
      const el = scrollRef.current;
      const items = el.querySelectorAll<HTMLElement>(
        ":scope > div.group\\/thumb",
      );
      if (items.length >= assets.length * copyCount) {
        const firstItem = items[0];
        const middleItem = items[assets.length * middleCopyIndex];
        if (firstItem && middleItem) {
          const shift = middleItem.offsetLeft - firstItem.offsetLeft;
          el.scrollLeft = shift;
        }
      }
    }
  }, [assets.length, copyCount, middleCopyIndex]);

  const handleScrollEvent = () => {
    if (!scrollRef.current || assets.length === 0) return;
    const el = scrollRef.current;

    if (scrollTimeout.current) clearTimeout(scrollTimeout.current);

    scrollTimeout.current = setTimeout(() => {
      if (!el) return;
      const items = el.querySelectorAll<HTMLElement>(
        ":scope > div.group\\/thumb",
      );
      if (items.length < assets.length * 2) return;

      const firstItem = items[0];
      const secondBlockItem = items[assets.length];
      const segmentWidth = secondBlockItem.offsetLeft - firstItem.offsetLeft;

      if (segmentWidth <= 0) return;

      const centerPos = segmentWidth * middleCopyIndex;
      if (Math.abs(el.scrollLeft - centerPos) > segmentWidth) {
        const offset = centerPos - el.scrollLeft;
        const k = Math.round(offset / segmentWidth);
        el.scrollLeft += k * segmentWidth;
      }
    }, 150);
  };

  const scroll = (direction: "left" | "right", e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (scrollRef.current) {
      const scrollAmount = direction === "left" ? -300 : 300;
      scrollRef.current.scrollBy({ left: scrollAmount, behavior: "smooth" });
    }
  };

  if (!assets.length) return null;

  return (
    <div className="relative group/list flex items-center">
      <button
        onClick={(e) => scroll("left", e)}
        className="absolute left-0 z-20 bg-background/80 hover:bg-background text-foreground shadow-sm rounded-r-md p-1 opacity-0 group-hover/list:opacity-100 transition-opacity cursor-pointer"
        aria-label={t("scrollLeft")}
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m15 18-6-6-6 6" />
        </svg>
      </button>

      <div
        ref={scrollRef}
        onScroll={handleScrollEvent}
        className="flex gap-2 overflow-x-auto pb-1 pt-2 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] scrollbar-none snap-x w-full relative"
      >
        {displayAssets.map((thumbAsset, idx) => {
          const thumbSource = resolvePreferredImageSource(thumbAsset);
          if (!thumbSource?.imgSrc) return null;

          const thumbRatio =
            thumbAsset.width && thumbAsset.height
              ? `${thumbAsset.width} / ${thumbAsset.height}`
              : "2/3";

          return (
            <div
              key={`${thumbSource.imgSrc || ""}-${idx}`}
              className="relative h-32 shrink-0 overflow-hidden bg-muted/30 border border-border/40 snap-center group/thumb cursor-zoom-in"
              style={{ aspectRatio: thumbRatio }}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                const url = getFullResUrl(thumbAsset);
                if (url) onImageClick(url);
              }}
              title={t("viewLarge")}
            >
              <CardImage
                src={thumbSource.imgSrc}
                avif={thumbSource.avifSrc}
                webp={thumbSource.webpSrc}
                alt=""
                blurhash={thumbAsset.blurhash}
                blurhashWidth={thumbAsset.blurhash_width}
                blurhashHeight={thumbAsset.blurhash_height}
                imgClassName="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover/thumb:scale-110"
              />
            </div>
          );
        })}
      </div>

      <button
        onClick={(e) => scroll("right", e)}
        className="absolute right-0 z-20 bg-background/80 hover:bg-background text-foreground shadow-sm rounded-l-md p-1 opacity-0 group-hover/list:opacity-100 transition-opacity cursor-pointer"
        aria-label={t("scrollRight")}
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="m9 18 6-6-6-6" />
        </svg>
      </button>
    </div>
  );
}

type ModelCardProps = {
  index: number;
  modelSummary: RunSummary;
  onPreviewImage: (url: string) => void;
};

export function ModelCard({
  index,
  modelSummary,
  onPreviewImage,
}: ModelCardProps) {
  const t = useTranslations("modelCard");
  const modelName = modelSummary.model?.name || modelSummary.run_dir;
  const modelDesc =
    modelSummary.model?.description?.zh || modelSummary.model?.description?.en;

  const coverAsset = modelSummary.assets?.cover;
  const coverSource = resolvePreferredImageSource(coverAsset);
  const homepageCards = modelSummary.assets?.homepage_cards || [];

  const coverRatio =
    coverAsset?.width && coverAsset?.height
      ? `${coverAsset.width} / ${coverAsset.height}`
      : "16 / 10";

  return (
    <Link
      href={`/models/${encodeURIComponent(modelSummary.run_dir)}`}
      className="group animate-fade-in-up block outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      style={{
        animationFillMode: "forwards",
        opacity: 0,
        animationDelay: `${index * 80}ms`,
      }}
    >
      <Card className="flex flex-col transition-colors duration-300 hover:ring-1 hover:ring-primary/40 hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:hover:shadow-[0_8px_30px_rgba(255,255,255,0.02)] border-border/40 bg-card/80 [-webkit-backdrop-filter:blur(8px)] backdrop-blur-sm rounded-none overflow-hidden relative p-0 gap-0">
        <div className="absolute top-0 left-0 w-full h-0.5 bg-linear-to-r from-transparent via-primary/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 z-10" />

        <div
          className="relative w-full overflow-hidden bg-muted/40 border-b border-border/40 cursor-zoom-in will-change-transform"
          style={{ aspectRatio: coverRatio }}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            const url = getFullResUrl(coverAsset);
            if (url) onPreviewImage(url);
          }}
          title={t("viewLarge")}
        >
          <CardImage
            src={coverSource?.imgSrc}
            avif={coverSource?.avifSrc}
            webp={coverSource?.webpSrc}
            alt={modelName}
            blurhash={coverAsset?.blurhash}
            blurhashWidth={coverAsset?.blurhash_width}
            blurhashHeight={coverAsset?.blurhash_height}
            imgClassName="absolute inset-0 h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
          />

          <div className="absolute inset-0 bg-linear-to-t from-background/80 via-background/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

          <div className="absolute bottom-4 right-4 translate-x-2 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 transition-[transform,opacity] duration-300 ease-out text-primary">
            <span className="font-bold text-xl leading-none">→</span>
          </div>
        </div>

        <CardContent className="flex flex-1 flex-col justify-between p-6 gap-6">
          <div className="space-y-3">
            <h3 className="text-xl font-bold tracking-tight group-hover:text-primary transition-colors wrap-break-word">
              {modelName}
            </h3>

            {modelDesc ? <ExpandableDescription text={modelDesc} /> : null}
          </div>

          <div className="space-y-6">
            {homepageCards.length > 0 ? (
              <HorizontalScrollList
                assets={homepageCards}
                onImageClick={onPreviewImage}
              />
            ) : null}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
