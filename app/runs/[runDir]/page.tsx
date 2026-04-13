"use client";

import { use, useEffect, useMemo, useState } from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import Link from "next/link";

import {
  type BlurhashCell,
  type RunGridIndexData,
  type RunGridXColumn,
  VirtualGrid,
} from "@/components/comfyui/virtual-grid";
import { useUserPreferences } from "@/components/user-preferences-provider";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { FileIcon, LinkSquare02Icon } from "@hugeicons/core-free-icons";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";

type RunDetailSummary = {
  run_id: string;
  created_at: string;
  run_dir: string;
  selection: {
    total_cells: number;
  };
  model?: {
    name?: string | null;
    description?: {
      zh?: string | null;
      en?: string | null;
    } | null;
    links?: {
      homepage?: string | null;
      huggingface?: string | null;
      civitai?: string | null;
    } | null;
  } | null;
  workflow?: {
    sha256?: string | null;
    download_url?: string | null;
  } | null;
};

type RunDetailResponse = {
  run: RunDetailSummary;
  xLabels: string[];
  yLabels: string[];
  x_columns: RunGridXColumn[];
  y_indexes: number[];
};

type LoadState = "loading" | "ready" | "not-found" | "error";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function isRunDetailResponse(value: unknown): value is RunDetailResponse {
  if (!isRecord(value)) {
    return false;
  }

  if (!isStringArray(value.xLabels) || !isStringArray(value.yLabels)) {
    return false;
  }

  if (!Array.isArray(value.x_columns) || !Array.isArray(value.y_indexes)) {
    return false;
  }

  if (!isRecord(value.run) || !isRecord(value.run.selection)) {
    return false;
  }

  const run = value.run;
  const selection = run.selection as Record<string, unknown>;

  return (
    typeof run.run_id === "string" &&
    typeof run.created_at === "string" &&
    typeof run.run_dir === "string" &&
    typeof selection.total_cells === "number"
  );
}

function isRunGridIndexData(value: unknown): value is RunGridIndexData {
  if (!isRecord(value)) {
    return false;
  }

  if (!Array.isArray(value.x_columns) || !Array.isArray(value.y_indexes)) {
    return false;
  }

  const x_columns = value.x_columns as unknown[];
  const xColumnsOk = x_columns.every((col) => {
    if (!isRecord(col)) return false;
    const type = col.type;
    const typeOk = typeof type === "string" || type === null;
    const desc = col.description;
    const descOk = desc === null || isRecord(desc);
    return typeOk && descOk;
  });

  const y_indexes = value.y_indexes as unknown[];
  const yIndexesOk = y_indexes.every(
    (item) => typeof item === "number" && Number.isFinite(item) && item >= 0,
  );

  const hasBlurhashCells = Array.isArray(value.blurhash_cells);

  return (
    xColumnsOk && yIndexesOk && (hasBlurhashCells || !value.blurhash_cells)
  );
}

function SummarySkeleton() {
  const keys = ["k1", "k2", "k3", "k4"];
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {keys.map((key) => (
        <div key={key} className="border p-3">
          <Skeleton className="mb-2 h-3 w-16" />
          <Skeleton className="h-4 w-full" />
        </div>
      ))}
    </div>
  );
}

function GridSkeleton() {
  const rowKeys = ["r1", "r2", "r3", "r4", "r5"];
  const cellKeys = ["c1", "c2", "c3", "c4", "c5", "c6"];
  return (
    <div className="space-y-2">
      {rowKeys.map((rowKey) => (
        <div key={rowKey} className="grid min-w-240 grid-cols-6 gap-2">
          {cellKeys.map((cellKey) => (
            <Skeleton key={`${rowKey}-${cellKey}`} className="h-32 w-full" />
          ))}
        </div>
      ))}
    </div>
  );
}

export default function RunDetailPage({
  params,
}: {
  params: Promise<{ runDir: string | string[] }>;
}) {
  const resolvedParams = use(params);
  const { showNsfw } = useUserPreferences();
  const [detailLoadState, setDetailLoadState] = useState<LoadState>("loading");
  const [gridLoadState, setGridLoadState] = useState<LoadState>("loading");
  const [detailData, setDetailData] = useState<RunDetailResponse | null>(null);
  const [gridData, setGridData] = useState<RunGridIndexData | null>(null);

  const runDir = useMemo(() => {
    if (!resolvedParams?.runDir) {
      return "";
    }

    return Array.isArray(resolvedParams.runDir)
      ? resolvedParams.runDir[0]
      : resolvedParams.runDir;
  }, [resolvedParams]);

  useEffect(() => {
    const abortController = new AbortController();
    const preferenceRequestKey = showNsfw ? "nsfw-on" : "nsfw-off";

    async function fetchAll() {
      if (!runDir) {
        setDetailLoadState("not-found");
        setGridLoadState("not-found");
        setDetailData(null);
        setGridData(null);
        return;
      }

      setDetailLoadState("loading");
      setGridLoadState("loading");

      const detailPromise = fetch(
        `/api/comfyui/run/${encodeURIComponent(runDir)}?viewer_nsfw=${preferenceRequestKey}`,
        {
          cache: "no-store",
          signal: abortController.signal,
        },
      ).then(async (res) => {
        if (res.status === 404) throw new Error("not-found");
        if (!res.ok) throw new Error("error");
        const data = await res.json();
        if (!isRunDetailResponse(data)) throw new Error("error");
        return data;
      });

      const gridPromise = fetch(
        `/api/comfyui/run/${encodeURIComponent(runDir)}/grid?viewer_nsfw=${preferenceRequestKey}`,
        {
          cache: "no-store",
          signal: abortController.signal,
        },
      ).then(async (res) => {
        if (res.status === 404) throw new Error("not-found");
        if (!res.ok) throw new Error("error");
        const data = await res.json();
        if (!isRunGridIndexData(data)) throw new Error("error");
        return data;
      });

      detailPromise
        .then((data) => {
          if (abortController.signal.aborted) return;
          setDetailData(data);
          setDetailLoadState("ready");
        })
        .catch((err) => {
          if (abortController.signal.aborted) return;
          if (err.name === "AbortError") return;
          setDetailLoadState(
            err.message === "not-found" ? "not-found" : "error",
          );
        });

      gridPromise
        .then((data) => {
          if (abortController.signal.aborted) return;
          setGridData(data);
          setGridLoadState("ready");
        })
        .catch((err) => {
          if (abortController.signal.aborted) return;
          if (err.name === "AbortError") return;
          setGridLoadState(err.message === "not-found" ? "not-found" : "error");
        });
    }

    void fetchAll();

    return () => {
      abortController.abort();
    };
  }, [runDir, showNsfw]);

  const isDetailLoading = detailLoadState === "loading";
  const isGridLoading = gridLoadState === "loading";
  const isDetailReady = detailLoadState === "ready" && detailData !== null;
  const isGridReady = gridLoadState === "ready" && gridData !== null;

  const breadcrumbTitle = isDetailReady
    ? detailData.run.model?.name || detailData.run.run_dir
    : runDir || "(无效路径)";

  const blurhashMap = useMemo(() => {
    const map = new Map<string, BlurhashCell>();
    if (!gridData?.blurhash_cells) return map;
    for (const cell of gridData.blurhash_cells) {
      const key = `${cell.x_index}:${cell.y_index}`;
      // Keep only the first item per (x, y) — the representative
      if (!map.has(key)) {
        map.set(key, cell);
      }
    }
    return map;
  }, [gridData]);
  return (
    <main className="mx-auto flex h-full w-full max-w-none flex-col gap-2 overflow-hidden p-2">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/">首页</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{breadcrumbTitle}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      {isDetailLoading ? (
        <div data-testid="run-detail-loading">
          <SummarySkeleton />
        </div>
      ) : null}

      {detailLoadState === "not-found" ? (
        <Empty data-testid="run-not-found">
          <EmptyHeader>
            <EmptyTitle>未找到 run</EmptyTitle>
            <EmptyDescription>
              无法加载 {runDir || "该路径"}，请确认 runDir 是否存在。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {detailLoadState === "error" ? (
        <Empty data-testid="run-error">
          <EmptyHeader>
            <EmptyTitle>加载失败</EmptyTitle>
            <EmptyDescription>
              请求 run 详情失败，请稍后刷新重试。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {isDetailReady
        ? (() => {
          const modelName =
            detailData.run.model?.name || detailData.run.run_dir;
          const modelDesc =
            detailData.run.model?.description?.zh ||
            detailData.run.model?.description?.en;
          const links = detailData.run.model?.links;
          const workflow = detailData.run.workflow;

          return (
            <div className="animate-fade-in-up flex flex-col gap-3 py-2 px-1">
              <div className="flex items-end justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3">
                  <h1 className="text-xl font-semibold tracking-tight">
                    {modelName}
                  </h1>
                  <div className="text-muted-foreground flex items-center gap-1.5 bg-muted/30 px-2 py-0.5 rounded-md border border-border/40">
                    <HugeiconsIcon
                      icon={FileIcon}
                      className="size-3.5"
                      strokeWidth={2}
                    />
                    <span className="font-mono text-xs">
                      {detailData.run.run_dir}
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {links &&
                    (links.homepage || links.huggingface || links.civitai) ? (
                    <div className="flex items-center gap-1.5">
                      {links.homepage ? (
                        <a
                          href={links.homepage}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label="打开模型官网"
                          className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
                        >
                          <HugeiconsIcon
                            icon={LinkSquare02Icon}
                            className="size-3"
                            strokeWidth={2}
                          />
                          官网
                        </a>
                      ) : null}
                      {links.huggingface ? (
                        <a
                          href={links.huggingface}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label="打开 Hugging Face 页面"
                          className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
                        >
                          Hugging Face 链接
                        </a>
                      ) : null}
                      {links.civitai ? (
                        <a
                          href={links.civitai}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label="打开 Civitai 页面"
                          className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
                        >
                          Civitai 链接
                        </a>
                      ) : null}
                    </div>
                  ) : null}

                  {workflow?.download_url ? (
                    <a
                      href={workflow.download_url}
                      download
                      className="hover:bg-primary/10 hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium transition-colors backdrop-blur-sm"
                    >
                      <HugeiconsIcon
                        icon={FileIcon}
                        className="size-3"
                        strokeWidth={2}
                      />
                      下载 Comfy UI 工作流
                    </a>
                  ) : null}
                </div>
              </div>

              {modelDesc ? (
                <div className="group relative">
                  <p className="text-muted-foreground/80 text-xs leading-relaxed line-clamp-1 group-hover:line-clamp-none transition-all duration-300">
                    {modelDesc}
                  </p>
                </div>
              ) : null}
            </div>
          );
        })()
        : null}

      <div className="flex min-h-0 flex-1 flex-col">
        {isGridLoading ? <GridSkeleton /> : null}

        {isGridReady ? (
          <div className="min-h-0 flex-1">
            <VirtualGrid
              key={`${runDir}:${showNsfw ? "nsfw" : "sfw"}`}
              runDir={runDir}
              grid={gridData}
              blurhashMap={blurhashMap}
            />
          </div>
        ) : null}

        {(gridLoadState === "not-found" || gridLoadState === "error") &&
          isDetailReady ? (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>暂无网格可展示</EmptyTitle>
              <EmptyDescription>
                修复 runDir 或请求错误后，此区域将显示完整网格。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}
      </div>
    </main>
  );
}
