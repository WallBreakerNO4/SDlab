"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { useAuth } from "@/components/auth-provider";
import { Input } from "@/components/ui/input";

import { VirtualGridPreviewCell } from "./virtual-grid-preview-cell";
import { VirtualGridRowLabel } from "./virtual-grid-row-label";
import { VirtualGridCellDialog } from "./virtual-grid-cell-dialog";
import { useVirtualGridLayout } from "./use-virtual-grid-layout";
import { useVirtualGridRows } from "./use-virtual-grid-rows";
import { useVirtualGridScroll } from "./use-virtual-grid-scroll";
import { getPreferredVariantCacheKey } from "./virtual-grid-utils";
import type { RunViewAccess } from "@/app/models/[runDir]/model-detail-types";
import type {
  BlurhashCell,
  RowCell,
  RunGridIndexData,
  SelectedCellPreview,
} from "./virtual-grid-types";

export type {
  BlurhashCell,
  RunGridIndexData,
  RunGridXColumn,
  VariantSources,
} from "./virtual-grid-types";

type VirtualGridProps = {
  runDir: string;
  grid: RunGridIndexData;
  blurhashMap: Map<string, BlurhashCell>;
  showNsfw: boolean;
  currentView: { release_id: string } | null;
  viewAccess: RunViewAccess | null;
};

const DEV_IMAGE_DOM_CAP_NOTE = 300;

export function VirtualGrid({
  runDir,
  grid,
  blurhashMap,
  showNsfw,
  currentView,
  viewAccess,
}: VirtualGridProps) {
  "use no memo";

  const scrollElementRef = useRef<HTMLDivElement | null>(null);
  const loadedThumbKeysRef = useRef(new Set<string>());
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedCell, setSelectedCell] = useState<SelectedCellPreview | null>(
    null,
  );
  const { user } = useAuth();
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);
  const [isJumpInputOpen, setIsJumpInputOpen] = useState(false);
  const [jumpInputValue, setJumpInputValue] = useState("");
  const jumpInputRef = useRef<HTMLInputElement>(null);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeMatchIndex, setActiveMatchIndex] = useState(-1);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const { rowCacheRef, rowCacheVersion, requestRow } = useVirtualGridRows({
    runDir,
    showNsfw,
    releaseId: currentView?.release_id ?? null,
    viewAccess,
  });
  const layout = useVirtualGridLayout({
    scrollElementRef,
    grid,
    blurhashMap,
    rowCacheRef,
    rowCacheVersion,
  });
  const { rowHeight, gridTemplateColumns, gridMinWidth, scrollViewportWidth, xHeaders } =
    layout;

  // eslint-disable-next-line react-hooks/incompatible-library
  const rowVirtualizer = useVirtualizer({
    count: grid.y_indexes.length,
    getScrollElement: () => scrollElementRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
  });

  const { scrollToLineNumber, syncUrlHashWithLineNumber } =
    useVirtualGridScroll({
      scrollElementRef,
      rowVirtualizer,
      gridYIndexes: grid.y_indexes,
      rowHeight,
      runDir,
      scrollViewportWidth,
    });

  const searchMatches = useMemo(() => {
    const query = searchQuery.trim();
    if (!query) return [];
    const term = query.toLowerCase();
    const matches: { rowIndex: number; yIndex: number; label: string }[] = [];
    const yLabels = grid.y_labels ?? [];
    for (let i = 0; i < yLabels.length; i++) {
      const label = yLabels[i];
      if (typeof label === "string" && label.toLowerCase().includes(term)) {
        matches.push({ rowIndex: i, yIndex: grid.y_indexes[i] ?? i, label });
      }
    }
    return matches;
  }, [searchQuery, grid.y_labels, grid.y_indexes]);

  const goToMatch = useCallback(
    (delta: number) => {
      if (searchMatches.length === 0) return;
      setActiveMatchIndex((prev) => {
        if (prev < 0) {
          return delta > 0 ? 0 : searchMatches.length - 1;
        }
        return (prev + delta + searchMatches.length) % searchMatches.length;
      });
    },
    [searchMatches.length],
  );

  useEffect(() => {
    if (activeMatchIndex < 0 || searchMatches.length === 0) return;
    const match = searchMatches[activeMatchIndex];
    const lineNum = match.rowIndex + 1;
    scrollToLineNumber(lineNum);
    syncUrlHashWithLineNumber(lineNum);
  }, [
    activeMatchIndex,
    searchMatches,
    scrollToLineNumber,
    syncUrlHashWithLineNumber,
  ]);

  useEffect(() => {
    setActiveMatchIndex(-1);
  }, [searchQuery]);

  const markThumbAsLoaded = useCallback((cacheKey: string) => {
    const key = cacheKey.trim();
    if (!key) {
      return;
    }

    loadedThumbKeysRef.current.add(key);
  }, []);

  const virtualRows = rowVirtualizer.getVirtualItems();
  const isDevEnv = process.env.NODE_ENV !== "production";

  useEffect(() => {
    void rowHeight;
    rowVirtualizer.measure();
  }, [rowHeight, rowVirtualizer]);

  useEffect(() => {
    const yIndexes = grid.y_indexes;
    for (const virtualRow of virtualRows) {
      const yIndex = yIndexes[virtualRow.index];
      if (typeof yIndex !== "number") continue;
      void requestRow(yIndex);
    }
  }, [grid.y_indexes, requestRow, virtualRows]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (document.activeElement === searchInputRef.current) {
        if (e.key === "Escape") {
          e.preventDefault();
          setIsSearchOpen(false);
          searchInputRef.current?.blur();
          return;
        }
        if (e.key === "Enter") {
          e.preventDefault();
          goToMatch(e.shiftKey ? -1 : 1);
          return;
        }
        return;
      }

      if (e.key === "/" || (e.ctrlKey && e.key.toLowerCase() === "f")) {
        const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") return;
        e.preventDefault();
        setIsSearchOpen(true);
        setIsJumpInputOpen(false);
        setTimeout(() => searchInputRef.current?.focus(), 0);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [goToMatch]);

  const openCellDialog = useCallback(
    (
      cell: RowCell,
      xIndex: number,
      yIndex: number,
      xLabel: string,
      yLabel: string,
      preloadedBlurhash: string | null,
    ) => {
      const items = cell.items.map((item) => {
        const thumbKey = getPreferredVariantCacheKey(item.thumb);

        return {
          batchIndex: item.batch_index,
          width: item.width,
          height: item.height,
          thumb: item.thumb,
          display: item.display,
          thumbLoaded: thumbKey
            ? loadedThumbKeysRef.current.has(thumbKey)
            : false,
          blurhash: item.blurhash ?? preloadedBlurhash,
        };
      });

      const representative =
        cell.items.find((item) => item.display || item.thumb)?.meta ??
        cell.items[0]?.meta ??
        null;
      const positivePrompt = grid.prompts.find(
        (prompt) => prompt.id === representative?.prompt_id,
      )?.positive_prompt;
      const seed = representative?.seed ?? null;
      const promptHash = representative?.prompt_hash ?? null;

      setSelectedCell({
        xIndex,
        yIndex,
        xLabel,
        yLabel,
        seed,
        promptHash,
        positivePrompt:
          positivePrompt ??
          representative?.positive_prompt ??
          "（无 positive prompt）",
        items,
      });
      setDialogOpen(true);
    },
    [grid.prompts],
  );

  const copyRowLabel = useCallback(async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success("已复制画师串");
    } catch {
      toast.error("复制失败");
    }
  }, []);

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
                className="bg-background/95 sticky left-0 z-40 flex flex-col gap-1.5 border-r border-border/40 px-3 py-2 backdrop-blur supports-backdrop-filter:bg-background/80"
                data-testid="run-grid-corner"
              >
                <div className="flex items-end justify-between w-full">
                  <span className="text-muted-foreground/50 text-[10px] font-medium leading-none pb-0.5">
                    点击画师串可直接复制
                  </span>
                  <div className="flex items-center -mb-1 -mr-1 gap-1">
                    {isSearchOpen ? (
                      <form
                        className="flex items-center gap-1 w-36 relative"
                        onSubmit={(e) => {
                          e.preventDefault();
                          goToMatch(1);
                        }}
                      >
                        <Input
                          ref={searchInputRef}
                          type="text"
                          className="h-5 pl-1.5 pr-14 py-0 text-[10px] w-full bg-background/50 rounded-[3px] shadow-none focus-visible:ring-1 focus-visible:ring-ring/30 border-border/50 placeholder:text-muted-foreground/30"
                          placeholder="搜索画师..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          onBlur={() => setIsSearchOpen(false)}
                        />
                        {searchQuery.trim() && (
                          <span className="absolute right-10 top-1/2 -translate-y-1/2 text-muted-foreground/50 text-[9px] pointer-events-none">
                            {searchMatches.length > 0
                              ? `${activeMatchIndex >= 0 ? activeMatchIndex + 1 : 0}/${searchMatches.length}`
                              : "无结果"}
                          </span>
                        )}
                        <button
                          type="button"
                          className="text-muted-foreground/40 hover:text-foreground/80 hover:bg-muted/50 rounded px-1 py-0.5 text-[10px] font-medium transition-all"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => goToMatch(-1)}
                          title="上一个匹配"
                          disabled={searchMatches.length === 0}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="text-muted-foreground/40 hover:text-foreground/80 hover:bg-muted/50 rounded px-1 py-0.5 text-[10px] font-medium transition-all"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => goToMatch(1)}
                          title="下一个匹配"
                          disabled={searchMatches.length === 0}
                        >
                          ↓
                        </button>
                      </form>
                    ) : (
                      <button
                        type="button"
                        className="text-muted-foreground/40 hover:text-foreground/80 hover:bg-muted/50 rounded px-1.5 py-0.5 text-[10px] font-medium transition-all"
                        onClick={() => {
                          setIsSearchOpen(true);
                          setIsJumpInputOpen(false);
                          setSearchQuery("");
                          setTimeout(() => searchInputRef.current?.focus(), 0);
                        }}
                        title="搜索画师 (/)"
                      >
                        搜索
                      </button>
                    )}
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
                          setIsSearchOpen(false);
                          setJumpInputValue("");
                          setTimeout(() => jumpInputRef.current?.focus(), 0);
                        }}
                        title="跳转到指定行"
                      >
                        跳转
                      </button>
                    )}
                  </div>
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
                      highlightTerm={searchQuery.trim() || undefined}
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
                          previewHeight={layout.previewHeight}
                          isAuthenticated={!!user}
                          currentUserId={user?.id ?? null}
                          grant={viewAccess?.grant ?? null}
                          onRequireLogin={() => setLoginDialogOpen(true)}
                          onOpenCellDialog={openCellDialog}
                          onThumbLoad={markThumbAsLoaded}
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

      <VirtualGridCellDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        cell={selectedCell}
        currentUserId={user?.id ?? null}
        grant={viewAccess?.grant ?? null}
      />

      <AuthLoginDialog
        open={loginDialogOpen}
        onOpenChange={setLoginDialogOpen}
      />
    </div>
  );
}
