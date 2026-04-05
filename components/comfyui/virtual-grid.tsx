"use client";

import { useVirtualizer } from "@tanstack/react-virtual";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { GridImage } from "./grid-image";

export type VariantUrls = {
  webp?: string;
  avif?: string;
};

type RowMeta = {
  seed: string | null;
  prompt_hash: string | null;
  positive_prompt: string | null;
  y_value: string | null;
};

type RowItem = {
  batch_index: number;
  category: string | null;
  width: number | null;
  height: number | null;
  blurhash: string | null;
  meta: RowMeta;
  thumb: VariantUrls | null;
  display: VariantUrls | null;
};

type RowCell = {
  x_index: number;
  y_index: number;
  items: RowItem[];
};

type RowPayload = {
  run_dir: string;
  y_index: number;
  cells: RowCell[];
};

export type RunGridXColumn = {
  type: string | null;
  description: Record<string, unknown> | null;
};

export type BlurhashCell = {
  x_index: number;
  y_index: number;
  batch_index: number;
  category: string;
  width: number | null;
  height: number | null;
  blurhash: string | null;
};

export type RunGridIndexData = {
  x_columns: RunGridXColumn[];
  y_indexes: number[];
  blurhash_cells: BlurhashCell[];
};

type VirtualGridProps = {
  runDir: string;
  grid: RunGridIndexData;
  /** Pre-loaded blurhash lookup: key = "x_index:y_index" → first matching BlurhashCell */
  blurhashMap: Map<string, BlurhashCell>;
};

const CELL_MIN_WIDTH = 184;
const LEFT_COLUMN_WIDTH = 220;
const DEV_IMAGE_DOM_CAP_NOTE = 300;

const CELL_PADDING_PX = 8;
const CELL_GAP_PX = 4;
const CELL_META_HEIGHT_PX = 28;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function getNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function getFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function getSeedString(value: unknown): string | null {
  if (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Number.isInteger(value)
  ) {
    return String(value);
  }
  return getNonEmptyString(value);
}

function getXLabel(
  column: RunGridXColumn | null | undefined,
  index: number,
): string {
  const raw = column?.description;
  const zh =
    raw && typeof raw.zh === "string" ? getNonEmptyString(raw.zh) : null;
  return zh ?? `X${index}`;
}

function pickBestVariants(
  primary: VariantUrls | null,
  fallback: VariantUrls | null,
): VariantUrls | null {
  const candidate = primary ?? fallback;
  if (!candidate) return null;
  const hasWebp =
    typeof candidate.webp === "string" && candidate.webp.length > 0;
  const hasAvif =
    typeof candidate.avif === "string" && candidate.avif.length > 0;
  if (!hasWebp && !hasAvif) return null;
  return {
    webp: hasWebp ? candidate.webp : undefined,
    avif: hasAvif ? candidate.avif : undefined,
  };
}

function getPreferredAspectRatioFromCache(rows: Iterable<CachedRow>): number {
  for (const row of rows) {
    if (row.status !== "ready") continue;
    for (const cell of row.cellsByX.values()) {
      for (const item of cell.items) {
        const width = item.width;
        const height = item.height;
        if (
          typeof width === "number" &&
          typeof height === "number" &&
          Number.isFinite(width) &&
          Number.isFinite(height) &&
          width > 0 &&
          height > 0
        ) {
          return height / width;
        }
      }
    }
  }
  return 1;
}

type SelectedCellPreview = {
  xIndex: number;
  yIndex: number;
  xLabel: string;
  yLabel: string;
  seed: string | null;
  promptHash: string | null;
  positivePrompt: string;
  items: Array<{
    batchIndex: number;
    width: number | null;
    height: number | null;
    thumb: VariantUrls | null;
    display: VariantUrls | null;
  }>;
};

type CachedRow =
  | {
      status: "ready";
      yIndex: number;
      yValue: string | null;
      representativeMeta: RowMeta | null;
      cellsByX: Map<number, RowCell>;
    }
  | {
      status: "error";
      yIndex: number;
      error: string;
    };

function parseVariantUrls(value: unknown): VariantUrls | null {
  if (!isRecord(value)) return null;
  const webp = getNonEmptyString(value.webp);
  const avif = getNonEmptyString(value.avif);
  if (!webp && !avif) return null;
  return {
    webp: webp ?? undefined,
    avif: avif ?? undefined,
  };
}

function parseRowMeta(value: unknown): RowMeta {
  if (!isRecord(value)) {
    return {
      seed: null,
      prompt_hash: null,
      positive_prompt: null,
      y_value: null,
    };
  }

  return {
    seed: getSeedString(value.seed),
    prompt_hash: getNonEmptyString(value.prompt_hash),
    positive_prompt: getNonEmptyString(value.positive_prompt),
    y_value: getNonEmptyString(value.y_value),
  };
}

function normalizeRowPayload(
  raw: unknown,
  requestedYIndex: number,
): RowPayload | null {
  if (!isRecord(raw)) return null;

  const rawCells = raw.cells;
  const cells: RowCell[] = Array.isArray(rawCells)
    ? rawCells
        .map((cell) => {
          if (!isRecord(cell)) return null;
          const xIndex = getFiniteNumber(cell.x_index);
          const yIndex = getFiniteNumber(cell.y_index);
          if (xIndex === null || yIndex === null) return null;
          const itemsRaw = cell.items;
          const items: RowItem[] = Array.isArray(itemsRaw)
            ? itemsRaw
                .map((item) => {
                  if (!isRecord(item)) return null;
                  const batchIndex = getFiniteNumber(item.batch_index);
                  if (batchIndex === null) return null;
                  const meta = parseRowMeta(item.meta);
                  return {
                    batch_index: batchIndex,
                    category: getNonEmptyString(item.category),
                    width: getFiniteNumber(item.width),
                    height: getFiniteNumber(item.height),
                    blurhash: getNonEmptyString(item.blurhash),
                    meta,
                    thumb: parseVariantUrls(item.thumb),
                    display: parseVariantUrls(item.display),
                  };
                })
                .filter((v): v is RowItem => v !== null)
            : [];

          items.sort((a, b) => a.batch_index - b.batch_index);
          return { x_index: xIndex, y_index: yIndex, items };
        })
        .filter((v): v is RowCell => v !== null)
    : [];

  const yIndexValue = getFiniteNumber(raw.y_index) ?? requestedYIndex;
  const runDir = getNonEmptyString(raw.run_dir) ?? "";

  return {
    run_dir: runDir,
    y_index: yIndexValue,
    cells,
  };
}

function formatValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === ""
    ? "-"
    : String(value);
}

export function VirtualGrid({ runDir, grid, blurhashMap }: VirtualGridProps) {
  const scrollElementRef = useRef<HTMLDivElement | null>(null);
  const [scrollViewportWidth, setScrollViewportWidth] = useState<number | null>(
    null,
  );
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedCell, setSelectedCell] = useState<SelectedCellPreview | null>(
    null,
  );
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [copiedField, setCopiedField] = useState<"prompt" | "seed" | null>(
    null,
  );
  const rowCacheRef = useRef<Map<number, CachedRow>>(new Map());
  const rowRequestsRef = useRef<Map<number, AbortController>>(new Map());
  const [rowCacheVersion, setRowCacheVersion] = useState(0);
  const { user } = useAuth();
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);

  useEffect(() => {
    const element = scrollElementRef.current;
    if (!element) {
      return;
    }

    const update = () => {
      setScrollViewportWidth(element.clientWidth);
    };

    update();

    const observer = new ResizeObserver(() => {
      update();
    });

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, []);

  const xHeaders = useMemo(() => {
    return grid.x_columns.map((col, index) => {
      const label = getXLabel(col, index);
      const type = getNonEmptyString(col.type) ?? "x";
      return {
        key: `${index}:${type}:${label}`,
        label,
      };
    });
  }, [grid.x_columns]);

  const preferredAspectRatio = useMemo(() => {
    void rowCacheVersion;
    // Try row cache first
    const fromCache = getPreferredAspectRatioFromCache(
      rowCacheRef.current.values(),
    );
    if (fromCache !== 1) return fromCache;
    // Fall back to pre-loaded blurhash cells for instant aspect ratio
    for (const cell of blurhashMap.values()) {
      const w = cell.width;
      const h = cell.height;
      if (
        typeof w === "number" &&
        typeof h === "number" &&
        Number.isFinite(w) &&
        Number.isFinite(h) &&
        w > 0 &&
        h > 0
      ) {
        return h / w;
      }
    }
    return 1;
  }, [rowCacheVersion, blurhashMap]);

  const cellWidth = useMemo(() => {
    if (!scrollViewportWidth || scrollViewportWidth <= 0) {
      return CELL_MIN_WIDTH;
    }

    const xCount = Math.max(1, xHeaders.length);
    const available = scrollViewportWidth - LEFT_COLUMN_WIDTH;

    if (available <= 0) {
      return CELL_MIN_WIDTH;
    }

    return Math.max(CELL_MIN_WIDTH, Math.floor(available / xCount));
  }, [scrollViewportWidth, xHeaders.length]);

  const previewHeight = useMemo(() => {
    const innerWidth = Math.max(1, cellWidth - CELL_PADDING_PX * 2);
    return Math.max(32, Math.round(innerWidth * preferredAspectRatio));
  }, [cellWidth, preferredAspectRatio]);

  const rowHeight = useMemo(() => {
    return (
      CELL_PADDING_PX * 2 + previewHeight + CELL_GAP_PX + CELL_META_HEIGHT_PX
    );
  }, [previewHeight]);

  // TanStack Virtual's hook returns functions that React Compiler can't memoize safely.
  // We intentionally keep virtualization here for performance.
  const rowVirtualizer = useVirtualizer({
    count: grid.y_indexes.length,
    getScrollElement: () => scrollElementRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
  });

  const gridTemplateColumns = useMemo(
    () => `${LEFT_COLUMN_WIDTH}px repeat(${xHeaders.length}, ${cellWidth}px)`,
    [cellWidth, xHeaders.length],
  );
  const gridMinWidth = LEFT_COLUMN_WIDTH + xHeaders.length * CELL_MIN_WIDTH;
  const virtualRows = rowVirtualizer.getVirtualItems();
  const isDevEnv = process.env.NODE_ENV !== "production";
  const totalImages = selectedCell?.items.length ?? 0;
  const currentItem = selectedCell?.items[currentImageIndex] ?? null;
  const currentDisplayVariants = useMemo(() => {
    if (!currentItem) return null;
    return pickBestVariants(currentItem.display, currentItem.thumb);
  }, [currentItem]);
  const currentDownloadUrl =
    currentDisplayVariants?.webp ?? currentDisplayVariants?.avif ?? null;
  const sizeText =
    currentItem &&
    typeof currentItem.width === "number" &&
    typeof currentItem.height === "number" &&
    Number.isFinite(currentItem.width) &&
    Number.isFinite(currentItem.height)
      ? `${currentItem.width}×${currentItem.height}`
      : "-";

  useEffect(() => {
    if (!dialogOpen) {
      setCopiedField(null);
      setCurrentImageIndex(0);
    }
  }, [dialogOpen]);

  useEffect(() => {
    void rowHeight;
    rowVirtualizer.measure();
  }, [rowHeight, rowVirtualizer]);

  const requestRow = useCallback(
    async (yIndex: number) => {
      if (!Number.isFinite(yIndex) || yIndex < 0) return;
      if (rowCacheRef.current.has(yIndex)) return;
      if (rowRequestsRef.current.has(yIndex)) return;

      const controller = new AbortController();
      rowRequestsRef.current.set(yIndex, controller);

      try {
        const response = await fetch(
          `/api/comfyui/run/${encodeURIComponent(runDir)}/row?y_index=${encodeURIComponent(String(yIndex))}`,
          {
            cache: "no-store",
            signal: controller.signal,
          },
        );

        if (response.status === 404) {
          rowCacheRef.current.set(yIndex, {
            status: "error",
            yIndex,
            error: "not-found",
          });
          setRowCacheVersion((v) => v + 1);
          return;
        }

        if (!response.ok) {
          rowCacheRef.current.set(yIndex, {
            status: "error",
            yIndex,
            error: `http-${response.status}`,
          });
          setRowCacheVersion((v) => v + 1);
          return;
        }

        const raw: unknown = await response.json();
        const payload = normalizeRowPayload(raw, yIndex);
        if (!payload) {
          rowCacheRef.current.set(yIndex, {
            status: "error",
            yIndex,
            error: "invalid-payload",
          });
          setRowCacheVersion((v) => v + 1);
          return;
        }

        const cellsByX = new Map<number, RowCell>();
        let representativeMeta: RowMeta | null = null;
        for (const cell of payload.cells) {
          cellsByX.set(cell.x_index, cell);
          if (!representativeMeta) {
            const firstItem = cell.items[0];
            if (firstItem) {
              representativeMeta = firstItem.meta;
            }
          }
        }

        const yValue = representativeMeta?.y_value ?? null;
        rowCacheRef.current.set(yIndex, {
          status: "ready",
          yIndex,
          yValue,
          representativeMeta,
          cellsByX,
        });
        setRowCacheVersion((v) => v + 1);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        rowCacheRef.current.set(yIndex, {
          status: "error",
          yIndex,
          error: "fetch-failed",
        });
        setRowCacheVersion((v) => v + 1);
      } finally {
        rowRequestsRef.current.delete(yIndex);
      }
    },
    [runDir],
  );

  useEffect(() => {
    const yIndexes = grid.y_indexes;
    for (const virtualRow of virtualRows) {
      const yIndex = yIndexes[virtualRow.index];
      if (typeof yIndex !== "number") continue;
      void requestRow(yIndex);
    }
  }, [grid.y_indexes, requestRow, virtualRows]);

  useEffect(() => {
    const requests = rowRequestsRef.current;
    return () => {
      for (const controller of requests.values()) {
        controller.abort();
      }
      requests.clear();
    };
  }, []);

  const openCellDialog = useCallback(
    (
      cell: RowCell,
      xIndex: number,
      yIndex: number,
      xLabel: string,
      yLabel: string,
    ) => {
      const items = cell.items
        .map((item) => ({
          batchIndex: item.batch_index,
          width: item.width,
          height: item.height,
          thumb: item.thumb,
          display: item.display,
        }))
        .filter((item) => item.thumb !== null || item.display !== null);

      const representative = cell.items[0]?.meta ?? null;
      const positivePrompt = representative?.positive_prompt;
      const seed = representative?.seed ?? null;
      const promptHash = representative?.prompt_hash ?? null;

      setSelectedCell({
        xIndex,
        yIndex,
        xLabel,
        yLabel,
        seed,
        promptHash,
        positivePrompt: positivePrompt ?? "（无 positive prompt）",
        items,
      });
      setCurrentImageIndex(0);
      setDialogOpen(true);
    },
    [],
  );

  const copyText = useCallback(
    async (field: "prompt" | "seed", value: string) => {
      try {
        await navigator.clipboard.writeText(value);
        setCopiedField(field);
      } catch {
        setCopiedField(null);
      }
    },
    [],
  );

  const showPreviousImage = useCallback(() => {
    setCurrentImageIndex((index) => {
      if (index <= 0) {
        return 0;
      }

      return index - 1;
    });
  }, []);

  const showNextImage = useCallback(() => {
    setCurrentImageIndex((index) => {
      if (!selectedCell || index >= selectedCell.items.length - 1) {
        return index;
      }

      return index + 1;
    });
  }, [selectedCell]);

  return (
    <div
      className="flex h-full min-h-0 flex-col overflow-hidden border rounded-sm"
      data-testid="run-grid"
      data-row-count={grid.y_indexes.length}
      data-row-height={rowHeight}
    >
      {isDevEnv ? (
        <div
          className="text-muted-foreground border-b bg-muted/30 px-3 py-1 text-[10px]"
          data-testid="run-grid-dev-debug"
        >
          {`dev: rendered rows ${virtualRows.length}, img cap target < ${DEV_IMAGE_DOM_CAP_NOTE}`}
        </div>
      ) : null}

      <div
        ref={scrollElementRef}
        className="relative min-h-0 flex-1 overflow-auto"
        data-testid="run-grid-scroll"
      >
        <div className="relative" style={{ minWidth: gridMinWidth }}>
          <div className="bg-background/95 sticky top-0 z-30 border-b backdrop-blur supports-[backdrop-filter]:bg-background/80">
            <div className="grid" style={{ gridTemplateColumns }}>
              <div
                className="bg-background/95 sticky left-0 z-40 border-r px-3 py-2 text-xs font-semibold backdrop-blur supports-[backdrop-filter]:bg-background/80"
                data-testid="run-grid-corner"
              >
                Y\X
              </div>
              {xHeaders.map((header, xIndex) => (
                <div
                  key={header.key}
                  className="border-r px-3 py-2 text-xs font-semibold"
                >
                  <p className="truncate">{`X${xIndex}`}</p>
                  <p className="text-muted-foreground mt-1 truncate text-[10px] font-normal">
                    {header.label}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div
            className="relative"
            style={{ height: rowVirtualizer.getTotalSize() }}
          >
            {virtualRows.map((virtualRow) => {
              const yIndex =
                grid.y_indexes[virtualRow.index] ?? virtualRow.index;
              const cachedRow = rowCacheRef.current.get(yIndex);
              const yLabel =
                cachedRow && cachedRow.status === "ready" && cachedRow.yValue
                  ? cachedRow.yValue
                  : `Y${yIndex}`;

              return (
                <div
                  key={virtualRow.key}
                  className="absolute left-0 top-0 w-full border-b"
                  data-testid="run-grid-row"
                  data-row-index={yIndex}
                  style={{
                    height: virtualRow.size,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <div className="grid h-full" style={{ gridTemplateColumns }}>
                    <div
                      className="bg-background/95 sticky left-0 z-20 flex h-full border-r px-3 py-2 text-xs backdrop-blur supports-[backdrop-filter]:bg-background/80"
                      data-testid="run-grid-y-label"
                    >
                      <div>
                        <p className="font-semibold">{`Y${yIndex}`}</p>
                        <p className="text-muted-foreground mt-1 line-clamp-3 text-[10px]">
                          {cachedRow && cachedRow.status === "ready"
                            ? (cachedRow.yValue ?? "-")
                            : cachedRow && cachedRow.status === "error"
                              ? "加载失败"
                              : yLabel}
                        </p>
                      </div>
                    </div>

                    {xHeaders.map((header, xIndex) => {
                      const xLabel = header.label;
                      const xKey = header.key;
                      const rowEntry = rowCacheRef.current.get(yIndex);
                      const rowCell =
                        rowEntry && rowEntry.status === "ready"
                          ? (rowEntry.cellsByX.get(xIndex) ?? null)
                          : null;

                      const representativeItem = rowCell?.items[0] ?? null;
                      const seed = representativeItem?.meta.seed ?? null;
                      const thumbVariants = representativeItem
                        ? pickBestVariants(
                            representativeItem.thumb,
                            representativeItem.display,
                          )
                        : null;

                      // Always use pre-loaded blurhash from the grid-level map as the
                      // primary source — it's available before any row API call completes.
                      // Fall back to the row-level data only if the map has no entry.
                      const preloadedCell = blurhashMap.get(
                        `${xIndex}:${yIndex}`,
                      );
                      const effectiveBlurhash =
                        preloadedCell?.blurhash ??
                        representativeItem?.blurhash ??
                        null;
                      const effectiveCategory =
                        preloadedCell?.category ??
                        representativeItem?.category ??
                        null;

                      const canOpenDialog =
                        !!rowCell && rowCell.items.length > 0;
                      const isLocked =
                        !user &&
                        effectiveCategory !== null &&
                        effectiveCategory !== "normal";

                      const hasBlurhash = !!effectiveBlurhash;
                      // Show the image component whenever we have real thumbs OR a blurhash
                      // (locked or not, row loaded or not).
                      const showImage = !!thumbVariants || hasBlurhash;

                      const placeholderLabel =
                        rowEntry && rowEntry.status === "error"
                          ? "加载失败"
                          : rowEntry
                            ? "缺失"
                            : "加载中";

                      const previewNode = showImage ? (
                        <div
                          className="w-full rounded border"
                          style={{ height: previewHeight }}
                        >
                          <GridImage
                            thumbVariants={thumbVariants}
                            blurhash={effectiveBlurhash}
                            alt={`${yLabel} × ${xLabel}`}
                            locked={isLocked}
                            onLockedClick={() => setLoginDialogOpen(true)}
                          />
                        </div>
                      ) : (
                        <div
                          className="bg-muted/40 text-muted-foreground flex items-center justify-center rounded border border-dashed text-[10px] font-medium"
                          data-testid="run-grid-placeholder"
                          style={{ height: previewHeight }}
                        >
                          {placeholderLabel}
                        </div>
                      );

                      return (
                        <div
                          key={`${xKey}-${yIndex}`}
                          className="flex h-full flex-col gap-1 border-r p-2 transition-colors hover:bg-muted/30"
                        >
                          {canOpenDialog && !isLocked ? (
                            <button
                              type="button"
                              aria-label={`打开单元格 X${xIndex} Y${yIndex} 预览`}
                              className="focus-visible:ring-ring rounded text-left focus-visible:outline-none focus-visible:ring-2"
                              onClick={() => {
                                if (!rowCell) return;
                                openCellDialog(
                                  rowCell,
                                  xIndex,
                                  yIndex,
                                  xLabel,
                                  yLabel,
                                );
                              }}
                            >
                              {previewNode}
                            </button>
                          ) : (
                            previewNode
                          )}
                          <div className="space-y-0.5 text-[10px] leading-tight">
                            <p className="truncate font-medium">{`X${xIndex} · Y${yIndex}`}</p>
                            {seed !== null && seed !== undefined ? (
                              <p className="text-muted-foreground truncate">{`seed ${seed}`}</p>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent
          className="max-h-[90vh] overflow-auto p-4 sm:max-w-4xl sm:p-6"
          data-testid="cell-dialog"
        >
          <DialogHeader>
            <DialogTitle>{`单元格 X${selectedCell?.xIndex ?? "-"} · Y${selectedCell?.yIndex ?? "-"}`}</DialogTitle>
            <DialogDescription>
              {selectedCell
                ? `${selectedCell.yLabel} × ${selectedCell.xLabel}`
                : "-"}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="space-y-2">
              {currentDownloadUrl ? (
                <div className="bg-muted/20 h-[62vh] w-full rounded-sm border">
                  <picture>
                    {currentDisplayVariants?.avif ? (
                      <source
                        srcSet={currentDisplayVariants.avif}
                        type="image/avif"
                      />
                    ) : null}
                    {currentDisplayVariants?.webp ? (
                      <source
                        srcSet={currentDisplayVariants.webp}
                        type="image/webp"
                      />
                    ) : null}
                    <img
                      alt={
                        selectedCell
                          ? `${selectedCell.yLabel} × ${selectedCell.xLabel}`
                          : "cell preview"
                      }
                      className="h-full w-full object-contain"
                      decoding="async"
                      src={currentDownloadUrl}
                    />
                  </picture>
                </div>
              ) : (
                <div className="bg-muted/30 text-muted-foreground flex min-h-64 items-center justify-center rounded border border-dashed text-xs">
                  当前单元格无可用图片
                </div>
              )}

              {totalImages > 1 ? (
                <div className="flex items-center justify-between gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={showPreviousImage}
                    disabled={currentImageIndex <= 0}
                  >
                    上一张
                  </Button>
                  <p className="text-muted-foreground text-xs">{`${currentImageIndex + 1}/${totalImages}`}</p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={showNextImage}
                    disabled={currentImageIndex >= totalImages - 1}
                  >
                    下一张
                  </Button>
                </div>
              ) : null}
            </div>

            <div className="space-y-4">
              <div className="space-y-1">
                <p className="text-muted-foreground text-xs font-medium">
                  positive prompt
                </p>
                <p
                  className="bg-muted/30 max-h-52 overflow-auto rounded border p-2 text-xs whitespace-pre-wrap"
                  data-testid="cell-dialog-prompt"
                >
                  {selectedCell?.positivePrompt ?? "（无 positive prompt）"}
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  data-testid="cell-dialog-copy-prompt"
                  onClick={() => {
                    void copyText("prompt", selectedCell?.positivePrompt ?? "");
                  }}
                  disabled={!selectedCell}
                >
                  {copiedField === "prompt" ? "已复制 prompt" : "复制 prompt"}
                </Button>
              </div>

              <div className="space-y-2 text-xs">
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">seed</p>
                  <p data-testid="cell-dialog-seed">
                    {formatValue(selectedCell?.seed)}
                  </p>
                </div>
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">prompt_hash</p>
                  <p>{formatValue(selectedCell?.promptHash)}</p>
                </div>
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">batch</p>
                  <p>
                    {formatValue(
                      totalImages > 0
                        ? `${currentImageIndex + 1}/${totalImages}`
                        : null,
                    )}
                  </p>
                </div>
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">size</p>
                  <p>{sizeText}</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  data-testid="cell-dialog-copy-seed"
                  onClick={() => {
                    void copyText(
                      "seed",
                      selectedCell && selectedCell.seed !== null
                        ? String(selectedCell.seed)
                        : "",
                    );
                  }}
                  disabled={!selectedCell || selectedCell.seed === null}
                >
                  {copiedField === "seed" ? "已复制 seed" : "复制 seed"}
                </Button>

                {currentDownloadUrl ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={currentDownloadUrl} download>
                      下载图片
                    </a>
                  </Button>
                ) : (
                  <Button size="sm" variant="outline" disabled>
                    下载图片
                  </Button>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <AuthLoginDialog
        open={loginDialogOpen}
        onOpenChange={setLoginDialogOpen}
      />
    </div>
  );
}
