"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";

import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  normalizeStylePromptText,
  type StylePromptFavorite,
} from "@/lib/style-prompt-favorites";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Search01Icon,
  ArrowUp01Icon,
  ArrowDown01Icon,
  ArrowMoveUpRightIcon,
  StarIcon,
  Cancel01Icon,
  Settings02Icon,
} from "@hugeicons/core-free-icons";

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
  stylePromptFavorites: StylePromptFavorite[];
  favoriteByPrompt: Map<string, StylePromptFavorite>;
  isStylePromptFavoritesLoading: boolean;
  pendingStylePromptKeys: Set<string>;
  onCreateStylePromptFavorite: (options: {
    promptText: string;
    sourceYIndex: number | null;
  }) => Promise<StylePromptFavorite>;
  onDeleteStylePromptFavorite: (favorite: StylePromptFavorite) => Promise<void>;
  onUseStylePromptFavorite: (favorite: StylePromptFavorite) => Promise<void>;
  gridToolsPortalElement?: HTMLElement | null;
};

const DEV_IMAGE_DOM_CAP_NOTE = 300;

export function VirtualGrid({
  runDir,
  grid,
  blurhashMap,
  showNsfw,
  currentView,
  viewAccess,
  stylePromptFavorites,
  favoriteByPrompt,
  isStylePromptFavoritesLoading,
  pendingStylePromptKeys,
  onCreateStylePromptFavorite,
  onDeleteStylePromptFavorite,
  onUseStylePromptFavorite,
  gridToolsPortalElement,
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
  const [gridToolsOpen, setGridToolsOpen] = useState(false);
  const [jumpInputValue, setJumpInputValue] = useState("");
  const jumpInputRef = useRef<HTMLInputElement>(null);
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
  const {
    rowHeight,
    gridTemplateColumns,
    gridMinWidth,
    scrollViewportWidth,
    xHeaders,
  } = layout;

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

  const stylePromptMatchesByPrompt = useMemo(() => {
    const map = new Map<
      string,
      { rowIndex: number; yIndex: number; label: string }
    >();
    const yLabels = grid.y_labels ?? [];
    for (let i = 0; i < yLabels.length; i++) {
      const label = yLabels[i];
      if (typeof label !== "string") continue;
      const key = normalizeStylePromptText(label);
      if (!key || map.has(key)) continue;
      map.set(key, {
        rowIndex: i,
        yIndex: grid.y_indexes[i] ?? i,
        label,
      });
    }
    return map;
  }, [grid.y_labels, grid.y_indexes]);

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

  const openGridToolsForSearch = useCallback(() => {
    setGridToolsOpen(true);
    setTimeout(() => searchInputRef.current?.focus(), 0);
  }, []);

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
          setGridToolsOpen(false);
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

      if (document.activeElement === jumpInputRef.current) {
        if (e.key === "Escape") {
          e.preventDefault();
          setGridToolsOpen(false);
          jumpInputRef.current?.blur();
        }
        return;
      }

      if (e.key === "/" || (e.ctrlKey && e.key.toLowerCase() === "f")) {
        const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") return;
        e.preventDefault();
        openGridToolsForSearch();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [goToMatch, openGridToolsForSearch]);

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
          blurhash: preloadedBlurhash,
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

  const toggleStylePromptFavorite = useCallback(
    async (
      promptText: string,
      yIndex: number | null,
      favorite: StylePromptFavorite | null,
    ) => {
      if (!user) {
        setLoginDialogOpen(true);
        return;
      }

      try {
        if (favorite) {
          await onDeleteStylePromptFavorite(favorite);
          toast.success("已取消收藏画师串");
          return;
        }

        await onCreateStylePromptFavorite({ promptText, sourceYIndex: yIndex });
        toast.success("已收藏画师串");
      } catch {
        toast.error("收藏更新失败");
      }
    },
    [onCreateStylePromptFavorite, onDeleteStylePromptFavorite, user],
  );

  const jumpToStylePromptFavorite = useCallback(
    async (favorite: StylePromptFavorite) => {
      const match = stylePromptMatchesByPrompt.get(
        normalizeStylePromptText(favorite.prompt_text),
      );
      if (!match) {
        toast.error("当前模型未包含这个画师串");
        return;
      }

      const lineNum = match.rowIndex + 1;
      scrollToLineNumber(lineNum);
      syncUrlHashWithLineNumber(lineNum);
      setGridToolsOpen(false);

      void onUseStylePromptFavorite(favorite).catch((error: unknown) => {
        console.error("[style-prompt-favorites] Failed to mark used", error);
      });
    },
    [
      onUseStylePromptFavorite,
      scrollToLineNumber,
      stylePromptMatchesByPrompt,
      syncUrlHashWithLineNumber,
    ],
  );

  const removeStylePromptFavoriteFromList = useCallback(
    async (favorite: StylePromptFavorite) => {
      try {
        await onDeleteStylePromptFavorite(favorite);
        toast.success("已取消收藏画师串");
      } catch {
        toast.error("收藏更新失败");
      }
    },
    [onDeleteStylePromptFavorite],
  );

  const gridToolsMenu = (
    <Popover open={gridToolsOpen} onOpenChange={setGridToolsOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="hover:bg-primary/10 hover:text-primary data-[state=open]:bg-background/70 data-[state=open]:text-foreground focus-visible:ring-border relative inline-flex items-center gap-1 rounded-md border border-border/40 bg-background/50 px-2 py-1 font-medium text-muted-foreground transition-colors backdrop-blur-sm focus-visible:outline-none focus-visible:ring-1"
          title="网格工具"
          aria-label="网格工具"
        >
          <HugeiconsIcon
            icon={Settings02Icon}
            strokeWidth={2}
            className="size-3"
          />
          工具
          {searchQuery.trim() ? (
            <span
              aria-hidden="true"
              className="absolute -right-0.5 -top-0.5 size-1.5 rounded-full bg-amber-400"
            />
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={6}
        className="w-[calc(100vw-2rem)] max-w-96 gap-0 p-0 sm:w-96"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          searchInputRef.current?.focus();
        }}
      >
        <form
          className="border-b border-border/60 p-2.5"
          onSubmit={(e) => {
            e.preventDefault();
            goToMatch(1);
          }}
        >
          <div className="mb-1.5 text-[10px] font-medium text-muted-foreground">
            搜索画师串
          </div>
          <div className="relative">
            <HugeiconsIcon
              icon={Search01Icon}
              strokeWidth={2}
              className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground/50 pointer-events-none"
            />
            <Input
              ref={searchInputRef}
              type="text"
              className="h-7 w-full rounded-none border-border/50 py-0 pl-7 pr-28 text-xs shadow-none placeholder:text-muted-foreground/50 focus-visible:ring-1 focus-visible:ring-ring/30"
              placeholder="搜索画师..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <div className="absolute right-1 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
              {searchQuery.trim() ? (
                <span className="mr-0.5 text-[10px] tabular-nums text-muted-foreground/60">
                  {searchMatches.length > 0
                    ? `${activeMatchIndex >= 0 ? activeMatchIndex + 1 : 0}/${searchMatches.length}`
                    : "无结果"}
                </span>
              ) : null}
              {searchQuery ? (
                <Button
                  type="button"
                  size="icon-xs"
                  variant="ghost"
                  className="size-5"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    setSearchQuery("");
                    setActiveMatchIndex(-1);
                  }}
                  title="清空搜索"
                >
                  <HugeiconsIcon
                    icon={Cancel01Icon}
                    strokeWidth={2}
                    className="size-3"
                  />
                </Button>
              ) : null}
              <Button
                type="button"
                size="icon-xs"
                variant="ghost"
                className="size-5"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => goToMatch(-1)}
                title="上一个匹配"
                disabled={searchMatches.length === 0}
              >
                <HugeiconsIcon
                  icon={ArrowUp01Icon}
                  strokeWidth={2}
                  className="size-3"
                />
              </Button>
              <Button
                type="button"
                size="icon-xs"
                variant="ghost"
                className="size-5"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => goToMatch(1)}
                title="下一个匹配"
                disabled={searchMatches.length === 0}
              >
                <HugeiconsIcon
                  icon={ArrowDown01Icon}
                  strokeWidth={2}
                  className="size-3"
                />
              </Button>
            </div>
          </div>
        </form>

        <form
          className="flex items-end gap-2 border-b border-border/60 p-2.5"
          onSubmit={(e) => {
            e.preventDefault();
            const lineNum = parseInt(jumpInputValue, 10);
            if (scrollToLineNumber(lineNum)) {
              syncUrlHashWithLineNumber(lineNum);
              setJumpInputValue("");
              setGridToolsOpen(false);
            } else {
              toast.error(`行号必须在 1 到 ${grid.y_indexes.length} 之间`);
            }
          }}
        >
          <label className="min-w-0 flex-1">
            <span className="mb-1.5 block text-[10px] font-medium text-muted-foreground">
              跳转到行
            </span>
            <Input
              ref={jumpInputRef}
              type="number"
              min={1}
              max={grid.y_indexes.length}
              className="h-7 w-full rounded-none border-border/50 py-0 pl-2 pr-2 text-xs shadow-none placeholder:text-muted-foreground/50 focus-visible:ring-1 focus-visible:ring-ring/30 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none [-moz-appearance:textfield]"
              placeholder="行号"
              value={jumpInputValue}
              onChange={(e) => setJumpInputValue(e.target.value)}
            />
          </label>
          <Button type="submit" size="xs" variant="outline">
            <HugeiconsIcon
              icon={ArrowMoveUpRightIcon}
              strokeWidth={2}
              data-icon="inline-start"
            />
            跳转
          </Button>
        </form>

        <div className="p-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground">
            <HugeiconsIcon icon={StarIcon} strokeWidth={2} className="size-3" />
            收藏
          </div>
          {!user ? (
            <Button
              type="button"
              size="xs"
              variant="outline"
              className="w-full justify-start text-muted-foreground/80"
              onClick={() => {
                setGridToolsOpen(false);
                setLoginDialogOpen(true);
              }}
              title="登录后同步收藏"
            >
              <HugeiconsIcon
                icon={StarIcon}
                strokeWidth={2}
                data-icon="inline-start"
              />
              登录后同步收藏
            </Button>
          ) : (
            <Command className="max-h-72">
              <CommandInput placeholder="搜索收藏..." />
              <CommandList className="max-h-56">
                <CommandEmpty>
                  {isStylePromptFavoritesLoading ? "加载中" : "暂无收藏"}
                </CommandEmpty>
                <CommandGroup>
                  {stylePromptFavorites.map((favorite) => {
                    const match = stylePromptMatchesByPrompt.get(
                      normalizeStylePromptText(favorite.prompt_text),
                    );

                    return (
                      <CommandItem
                        key={favorite.id}
                        value={`${favorite.prompt_text} ${favorite.source_run_dir ?? ""}`}
                        onSelect={() => {
                          if (!match) {
                            toast.error("当前模型未包含这个画师串");
                            return;
                          }
                          void jumpToStylePromptFavorite(favorite);
                        }}
                        className={`items-start gap-2 py-2 ${match ? "" : "opacity-60"}`}
                      >
                        <Button
                          type="button"
                          size="icon-xs"
                          variant="ghost"
                          className="mt-0.5 size-5 text-amber-500 hover:text-amber-600"
                          title="取消收藏"
                          aria-label="取消收藏画师串"
                          disabled={pendingStylePromptKeys.has(
                            normalizeStylePromptText(favorite.prompt_text),
                          )}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                          }}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            void removeStylePromptFavoriteFromList(favorite);
                          }}
                        >
                          <HugeiconsIcon
                            icon={StarIcon}
                            strokeWidth={2}
                            className="size-3.5"
                          />
                        </Button>
                        <span className="min-w-0 flex-1">
                          <span className="line-clamp-2 font-mono text-[10px] leading-relaxed">
                            {favorite.prompt_text}
                          </span>
                          <span className="mt-0.5 block text-[10px] text-muted-foreground/60">
                            {match
                              ? `第 ${match.rowIndex + 1} 行`
                              : "当前模型无匹配"}
                          </span>
                        </span>
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );

  const gridToolsPortal = gridToolsPortalElement
    ? createPortal(gridToolsMenu, gridToolsPortalElement)
    : null;

  return (
    <>
      {gridToolsPortal}
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
                  {gridToolsPortalElement === undefined ? gridToolsMenu : null}
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
                const labelText =
                  cachedRow && cachedRow.status === "ready"
                    ? (cachedRow.yValue ?? preloadedYLabel) || "-"
                    : cachedRow && cachedRow.status === "error"
                      ? preloadedYLabel || "加载失败"
                      : yLabel;
                const normalizedLabelText = normalizeStylePromptText(
                  labelText === "-" || labelText === "加载失败"
                    ? ""
                    : labelText,
                );
                const stylePromptFavorite = normalizedLabelText
                  ? (favoriteByPrompt.get(normalizedLabelText) ?? null)
                  : null;

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
                    <div
                      className="grid h-full"
                      style={{ gridTemplateColumns }}
                    >
                      <VirtualGridRowLabel
                        cachedRow={cachedRow}
                        preloadedYLabel={preloadedYLabel}
                        yLabel={yLabel}
                        virtualRowIndex={virtualRow.index}
                        onCopyRowLabel={copyRowLabel}
                        highlightTerm={searchQuery.trim() || undefined}
                        favorite={stylePromptFavorite}
                        isFavoritePending={
                          normalizedLabelText
                            ? pendingStylePromptKeys.has(normalizedLabelText)
                            : false
                        }
                        onToggleFavorite={(value) =>
                          toggleStylePromptFavorite(
                            value,
                            yIndex,
                            stylePromptFavorite,
                          )
                        }
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
    </>
  );
}
