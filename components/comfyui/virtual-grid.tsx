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
import { toast } from "sonner";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Copy01Icon,
  Download01Icon,
  Tick01Icon,
} from "@hugeicons/core-free-icons";

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
import { Input } from "@/components/ui/input";

import { BlurhashCanvas } from "./blurhash-canvas";
import { VirtualGridPreviewCell } from "./virtual-grid-preview-cell";
import { VirtualGridRowLabel } from "./virtual-grid-row-label";
import {
  buildScrollAnchor,
  formatValue,
  getNonEmptyString,
  getPreferredAspectRatioFromCache,
  getXLabel,
  loadSavedScrollAnchor,
  normalizeRowPayload,
  parseDialogImagePayload,
  parseLineNumberFromHash,
  resolveScrollOffsetFromAnchor,
  saveScrollAnchor,
} from "./virtual-grid-utils";
import type {
  BlurhashCell,
  CachedRow,
  RowCell,
  RowMeta,
  RunGridIndexData,
  RunGridXColumn,
  SelectedCellPreview,
  VariantUrls,
} from "./virtual-grid-types";

export type {
  BlurhashCell,
  RunGridIndexData,
  RunGridXColumn,
  VariantUrls,
} from "./virtual-grid-types";

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

export function VirtualGrid({ runDir, grid, blurhashMap }: VirtualGridProps) {
  "use no memo";

  const scrollElementRef = useRef<HTMLDivElement | null>(null);
  const didRestoreScrollRef = useRef(false);
  const dialogImageRequestRef = useRef<AbortController | null>(null);
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
  const [dialogImageVariants, setDialogImageVariants] =
    useState<VariantUrls | null>(null);
  const rowCacheRef = useRef<Map<number, CachedRow>>(new Map());
  const rowRequestsRef = useRef<Map<number, AbortController>>(new Map());
  const [rowCacheVersion, setRowCacheVersion] = useState(0);
  const { user } = useAuth();
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);
  const [isJumpInputOpen, setIsJumpInputOpen] = useState(false);
  const [jumpInputValue, setJumpInputValue] = useState("");
  const jumpInputRef = useRef<HTMLInputElement>(null);
  const [isDialogImageLoaded, setIsDialogImageLoaded] = useState(false);

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
    const fromCache = getPreferredAspectRatioFromCache(
      rowCacheRef.current.values(),
    );
    if (fromCache !== 1) return fromCache;

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
  // React will already skip compiling this path; keep the warning suppressed locally
  // so lint can still enforce the rest of the file.
  // eslint-disable-next-line react-hooks/incompatible-library
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
  const selectedXIndex = selectedCell?.xIndex ?? null;
  const selectedYIndex = selectedCell?.yIndex ?? null;
  const currentBatchIndex = currentItem?.batchIndex ?? null;
  const currentUserId = user?.id ?? null;
  const currentDisplayVariants = dialogImageVariants;
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
      dialogImageRequestRef.current?.abort();
      dialogImageRequestRef.current = null;
      setCopiedField(null);
      setCurrentImageIndex(0);
      setDialogImageVariants(null);
      setIsDialogImageLoaded(false);
    }
  }, [dialogOpen]);

  useEffect(() => {
    return () => {
      dialogImageRequestRef.current?.abort();
      dialogImageRequestRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (
      !dialogOpen ||
      selectedXIndex === null ||
      selectedYIndex === null ||
      currentBatchIndex === null
    ) {
      return;
    }

    let ignore = false;
    dialogImageRequestRef.current?.abort();
    setDialogImageVariants(null);
    setIsDialogImageLoaded(false);

    const controller = new AbortController();
    dialogImageRequestRef.current = controller;

    async function loadDialogImage() {
      try {
        const response = await fetch(
          `/api/comfyui/run/${encodeURIComponent(runDir)}/display?x_index=${encodeURIComponent(String(selectedXIndex))}&y_index=${encodeURIComponent(String(selectedYIndex))}&batch_index=${encodeURIComponent(String(currentBatchIndex))}`,
          {
            cache: "no-store",
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          return;
        }

        const raw: unknown = await response.json();
        const image = parseDialogImagePayload(raw);
        if (!ignore && image) {
          setDialogImageVariants(image);
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
      } finally {
        if (dialogImageRequestRef.current === controller) {
          dialogImageRequestRef.current = null;
        }
      }
    }

    void loadDialogImage();

    return () => {
      ignore = true;
      controller.abort();
      if (dialogImageRequestRef.current === controller) {
        dialogImageRequestRef.current = null;
      }
    };
  }, [
    currentBatchIndex,
    currentUserId,
    dialogOpen,
    runDir,
    selectedXIndex,
    selectedYIndex,
  ]);

  useEffect(() => {
    void rowHeight;
    rowVirtualizer.measure();
  }, [rowHeight, rowVirtualizer]);

  const scrollToLineNumber = useCallback(
    (lineNumber: number): boolean => {
      if (
        !Number.isSafeInteger(lineNumber) ||
        lineNumber < 1 ||
        lineNumber > grid.y_indexes.length
      ) {
        return false;
      }

      rowVirtualizer.scrollToIndex(lineNumber - 1, { align: "start" });
      return true;
    },
    [grid.y_indexes.length, rowVirtualizer],
  );

  const scrollToHashLine = useCallback(
    (rawHash: string): boolean => {
      const lineNumber = parseLineNumberFromHash(rawHash, grid.y_indexes.length);
      if (lineNumber === null) {
        return false;
      }

      return scrollToLineNumber(lineNumber);
    },
    [grid.y_indexes.length, scrollToLineNumber],
  );

  const syncUrlHashWithLineNumber = useCallback((lineNumber: number) => {
    if (typeof window === "undefined") {
      return;
    }

    const nextHash = encodeURIComponent(String(lineNumber));
    const nextUrl = `${window.location.pathname}${window.location.search}#${nextHash}`;

    window.history.replaceState(null, "", nextUrl);
  }, []);

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
    if (scrollToHashLine(window.location.hash)) {
      return;
    }

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
  }, [
    grid.y_indexes,
    rowHeight,
    rowVirtualizer,
    runDir,
    scrollToHashLine,
    scrollViewportWidth,
  ]);

  useEffect(() => {
    const handleHashChange = () => {
      scrollToHashLine(window.location.hash);
    };

    window.addEventListener("hashchange", handleHashChange);

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, [scrollToHashLine]);

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
          setRowCacheVersion((value) => value + 1);
          return;
        }

        if (!response.ok) {
          rowCacheRef.current.set(yIndex, {
            status: "error",
            yIndex,
            error: `http-${response.status}`,
          });
          setRowCacheVersion((value) => value + 1);
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
          setRowCacheVersion((value) => value + 1);
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
        setRowCacheVersion((value) => value + 1);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        rowCacheRef.current.set(yIndex, {
          status: "error",
          yIndex,
          error: "fetch-failed",
        });
        setRowCacheVersion((value) => value + 1);
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
      preloadedBlurhash: string | null,
    ) => {
      const items = cell.items.map((item) => ({
        batchIndex: item.batch_index,
        width: item.width,
        height: item.height,
        thumb: item.thumb,
        blurhash: item.blurhash ?? preloadedBlurhash,
      }));

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
      setDialogImageVariants(null);
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
    if (currentImageIndex <= 0) {
      return;
    }

    setDialogImageVariants(null);
    setCurrentImageIndex((index) => Math.max(0, index - 1));
  }, [currentImageIndex]);

  const showNextImage = useCallback(() => {
    if (!selectedCell || currentImageIndex >= selectedCell.items.length - 1) {
      return;
    }

    setDialogImageVariants(null);
    setCurrentImageIndex((index) => index + 1);
  }, [currentImageIndex, selectedCell]);

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
                        if (scrollToLineNumber(lineNum)) {
                          syncUrlHashWithLineNumber(lineNum);
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
              const yIndex = grid.y_indexes[virtualRow.index] ?? virtualRow.index;
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
                    <VirtualGridRowLabel
                      cachedRow={cachedRow}
                      preloadedYLabel={preloadedYLabel}
                      yLabel={yLabel}
                      virtualRowIndex={virtualRow.index}
                      onCopyRowLabel={copyRowLabel}
                    />

                    {xHeaders.map((header, xIndex) => {
                      const xLabel = header.label;
                      const xKey = header.key;
                      const rowEntry = rowCacheRef.current.get(yIndex);

                      return (
                        <VirtualGridPreviewCell
                          key={`${xKey}-${yIndex}`}
                          xKey={xKey}
                          xIndex={xIndex}
                          xLabel={xLabel}
                          yIndex={yIndex}
                          yLabel={yLabel}
                          rowEntry={rowEntry}
                          blurhashMap={blurhashMap}
                          previewHeight={previewHeight}
                          isAuthenticated={!!user}
                          onRequireLogin={() => setLoginDialogOpen(true)}
                          onOpenCellDialog={openCellDialog}
                        />
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
          <DialogHeader className="sr-only">
            <DialogTitle>单元格预览</DialogTitle>
            <DialogDescription className="sr-only">
              单元格图片预览
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="space-y-2">
              <div className="relative h-[62vh] w-full rounded-sm border bg-black overflow-hidden flex items-center justify-center">
                {currentItem?.blurhash ? (
                  <BlurhashCanvas
                    blurhash={currentItem.blurhash}
                    width={(() => {
                      const ratio =
                        (currentItem.width ?? 1) / (currentItem.height ?? 1);
                      return ratio > 1
                        ? 32
                        : Math.max(1, Math.round(32 * ratio));
                    })()}
                    height={(() => {
                      const ratio =
                        (currentItem.width ?? 1) / (currentItem.height ?? 1);
                      return ratio > 1
                        ? Math.max(1, Math.round(32 / ratio))
                        : 32;
                    })()}
                    className={`absolute inset-0 m-auto h-full w-full object-contain blur-md transition-opacity duration-500 ${isDialogImageLoaded ? "opacity-0" : "opacity-100"}`}
                  />
                ) : null}
                {currentDownloadUrl ? (
                  <picture className="absolute inset-0 h-full w-full pointer-events-none">
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
                        selectedCell && (selectedCell.yLabel || selectedCell.xLabel)
                          ? [selectedCell.yLabel, selectedCell.xLabel]
                              .filter(Boolean)
                              .join(" × ")
                          : "cell preview"
                      }
                      className={`h-full w-full object-contain transition-opacity duration-500 pointer-events-auto ${isDialogImageLoaded ? "opacity-100" : "opacity-0"}`}
                      decoding="async"
                      src={currentDownloadUrl}
                      onLoad={() => setIsDialogImageLoaded(true)}
                    />
                  </picture>
                ) : null}
              </div>

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
                      <HugeiconsIcon
                        icon={Download01Icon}
                        className="mr-2 h-4 w-4"
                      />
                      下载图片
                    </a>
                  </Button>
                ) : (
                  <Button className="w-full" size="sm" disabled>
                    <HugeiconsIcon
                      icon={Download01Icon}
                      className="mr-2 h-4 w-4"
                    />
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
