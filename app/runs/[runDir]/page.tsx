"use client";

import { use, useEffect, useMemo, useState } from "react";

import {
  type BlurhashCell,
  type RunGridIndexData,
  type RunGridXColumn,
  VirtualGrid,
} from "@/components/comfyui/virtual-grid";
import Link from "next/link";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  FileIcon,
  Clock01Icon,
  GridIcon,
  Image01Icon,
  LinkSquare02Icon,
} from "@hugeicons/core-free-icons";
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
  const [loadState, setLoadState] = useState<LoadState>("loading");
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

    async function fetchRunDetail() {
      if (!runDir) {
        setDetailData(null);
        setGridData(null);
        setLoadState("not-found");
        return;
      }

      setLoadState("loading");

      try {
        const [detailResponse, gridResponse] = await Promise.all([
          fetch(`/api/comfyui/run/${encodeURIComponent(runDir)}`, {
            signal: abortController.signal,
          }),
          fetch(`/api/comfyui/run/${encodeURIComponent(runDir)}/grid`, {
            signal: abortController.signal,
          }),
        ]);

        if (detailResponse.status === 404 || gridResponse.status === 404) {
          setDetailData(null);
          setGridData(null);
          setLoadState("not-found");
          return;
        }

        if (!detailResponse.ok || !gridResponse.ok) {
          throw new Error("Failed to load run detail");
        }

        const [detailPayload, gridPayload]: [unknown, unknown] =
          await Promise.all([detailResponse.json(), gridResponse.json()]);

        if (!isRunDetailResponse(detailPayload)) {
          throw new Error("Unexpected run detail payload");
        }

        if (!isRunGridIndexData(gridPayload)) {
          throw new Error("Unexpected run grid payload");
        }

        setDetailData(detailPayload);
        setGridData(gridPayload);
        setLoadState("ready");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setDetailData(null);
        setGridData(null);
        setLoadState("error");
      }
    }

    void fetchRunDetail();

    return () => {
      abortController.abort();
    };
  }, [runDir]);

  const isLoading = loadState === "loading";
  const isReady =
    loadState === "ready" && detailData !== null && gridData !== null;
  const xCount = isReady ? gridData.x_columns.length : 0;
  const yCount = isReady ? gridData.y_indexes.length : 0;
  const breadcrumbTitle = isReady
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
      {isLoading ? (
        <div data-testid="run-detail-loading">
          <SummarySkeleton />
        </div>
      ) : null}

      {loadState === "not-found" ? (
        <Empty data-testid="run-not-found">
          <EmptyHeader>
            <EmptyTitle>未找到 run</EmptyTitle>
            <EmptyDescription>
              无法加载 {runDir || "该路径"}，请确认 runDir 是否存在。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {loadState === "error" ? (
        <Empty data-testid="run-error">
          <EmptyHeader>
            <EmptyTitle>加载失败</EmptyTitle>
            <EmptyDescription>
              请求 run 详情失败，请稍后刷新重试。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}

      {isReady
        ? (() => {
            const modelName =
              detailData.run.model?.name || detailData.run.run_dir;
            const modelDesc =
              detailData.run.model?.description?.zh ||
              detailData.run.model?.description?.en;
            const links = detailData.run.model?.links;
            const workflow = detailData.run.workflow;

            return (
              <div className="animate-fade-in-up bg-card text-card-foreground flex flex-col gap-4 rounded-xl border p-6 shadow-sm">
                <div className="flex flex-col gap-2">
                  <h1 className="text-3xl font-extrabold tracking-tight md:text-4xl">
                    {modelName}
                  </h1>
                  {modelDesc ? (
                    <div className="bg-muted/30 border-l-2 border-primary/30 my-2 py-3 pl-4 pr-3">
                      <p className="text-muted-foreground text-sm leading-relaxed md:text-base">
                        {modelDesc}
                      </p>
                    </div>
                  ) : null}
                </div>

                <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
                  <div className="text-muted-foreground flex items-center gap-1.5">
                    <HugeiconsIcon
                      icon={FileIcon}
                      className="size-4"
                      strokeWidth={2}
                    />
                    <span className="font-mono text-xs">
                      {detailData.run.run_dir}
                    </span>
                  </div>
                  <div className="text-muted-foreground flex items-center gap-1.5">
                    <HugeiconsIcon
                      icon={Clock01Icon}
                      className="size-4"
                      strokeWidth={2}
                    />
                    <span>{formatCreatedAt(detailData.run.created_at)}</span>
                  </div>
                  <div className="text-muted-foreground flex items-center gap-1.5">
                    <HugeiconsIcon
                      icon={GridIcon}
                      className="size-4"
                      strokeWidth={2}
                    />
                    <span>{`${xCount}×${yCount}`}</span>
                  </div>
                  <div className="text-muted-foreground flex items-center gap-1.5">
                    <HugeiconsIcon
                      icon={Image01Icon}
                      className="size-4"
                      strokeWidth={2}
                    />
                    <span>{`${detailData.run.selection.total_cells} 张`}</span>
                  </div>

                  {links &&
                  (links.homepage || links.huggingface || links.civitai) ? (
                    <div className="flex items-center gap-2 border-l pl-6">
                      {links.homepage ? (
                        <a
                          href={links.homepage}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label="打开模型官网"
                          className="hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors"
                        >
                          <HugeiconsIcon
                            icon={LinkSquare02Icon}
                            className="size-4"
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
                          className="hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors"
                        >
                          Hugging Face
                        </a>
                      ) : null}
                      {links.civitai ? (
                        <a
                          href={links.civitai}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label="打开 Civitai 页面"
                          className="hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors"
                        >
                          Civitai
                        </a>
                      ) : null}
                    </div>
                  ) : null}

                  {workflow?.download_url ? (
                    <div className="flex items-center gap-2 border-l pl-6">
                      <a
                        href={workflow.download_url}
                        download
                        className="hover:text-primary text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors"
                      >
                        <HugeiconsIcon
                          icon={FileIcon}
                          className="size-4"
                          strokeWidth={2}
                        />
                        下载工作流
                      </a>
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })()
        : null}

      <div className="flex min-h-0 flex-1 flex-col">
        {isLoading ? <GridSkeleton /> : null}

        {isReady ? (
          <div className="min-h-0 flex-1">
            <VirtualGrid
              runDir={runDir}
              grid={gridData}
              blurhashMap={blurhashMap}
            />
          </div>
        ) : null}

        {loadState === "not-found" || loadState === "error" ? (
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
