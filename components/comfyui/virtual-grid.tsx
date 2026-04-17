"use client";

import { useVirtualizer } from "@tanstack/react-virtual";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { Input } from "@/components/ui/input";
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
import { toast } from "sonner";
import { HugeiconsIcon } from "@hugeicons/react";
import { Tick01Icon, Copy01Icon, Download01Icon } from "@hugeicons/core-free-icons";

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
  y_labels?: string[];
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
const SCROLL_ANCHOR_STORAGE_VERSION = 1;
const SCROLL_ANCHOR_STORAGE_PREFIX = "sd-style-lab:model-grid-anchor:";
const MAX_ROW_OFFSET_RATIO = 0.999999;

const CELL_PADDING_PX = 8;

type SavedScrollAnchor = {
  version: typeof SCROLL_ANCHOR_STORAGE_VERSION;
  yIndex: number;
  rowOffsetRatio: number;
};

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

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function getScrollAnchorStorageKey(runDir: string): string {
  return `${SCROLL_ANCHOR_STORAGE_PREFIX}${runDir}`;
}

function parseSavedScrollAnchor(raw: string | null): SavedScrollAnchor | null {
  if (!raw) return null;

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) return null;
    const version = getFiniteNumber(parsed.version);
    const yIndex = getFiniteNumber(parsed.yIndex);
    const rowOffsetRatio = getFiniteNumber(parsed.rowOffsetRatio);
    if (
      version !== SCROLL_ANCHOR_STORAGE_VERSION ||
      yIndex === null ||
      yIndex < 0 ||
      rowOffsetRatio === null
    ) {
      return null;
    }

    return {
      version: SCROLL_ANCHOR_STORAGE_VERSION,
      yIndex,
      rowOffsetRatio: clampNumber(rowOffsetRatio, 0, MAX_ROW_OFFSET_RATIO),
    };
  } catch {
    return null;
  }
}

function loadSavedScrollAnchor(runDir: string): SavedScrollAnchor | null {
  if (typeof window === "undefined" || runDir.trim().length === 0) {
    return null;
  }

  try {
    return parseSavedScrollAnchor(
      window.sessionStorage.getItem(getScrollAnchorStorageKey(runDir)),
    );
  } catch {
    return null;
  }
}

function saveScrollAnchor(runDir: string, anchor: SavedScrollAnchor): void {
  if (typeof window === "undefined" || runDir.trim().length === 0) {
    return;
  }

  try {
    window.sessionStorage.setItem(
      getScrollAnchorStorageKey(runDir),
      JSON.stringify(anchor),
    );
  } catch {
    // Ignore storage failures (private mode / quota / disabled storage).
  }
}

function buildScrollAnchor(
  scrollOffset: number,
  yIndexes: number[],
  rowHeight: number,
): SavedScrollAnchor | null {
  if (
    !Number.isFinite(scrollOffset) ||
    !Number.isFinite(rowHeight) ||
    rowHeight <= 0 ||
    yIndexes.length === 0
  ) {
    return null;
  }

  const listIndex = clampNumber(
    Math.floor(scrollOffset / rowHeight),
    0,
    yIndexes.length - 1,
  );
  const yIndex = yIndexes[listIndex];
  if (typeof yIndex !== "number" || !Number.isFinite(yIndex) || yIndex < 0) {
    return null;
  }

  const rowOffsetRatio = clampNumber(
    (scrollOffset - listIndex * rowHeight) / rowHeight,
    0,
    MAX_ROW_OFFSET_RATIO,
  );

  return {
    version: SCROLL_ANCHOR_STORAGE_VERSION,
    yIndex,
    rowOffsetRatio,
  };
}

function resolveScrollOffsetFromAnchor(
  anchor: SavedScrollAnchor,
  yIndexes: number[],
  rowHeight: number,
): number | null {
  if (!Number.isFinite(rowHeight) || rowHeight <= 0 || yIndexes.length === 0) {
    return null;
  }

  let listIndex = yIndexes.indexOf(anchor.yIndex);
  if (listIndex < 0) {
    const nextIndex = yIndexes.findIndex((value) => value > anchor.yIndex);
    listIndex =
      nextIndex === -1 ? yIndexes.length - 1 : Math.max(0, nextIndex - 1);
  }

  return listIndex * rowHeight + anchor.rowOffsetRatio * rowHeight;
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

function getXLabel(column: RunGridXColumn | null | undefined): string {
  const raw = column?.description;
  const zh =
    raw && typeof raw.zh === "string" ? getNonEmptyString(raw.zh) : null;
  return zh ?? "";
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
  const didRestoreScrollRef = useRef(false);
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
  const [isJumpInputOpen, setIsJumpInputOpen] = useState(false);
  const [jumpInputValue, setJumpInputValue] = useState("");
  const jumpInputRef = useRef<HTMLInputElement>(null);

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
      const label = getXLabel(col);
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
    return CELL_PADDING_PX * 2 + previewHeight;
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

  const persistCurrentScrollAnchor = useCallback(() => {
    const scrollElement = scrollElementRef.current;
    if (!scrollElement) return;

    const anchor = buildScrollAnchor(
      scrollElement.scrollTop,
      grid.y_indexes,
      rowHeight,
    );
    if (!anchor) return;

    saveScrollAnchor(runDir, anchor);
  }, [grid.y_indexes, rowHeight, runDir]);

  useLayoutEffect(() => {
    if (didRestoreScrollRef.current) {
      return;
    }

    if (scrollViewportWidth === null) {
      return;
    }

    didRestoreScrollRef.current = true;
    const anchor = loadSavedScrollAnchor(runDir);
    if (!anchor) {
      return;
    }

    const targetOffset = resolveScrollOffsetFromAnchor(
      anchor,
      grid.y_indexes,
      rowHeight,
    );
    if (targetOffset === null) {
      return;
    }

    rowVirtualizer.scrollToOffset(targetOffset);
  }, [grid.y_indexes, rowHeight, rowVirtualizer, runDir, scrollViewportWidth]);

  useEffect(() => {
    const element = scrollElementRef.current;
    if (!element) {
      return;
    }

    let frameId: number | null = null;

    const persistOnNextFrame = () => {
      if (frameId !== null) {
        return;
      }

      frameId = window.requestAnimationFrame(() => {
        frameId = null;
        persistCurrentScrollAnchor();
      });
    };

    element.addEventListener("scroll", persistOnNextFrame, { passive: true });

    return () => {
      element.removeEventListener("scroll", persistOnNextFrame);
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
      persistCurrentScrollAnchor();
    };
  }, [persistCurrentScrollAnchor]);

  useEffect(() => {
    if (!didRestoreScrollRef.current) {
      return;
    }

    persistCurrentScrollAnchor();
  }, [persistCurrentScrollAnchor]);

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
        setTimeout(() => {
          setCopiedField((current) => (current === field ? null : current));
        }, 2000);
      } catch {
        setCopiedField(null);
      }
    },
    [],
  );

  const copyRowLabel = useCallback(async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success("已复制画师串");
    } catch {
      toast.error("复制失败");
    }
  }, []);

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
      className="flex h-full min-h-0 flex-col overflow-hidden border border-border/40 rounded-sm"
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
          <div className="bg-background/95 sticky top-0 z-30 border-b backdrop-blur supports-backdrop-filter:bg-background/80">
            <div className="grid" style={{ gridTemplateColumns }}>
              <div
                className="bg-background/95 sticky left-0 z-40 flex items-end justify-between border-r border-border/40 px-3 py-2 backdrop-blur supports-backdrop-filter:bg-background/80"
                data-testid="run-grid-corner"
              >
                <span className="text-muted-foreground/50 text-[10px] font-medium leading-none pb-0.5">
                  点击画师串可直接复制
                </span>
                <div className="flex items-center -mb-1 -mr-1">
                  {isJumpInputOpen ? (
                    <form
                      className="flex items-center w-16 relative"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const lineNum = parseInt(jumpInputValue, 10);
                        if (!isNaN(lineNum) && lineNum >= 1 && lineNum <= grid.y_indexes.length) {
                          rowVirtualizer.scrollToIndex(lineNum - 1, { align: "start" });
                          setIsJumpInputOpen(false);
                        } else {
                          toast.error(`行号必须在 1 到 ${grid.y_indexes.length} 之间`);
                        }
                      }}
                    >
                      <Input
                        ref={jumpInputRef}
                        type="number"
                        min={1}
                        max={grid.y_indexes.length}
                        className="h-5 pl-1.5 pr-4 py-0 text-[10px] w-full bg-background/50 rounded-[3px] shadow-none focus-visible:ring-1 focus-visible:ring-ring/30 border-border/50 placeholder:text-muted-foreground/30 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none [-moz-appearance:textfield]"
                        placeholder="行号"
                        value={jumpInputValue}
                        onChange={(e) => setJumpInputValue(e.target.value)}
                        onBlur={() => setIsJumpInputOpen(false)}
                      />
                      <span className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground/30 text-[9px] pointer-events-none">
                        ↵
                      </span>
                    </form>
                  ) : (
                    <button
                      type="button"
                      className="text-muted-foreground/40 hover:text-foreground/80 hover:bg-muted/50 rounded px-1.5 py-0.5 text-[10px] font-medium transition-all"
                      onClick={() => {
                        setIsJumpInputOpen(true);
                        setJumpInputValue("");
                        setTimeout(() => jumpInputRef.current?.focus(), 0);
                      }}
                      title="跳转到指定行"
                    >
                      点此跳转
                    </button>
                  )}
                </div>
              </div>
              {xHeaders.map((header) => (
                <div
                  key={header.key}
                  className="border-r border-border/40 bg-muted/10 px-3 py-2 flex items-start"
                >
                  <p className="text-muted-foreground text-[10px] font-medium leading-relaxed tracking-wide wrap-break-word max-w-full">
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
              const preloadedYLabel = grid.y_labels?.[virtualRow.index] ?? "";
              const yLabel =
                cachedRow && cachedRow.status === "ready"
                  ? (cachedRow.yValue ?? preloadedYLabel)
                  : preloadedYLabel;

              return (
                <div
                  key={virtualRow.key}
                  className="absolute left-0 top-0 w-full border-b border-border/40"
                  data-testid="run-grid-row"
                  data-row-index={yIndex}
                  style={{
                    height: virtualRow.size,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <div className="grid h-full" style={{ gridTemplateColumns }}>
                    <div
                      className="bg-background/95 sticky left-0 z-20 flex h-full w-full border-r border-border/40 px-3 py-2 text-xs backdrop-blur supports-backdrop-filter:bg-background/80 overflow-hidden"
                      data-testid="run-grid-y-label"
                    >
                      <div className="flex flex-col items-start justify-between w-full h-full gap-1 relative group/y-label">
                        <div className="flex-1 w-full overflow-hidden">
                          {(() => {
                            const labelText =
                              cachedRow && cachedRow.status === "ready"
                                ? ((cachedRow.yValue ?? preloadedYLabel) || "-")
                                : cachedRow && cachedRow.status === "error"
                                  ? (preloadedYLabel || "加载失败")
                                  : yLabel;

                            if (!labelText || labelText === "-") {
                              return (
                                <span className="text-muted-foreground/50 text-[10px]">
                                  -
                                </span>
                              );
                            }

                            if (labelText.includes(",")) {
                              const parts = labelText
                                .split(",")
                                .map((p) => p.trim())
                                .filter(Boolean);
                              return (
                                <div
                                  className="flex flex-wrap gap-1 content-start max-h-full cursor-pointer hover:opacity-80 transition-opacity"
                                  onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    void copyRowLabel(labelText);
                                  }}
                                  title="点击复制"
                                >
                                  {parts.map((part, i) => {
                                    let weight = 1;
                                    const match = part.match(/:([0-9.]+)[)\]}]*$/);
                                    if (match) {
                                      const w = parseFloat(match[1]);
                                      if (!isNaN(w)) {
                                        weight = w;
                                      }
                                    }

                                    if (weight === 1) {
                                      return (
                                        <span
                                          key={i}
                                          className="inline-block border bg-muted/60 text-muted-foreground border-border/50 rounded px-1.5 py-0.5 text-[10px] font-mono leading-none truncate max-w-full transition-all"
                                        >
                                          {part}
                                        </span>
                                      );
                                    }

                                    if (weight < 1) {
                                      const opacity = Math.max(0.3, weight);
                                      return (
                                        <span
                                          key={i}
                                          className="inline-block border bg-muted/30 text-muted-foreground border-border/20 rounded px-1.5 py-0.5 text-[10px] font-mono leading-none truncate max-w-full transition-all"
                                          style={{ opacity }}
                                        >
                                          {part}
                                        </span>
                                      );
                                    }

                                    // weight > 1
                                    const ratio = Math.min(Math.max((weight - 1) / 1, 0), 1);
                                    // Hue from 220 (blue) down to 0 (red)
                                    const hue = Math.round(220 - 220 * ratio);
                                    // Smoothly increase font weight from 400 to 800+
                                    const fontWeight = Math.min(Math.round(400 + (weight - 1) * 400), 900);

                                    const style = {
                                      "--weight-hue": hue,
                                      fontWeight
                                    } as React.CSSProperties;

                                    return (
                                      <span
                                        key={i}
                                        className="inline-block border rounded px-1.5 py-0.5 text-[10px] font-mono leading-none truncate max-w-full transition-all bg-[hsla(var(--weight-hue),80%,50%,0.15)] border-[hsla(var(--weight-hue),80%,50%,0.3)] text-[hsl(var(--weight-hue),80%,40%)] dark:text-[hsl(var(--weight-hue),80%,65%)]"
                                        style={style}
                                      >
                                        {part}
                                      </span>
                                    );
                                  })}
                                </div>
                              );
                            }

                            return (
                              <p
                                className="text-muted-foreground text-[10px] leading-relaxed wrap-break-word w-full cursor-pointer hover:opacity-80 transition-opacity"
                                onClick={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  void copyRowLabel(labelText);
                                }}
                                title="点击复制"
                              >
                                {labelText}
                              </p>
                            );
                          })()}
                        </div>
                        <div className="absolute bottom-4 left-0 right-0 h-8 bg-linear-to-t from-background/95 to-transparent pointer-events-none" />
                        <div className="absolute -bottom-1 -right-1 text-[10px] font-mono text-muted-foreground/30 select-none pointer-events-none">
                          #{virtualRow.index + 1}
                        </div>
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
                          className="w-full rounded border border-border/40 overflow-hidden relative"
                          style={{ height: previewHeight }}
                        >
                          <div className="w-full h-full transition-transform duration-500 ease-out group-hover/cell:scale-[1.03]">
                            <GridImage
                              thumbVariants={thumbVariants}
                              blurhash={effectiveBlurhash}
                              alt={
                                yLabel && xLabel
                                  ? `${yLabel} × ${xLabel}`
                                  : yLabel || xLabel || "图片预览"
                              }
                              locked={isLocked}
                              onLockedClick={() => setLoginDialogOpen(true)}
                            />
                          </div>
                          <div className="absolute inset-0 bg-foreground/0 transition-colors duration-300 pointer-events-none group-hover/cell:bg-foreground/5" />
                        </div>
                      ) : (
                        <div
                          className="bg-muted/40 text-muted-foreground flex items-center justify-center rounded border border-border/40 border-dashed text-[10px] font-medium"
                          data-testid="run-grid-placeholder"
                          style={{ height: previewHeight }}
                        >
                          {placeholderLabel}
                        </div>
                      );

                      return (
                        <div
                          key={`${xKey}-${yIndex}`}
                          className="flex h-full flex-col border-r border-border/40 p-2 transition-colors hover:bg-muted/20 group/cell"
                        >
                          {canOpenDialog && !isLocked ? (
                            <button
                              type="button"
                              aria-label="打开单元格预览"
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
            <DialogTitle>单元格预览</DialogTitle>
            <DialogDescription className="sr-only">
              单元格图片预览
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
                        selectedCell &&
                          (selectedCell.yLabel || selectedCell.xLabel)
                          ? [selectedCell.yLabel, selectedCell.xLabel]
                            .filter(Boolean)
                            .join(" × ")
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

            <div className="flex flex-col gap-6">
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <p className="text-muted-foreground text-xs font-medium">
                    Positive Prompt
                  </p>
                  <Button
                    type="button"
                    size="icon-xs"
                    variant="ghost"
                    className="h-6 w-6 text-muted-foreground hover:text-foreground"
                    data-testid="cell-dialog-copy-prompt"
                    onClick={() => {
                      void copyText("prompt", selectedCell?.positivePrompt ?? "");
                    }}
                    disabled={!selectedCell}
                    title="复制 Prompt"
                  >
                    {copiedField === "prompt" ? (
                      <HugeiconsIcon icon={Tick01Icon} className="h-3 w-3" />
                    ) : (
                      <HugeiconsIcon icon={Copy01Icon} className="h-3 w-3" />
                    )}
                  </Button>
                </div>
                <div
                  className="bg-muted/30 max-h-64 overflow-auto rounded-md border p-3 text-xs leading-relaxed whitespace-pre-wrap"
                  data-testid="cell-dialog-prompt"
                >
                  {selectedCell?.positivePrompt ?? "（无 positive prompt）"}
                </div>
              </div>

              <div className="space-y-3">
                <p className="text-muted-foreground text-xs font-medium">
                  Parameters
                </p>
                <div className="bg-muted/20 rounded-md border p-3 text-xs">
                  <div className="flex flex-col gap-y-4">
                    <div className="space-y-1.5">
                      <p className="text-muted-foreground font-medium">Seed</p>
                      <div className="group flex items-start gap-2">
                        <p
                          className="break-all font-mono"
                          data-testid="cell-dialog-seed"
                        >
                          {formatValue(selectedCell?.seed)}
                        </p>
                        <Button
                          type="button"
                          size="icon-xs"
                          variant="ghost"
                          className="h-5 w-5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
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
                          title="复制 Seed"
                        >
                          {copiedField === "seed" ? (
                            <HugeiconsIcon icon={Tick01Icon} className="h-3 w-3" />
                          ) : (
                            <HugeiconsIcon icon={Copy01Icon} className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <p className="text-muted-foreground font-medium">Size</p>
                      <p className="font-mono">{sizeText}</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-auto pt-4">
                {currentDownloadUrl ? (
                  <Button asChild className="w-full" size="sm">
                    <a href={currentDownloadUrl} download>
                      <HugeiconsIcon icon={Download01Icon} className="mr-2 h-4 w-4" />
                      下载图片
                    </a>
                  </Button>
                ) : (
                  <Button className="w-full" size="sm" disabled>
                    <HugeiconsIcon icon={Download01Icon} className="mr-2 h-4 w-4" />
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
