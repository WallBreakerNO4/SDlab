"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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

  return (
    typeof run.run_id === "string" &&
    typeof run.run_dir === "string" &&
    typeof run.created_at === "string" &&
    typeof run.x_count === "number" &&
    typeof run.y_count === "number" &&
    typeof run.total_cells === "number"
  );
}

function formatCreatedAt(createdAt: string): string {
  const date = new Date(createdAt);

  if (Number.isNaN(date.getTime())) {
    return createdAt;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
}

function resolvePreferredImageSource(
  asset: RunAssetSummary | null | undefined,
) {
  if (!asset) {
    return null;
  }

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

function selectCardAsset(run: RunSummary) {
  const candidates = [run.assets?.cover, ...(run.assets?.homepage_cards ?? [])];

  for (const candidate of candidates) {
    const source = resolvePreferredImageSource(candidate);
    if (source?.imgSrc) {
      return {
        asset: candidate ?? null,
        source,
      };
    }
  }

  return {
    asset: null,
    source: null,
  };
}

function RunsSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {[1, 2, 3].map((id) => (
        <Card key={id} className="flex flex-col overflow-hidden">
          <Skeleton className="aspect-video w-full rounded-none" />
          <CardContent className="flex flex-1 flex-col justify-between space-y-4 p-6">
            <div className="space-y-3">
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-4 w-full" />
            </div>
            <div className="flex items-center justify-between pt-2">
              <div className="flex gap-2">
                <Skeleton className="h-5 w-16" />
                <Skeleton className="h-5 w-16" />
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
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 overflow-auto p-4 md:p-8">
      <div className="animate-fade-in-up space-y-4 text-center">
        <h1 className="bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-4xl font-bold tracking-tight text-transparent md:text-5xl">
          AI 图像风格实验室
        </h1>
        <p className="text-muted-foreground text-xl">
          探索 Stable Diffusion 风格组合，发现无限创意可能
        </p>
      </div>

      <div className="space-y-8">
        {isLoading ? <RunsSkeleton /> : null}

        {isEmpty ? (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>
                {loadState === "error" ? "加载失败" : "暂无可用 runs"}
              </EmptyTitle>
              <EmptyDescription>
                {loadState === "error"
                  ? "请稍后刷新重试。"
                  : "暂无可用 runs，请确认数据源已配置。"}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}

        {!isLoading && runs.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {runs.map((run, index) => {
              const modelName = run.model?.name || run.run_dir;
              const modelDesc =
                run.model?.description?.zh || run.model?.description?.en;
              const { source } = selectCardAsset(run);
              const webpSrc = source?.webpSrc ?? null;
              const avifSrc = source?.avifSrc ?? null;
              const imgSrc = source?.imgSrc ?? null;

              return (
                <Link
                  key={run.run_dir}
                  href={`/runs/${encodeURIComponent(run.run_dir)}`}
                  className="animate-fade-in-up block h-full"
                  style={{
                    animationFillMode: "forwards",
                    opacity: 0,
                    animationDelay: `${index * 80}ms`,
                  }}
                >
                  <Card className="hover:border-primary/50 overflow-hidden group h-full flex flex-col transition-all duration-300 hover:shadow-xl dark:hover:shadow-primary/5">
                    <div className="relative aspect-video w-full overflow-hidden bg-muted/30">
                      {imgSrc ? (
                        <picture>
                          {avifSrc && (
                            <source srcSet={avifSrc} type="image/avif" />
                          )}
                          {webpSrc && (
                            <source srcSet={webpSrc} type="image/webp" />
                          )}
                          <img
                            src={imgSrc}
                            alt={modelName}
                            className="object-cover w-full h-full transition-transform duration-500 group-hover:scale-105"
                            loading="lazy"
                          />
                        </picture>
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <span className="text-muted-foreground/40 text-sm">
                            暂无预览图
                          </span>
                        </div>
                      )}
                    </div>
                    <CardContent className="flex flex-1 flex-col justify-between space-y-4 p-6">
                      <div className="space-y-3">
                        <div className="space-y-1.5">
                          <div className="group-hover:text-primary transition-colors text-xl font-bold leading-none tracking-tight">
                            {modelName}
                          </div>
                          <div className="text-muted-foreground/60 font-mono text-[10px]">
                            {run.run_dir}
                          </div>
                        </div>
                        {modelDesc ? (
                          <div className="bg-muted/50 rounded-md p-3 text-sm text-muted-foreground line-clamp-2">
                            {modelDesc}
                          </div>
                        ) : null}
                      </div>
                      <div className="flex items-center justify-between pt-2">
                        <div className="flex items-center gap-2">
                          <Badge
                            variant="outline"
                            className="bg-primary/5"
                          >{`${run.x_count}×${run.y_count}`}</Badge>
                          <Badge
                            variant="secondary"
                            className="opacity-80"
                          >{`${run.total_cells} 张`}</Badge>
                        </div>
                        <div className="text-muted-foreground/80 text-xs">
                          {formatCreatedAt(run.created_at)}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
        ) : null}
      </div>
    </main>
  );
}
