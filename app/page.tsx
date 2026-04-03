"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { BlurhashCanvas } from "@/components/comfyui/blurhash-canvas";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";

import type { RunAssetSummary, RunSummary } from "@/lib/comfyui-types";

type LoadState = "loading" | "ready" | "error";

function isRunSummary(value: unknown): value is RunSummary {
  if (!value || typeof value !== "object") {
    return false;
  }
  const run = value as Partial<RunSummary>;
  const hasBasicFields =
    typeof run.run_id === "string" &&
    typeof run.run_dir === "string" &&
    typeof run.created_at === "string" &&
    typeof run.x_count === "number" &&
    typeof run.y_count === "number" &&
    typeof run.total_cells === "number";
  if (!hasBasicFields) return false;

  if ("model" in run && run.model !== undefined && run.model !== null) {
    if (typeof run.model !== "object") return false;
  }
  if ("assets" in run && run.assets !== undefined && run.assets !== null) {
    if (typeof run.assets !== "object") return false;
    const assets = run.assets as Record<string, unknown>;
    if (
      "cover" in assets &&
      assets.cover !== undefined &&
      assets.cover !== null
    ) {
      if (typeof assets.cover !== "object") return false;
    }
    if (
      "homepage_cards" in assets &&
      assets.homepage_cards !== undefined &&
      assets.homepage_cards !== null
    ) {
      if (!Array.isArray(assets.homepage_cards)) return false;
    }
  }

  return true;
}

function formatCreatedAt(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) {
    return createdAt;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

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
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ease-out ${
            isLoaded ? "opacity-0" : "opacity-100"
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
            className={`${imgClassName || ""} ${
              isLoaded ? "opacity-100" : "opacity-0"
            }`}
            loading="lazy"
            onLoad={() => setIsLoaded(true)}
          />
        </picture>
      ) : null}
    </>
  );
}

function RunsSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
      {[1, 2, 3].map((id) => (
        <Card
          key={id}
          className="flex flex-col overflow-hidden rounded-none border-border/40 bg-card/50"
        >
          <Skeleton className="aspect-[16/10] w-full rounded-none" />
          <CardContent className="flex flex-1 flex-col justify-between space-y-6 p-6">
            <div className="space-y-3">
              <Skeleton className="h-7 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
            <div className="flex gap-2 overflow-hidden pt-4">
              <Skeleton className="h-20 w-16 shrink-0" />
              <Skeleton className="h-20 w-16 shrink-0" />
              <Skeleton className="h-20 w-16 shrink-0" />
            </div>
            <div className="flex items-center justify-between pt-4 border-t border-border/40 mt-2">
              <div className="flex gap-2">
                <Skeleton className="h-6 w-16" />
                <Skeleton className="h-6 w-16" />
              </div>
              <Skeleton className="h-4 w-24" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function Page() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");

  useEffect(() => {
    const abortController = new AbortController();

    async function fetchRuns() {
      setLoadState("loading");
      try {
        const response = await fetch("/api/comfyui/runs", {
          signal: abortController.signal,
        });

        if (!response.ok) {
          throw new Error("Failed to load runs");
        }

        const data: unknown = await response.json();

        if (!Array.isArray(data)) {
          throw new Error("Unexpected runs payload");
        }

        setRuns(data.filter(isRunSummary));
        setLoadState("ready");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setRuns([]);
        setLoadState("error");
      }
    }

    void fetchRuns();

    return () => {
      abortController.abort();
    };
  }, []);

  const isLoading = loadState === "loading";
  const isEmpty = !isLoading && runs.length === 0;

  return (
    <main className="relative h-full w-full flex flex-col items-center selection:bg-primary/20 selection:text-primary overflow-y-auto">
      {/* Decorative Grid Background - refined opacity */}
      <div className="pointer-events-none absolute inset-0 flex justify-center z-[-1]">
        <div className="w-full h-full bg-[linear-gradient(to_right,var(--color-border)_1px,transparent_1px),linear-gradient(to_bottom,var(--color-border)_1px,transparent_1px)] bg-[size:32px_32px] opacity-20 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,#000_60%,transparent_100%)]"></div>
      </div>

      {/* Decorative Glow */}
      <div className="pointer-events-none absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] opacity-10 dark:opacity-20 mix-blend-screen blur-[100px] rounded-full bg-primary/30 z-[-1]"></div>

      <div className="w-full max-w-7xl px-4 md:px-8 py-24 md:py-32 flex flex-col gap-32">
        {/* Hero Section */}
        <section className="animate-fade-in-up flex flex-col items-start gap-8 max-w-3xl">
          <div className="flex flex-col space-y-6">
            <div className="flex items-center">
              <Badge
                variant="outline"
                className="px-3 py-1 font-mono text-[10px] tracking-[0.2em] border-primary/20 text-primary bg-primary/5 rounded-none uppercase flex items-center gap-2"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                Stable Diffusion Research
              </Badge>
            </div>

            <h1 className="text-5xl md:text-7xl font-black tracking-tight leading-[1.05] text-foreground">
              AI 图像风格
              <span className="block mt-1 bg-gradient-to-br from-primary to-primary/40 bg-clip-text text-transparent">
                实验室
              </span>
            </h1>
          </div>

          <p className="text-lg md:text-xl text-muted-foreground leading-relaxed max-w-2xl font-light">
            系统化的 Stable Diffusion
            模型评估平台。通过结构化参数网格与风格组合实验，沉淀可复现的生成数据与最优实践。
          </p>

          <div className="flex flex-wrap items-center gap-3 mt-2">
            <div className="flex items-center gap-2 text-xs font-mono border border-border/50 bg-background/50 backdrop-blur-sm px-4 py-2 text-muted-foreground">
              <span className="text-primary font-bold">⊞</span> 结构化网格
            </div>
            <div className="flex items-center gap-2 text-xs font-mono border border-border/50 bg-background/50 backdrop-blur-sm px-4 py-2 text-muted-foreground">
              <span className="text-primary font-bold">⌘</span> 多维对比
            </div>
            <div className="flex items-center gap-2 text-xs font-mono border border-border/50 bg-background/50 backdrop-blur-sm px-4 py-2 text-muted-foreground">
              <span className="text-primary font-bold">⎋</span> 数据沉淀
            </div>
          </div>
        </section>

        {/* Runs Section */}
        <section className="w-full flex flex-col gap-10">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between border-b border-border/40 pb-5 gap-4">
            <div className="space-y-1">
              <h2 className="text-2xl md:text-3xl font-bold tracking-tight">
                最新实验记录
              </h2>
              <p className="text-sm text-muted-foreground">
                浏览最近运行的模型评测与风格网格
              </p>
            </div>
            {!isLoading && !isEmpty && (
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-muted-foreground font-mono text-[10px] tracking-widest uppercase border border-border/40 px-2 py-1 bg-muted/20">
                  {runs.length} Records Found
                </span>
              </div>
            )}
          </div>

          {isLoading ? <RunsSkeleton /> : null}

          {isEmpty ? (
            <Empty className="py-24 border border-dashed border-border/50 bg-background/30 backdrop-blur-sm">
              <EmptyHeader>
                <EmptyTitle className="text-xl">
                  {loadState === "error" ? "加载失败" : "暂无实验记录"}
                </EmptyTitle>
                <EmptyDescription className="text-sm max-w-sm mx-auto">
                  {loadState === "error"
                    ? "请稍后刷新重试，或检查 API 服务状态。"
                    : "暂无可用 runs 数据，等待后端数据同步。"}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}

          {!isLoading && runs.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
              {runs.map((run, index) => {
                const modelName = run.model?.name || run.run_dir;
                const modelDesc =
                  run.model?.description?.zh || run.model?.description?.en;

                const coverAsset = run.assets?.cover;
                const coverSource = resolvePreferredImageSource(coverAsset);
                const homepageCards = (run.assets?.homepage_cards || []).slice(
                  0,
                  5,
                );

                const coverRatio =
                  coverAsset?.width && coverAsset?.height
                    ? `${coverAsset.width} / ${coverAsset.height}`
                    : "16 / 10";

                return (
                  <Link
                    key={run.run_dir}
                    href={`/runs/${encodeURIComponent(run.run_dir)}`}
                    className="group animate-fade-in-up block outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                    style={{
                      animationFillMode: "forwards",
                      opacity: 0,
                      animationDelay: `${index * 80}ms`,
                    }}
                  >
                    <Card className="h-full flex flex-col transition-all duration-300 hover:ring-1 hover:ring-primary/40 hover:shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:hover:shadow-[0_8px_30px_rgba(255,255,255,0.02)] border-border/40 bg-card/80 backdrop-blur-sm rounded-none overflow-hidden relative">
                      {/* Top accent line */}
                      <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-primary/30 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 z-10" />

                      {/* Image Area */}
                      <div
                        className="relative w-full overflow-hidden bg-muted/40 border-b border-border/40"
                        style={{ aspectRatio: coverRatio }}
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

                        {/* Overlay Gradient for contrast */}
                        <div className="absolute inset-0 bg-gradient-to-t from-background/80 via-background/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

                        <div className="absolute bottom-4 right-4 translate-x-2 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 transition-all duration-300 ease-out text-primary">
                          <span className="font-bold text-xl leading-none">
                            →
                          </span>
                        </div>
                      </div>

                      {/* Content Area */}
                      <CardContent className="flex flex-1 flex-col justify-between p-6 gap-6">
                        <div className="space-y-3">
                          <div className="space-y-1">
                            <h3 className="text-xl font-bold tracking-tight group-hover:text-primary transition-colors line-clamp-1">
                              {modelName}
                            </h3>
                            <div className="text-muted-foreground/50 font-mono text-[10px] truncate uppercase tracking-widest">
                              {run.run_dir}
                            </div>
                          </div>

                          {modelDesc ? (
                            <p className="text-sm text-muted-foreground/70 line-clamp-2 leading-relaxed">
                              {modelDesc}
                            </p>
                          ) : null}
                        </div>

                        <div className="space-y-6">
                          {/* Mini Previews */}
                          {homepageCards.length > 0 && (
                            <div className="flex gap-2 overflow-x-auto pb-1 pt-2 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none] snap-x">
                              {homepageCards.map((thumbAsset, idx) => {
                                const thumbSource =
                                  resolvePreferredImageSource(thumbAsset);
                                if (!thumbSource?.imgSrc) return null;

                                const thumbRatio =
                                  thumbAsset.width && thumbAsset.height
                                    ? `${thumbAsset.width} / ${thumbAsset.height}`
                                    : "2/3";

                                return (
                                  <div
                                    key={thumbSource.imgSrc || idx}
                                    className="relative h-20 shrink-0 overflow-hidden bg-muted/30 border border-border/40 snap-center group/thumb"
                                    style={{ aspectRatio: thumbRatio }}
                                  >
                                    <CardImage
                                      src={thumbSource.imgSrc}
                                      avif={thumbSource.avifSrc}
                                      webp={thumbSource.webpSrc}
                                      alt=""
                                      blurhash={thumbAsset.blurhash}
                                      blurhashWidth={thumbAsset.blurhash_width}
                                      blurhashHeight={
                                        thumbAsset.blurhash_height
                                      }
                                      imgClassName="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover/thumb:scale-110"
                                    />
                                  </div>
                                );
                              })}
                            </div>
                          )}

                          {/* Footer Info */}
                          <div className="flex items-center justify-between pt-4 border-t border-border/30">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-[10px] px-2 py-0.5 bg-muted/50 border border-border/40 text-foreground">
                                {run.x_count}×{run.y_count}
                              </span>
                              <span className="font-mono text-[10px] px-2 py-0.5 border border-border/30 text-muted-foreground">
                                {run.total_cells} ITEMS
                              </span>
                            </div>
                            <time
                              dateTime={run.created_at}
                              className="text-muted-foreground/70 font-mono text-[10px] tracking-wider uppercase"
                            >
                              {formatCreatedAt(run.created_at)}
                            </time>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                );
              })}
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
