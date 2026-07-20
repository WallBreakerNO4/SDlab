"use client";

import { useTranslations } from "next-intl";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Search01Icon,
  ArrowUp01Icon,
  ArrowDown01Icon,
  ArrowMoveUpRightIcon,
  Cancel01Icon,
  Settings02Icon,
  LayoutThreeColumnIcon,
} from "@hugeicons/core-free-icons";

import { VirtualGridPreviewCell } from "./virtual-grid-preview-cell";
import { VirtualGridRowLabel } from "./virtual-grid-row-label";
import { VirtualGridCellDialog } from "./virtual-grid-cell-dialog";
import {
  GridFavoritesPanel,
  type GridFavoritesPanelRow,
} from "./grid-favorites-panel";
import { useVirtualGridLayout } from "./use-virtual-grid-layout";
import { useVirtualGridRows } from "./use-virtual-grid-rows";
import { useVirtualGridScroll } from "./use-virtual-grid-scroll";
import {
  buildScrollAnchor,
  getPreferredVariantCacheKey,
  getXLabel,
  getNonEmptyString,
  resolveScrollOffsetFromAnchor,
} from "./virtual-grid-utils";
import { clearPrivateObjectUrlCache } from "./use-renderable-variant-source";
import { useColumnVisibility } from "./use-column-visibility";
import type { RunViewAccess } from "@/app/models/[runDir]/model-detail-types";
import { useStyleFavorites } from "@/app/models/[runDir]/use-style-favorites";
import {
  parseStyleItemsResponse,
  type StyleKey,
} from "@/lib/style-favorites";
import type {
  BlurhashCell,
  RowCell,
  RunGridIndexData,
  SavedScrollAnchor,
  SelectedCellPreview,
} from "./virtual-grid-types";

export type {
  BlurhashCell,
  RunGridIndexData,
  RunGridYPromptParts,
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
  onRefreshViewAccess: () => Promise<RunViewAccess | null>;
};

type PendingRestoreSession = {
  anchor: SavedScrollAnchor;
  token: number;
};

const DEV_IMAGE_DOM_CAP_NOTE = 300;
const SCROLL_OFFSET_EPSILON = 1;

export function VirtualGrid(props: VirtualGridProps) {
  "use no memo";

  const { user } = useAuth();
  // 收藏状态按用户隔离：切换登录用户/退出登录时整体重置
  // （参考 UserPreferencesProvider 的 key 重置模式），避免闪现上一用户的收藏态
  return <VirtualGridContent key={user?.id ?? "anonymous"} {...props} />;
}

function VirtualGridContent({
  runDir,
  grid,
  blurhashMap,
  showNsfw,
  currentView,
  viewAccess,
  onRefreshViewAccess,
}: VirtualGridProps) {
  "use no memo";

  const t = useTranslations("virtualGrid");
  const scrollElementRef = useRef<HTMLDivElement | null>(null);
  const toolsPanelRef = useRef<HTMLDivElement | null>(null);
  const loadedThumbKeysRef = useRef(new Set<string>());
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedCell, setSelectedCell] = useState<SelectedCellPreview | null>(
    null,
  );
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);
  const { user } = useAuth();

  const {
    favorites: styleFavorites,
    favoriteKeys,
    toggle: toggleStyleFavorite,
  } = useStyleFavorites();

  // style-items 映射（y_index → style_key）：bootstrap ready（即网格挂载）后
  // 惰性拉取，不限登录态。拉取失败/响应形态不符 → 静默降级为 null
  // （星标不渲染），不重试、不阻塞网格。
  const [styleKeyByYIndex, setStyleKeyByYIndex] = useState<ReadonlyMap<
    number,
    StyleKey
  > | null>(null);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(
          `/api/comfyui/run/${encodeURIComponent(runDir)}/style-items`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const items = parseStyleItemsResponse(await res.json());
        if (!items || cancelled) return;
        const map = new Map<number, StyleKey>();
        for (const item of items) {
          map.set(item.y_index, item.style_key);
        }
        if (!cancelled) setStyleKeyByYIndex(map);
      } catch {
        // 静默降级：星标不渲染，其余一切如常
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runDir]);

  // 星标点击：未登录 → 沿用网格既有按需登录弹窗；已登录 → 乐观 toggle
  const handleToggleFavorite = useCallback(
    (styleKey: StyleKey, label: string) => {
      if (!user) {
        setLoginDialogOpen(true);
        return;
      }
      void toggleStyleFavorite(styleKey, label);
    },
    [user, toggleStyleFavorite],
  );
  const [gridToolsOpen, setGridToolsOpen] = useState(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem("sd-style-lab:grid-tools-open") === "true";
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(
        "sd-style-lab:grid-tools-open",
        String(gridToolsOpen),
      );
    }
  }, [gridToolsOpen]);

  // VirtualGrid 卸载时清理所有缓存的私有图片 objectURL，防止内存泄漏
  useEffect(() => {
    return () => {
      clearPrivateObjectUrlCache();
    };
  }, []);

  const pendingRestoreRef = useRef<PendingRestoreSession | null>(null);
  const restoreSessionTokenRef = useRef(0);
  const suppressScrollAnchorPersistRef = useRef(false);

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
    onRefreshViewAccess,
  });

  const { hiddenColumns, toggleColumn, showAll, hideAll } = useColumnVisibility(
    { runDir, totalColumns: grid.x_columns.length },
  );

  const visibleXColumns = useMemo(() => {
    return grid.x_columns
      .map((col, originalIndex) => {
        const label = getXLabel(col);
        const type = getNonEmptyString(col.type) ?? "x";
        return {
          originalIndex,
          key: `${originalIndex}:${type}:${label}`,
          label,
          type,
        };
      })
      .filter((col) => !hiddenColumns.has(col.originalIndex));
  }, [grid.x_columns, hiddenColumns]);

  const layout = useVirtualGridLayout({
    scrollElementRef,
    grid,
    blurhashMap,
    rowCacheRef,
    rowCacheVersion,
    xHeaders: visibleXColumns.map((col) => ({
      key: col.key,
      label: col.label,
    })),
  });
  const {
    rowHeight,
    gridTemplateColumns,
    gridMinWidth,
    scrollViewportWidth,
    setScrollViewportWidthImmediate,
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
      suppressPersistRef: suppressScrollAnchorPersistRef,
    });

  const yPromptPartsByIndex = useMemo(() => {
    const result = new Map<
      number,
      NonNullable<RunGridIndexData["y_prompt_parts"]>[number]
    >();
    for (const promptParts of grid.y_prompt_parts ?? []) {
      result.set(promptParts.yIndex, promptParts);
    }
    return result;
  }, [grid.y_prompt_parts]);

  // 收藏面板数据：收藏 × style-items 客户端 join（favorites.style_key →
  // style-items Map → y_index → 网格行），label 取当前 run 网格行标签
  // （与行标签星标快照同一拼接规则），不用收藏快照。
  // 防御性过滤：style_key 不在当前 run style-items / 网格行内的项跳过。
  const favoritePanelRows = useMemo<GridFavoritesPanelRow[]>(() => {
    if (!styleKeyByYIndex || styleFavorites.length === 0) return [];
    const yIndexByStyleKey = new Map<StyleKey, number>();
    for (const [yIndex, styleKey] of styleKeyByYIndex) {
      yIndexByStyleKey.set(styleKey, yIndex);
    }
    const rowIndexByYIndex = new Map<number, number>();
    grid.y_indexes.forEach((yIndex, rowIndex) => {
      rowIndexByYIndex.set(yIndex, rowIndex);
    });
    const rows: GridFavoritesPanelRow[] = [];
    for (const entry of styleFavorites) {
      const yIndex = yIndexByStyleKey.get(entry.style_key);
      if (yIndex === undefined) continue;
      const rowIndex = rowIndexByYIndex.get(yIndex);
      if (rowIndex === undefined) continue;
      const promptParts = yPromptPartsByIndex.get(yIndex);
      const currentLabel = promptParts
        ? [promptParts.artist, promptParts.commonPrompt]
            .filter(Boolean)
            .join(" ")
        : (grid.y_labels?.[rowIndex] ?? "");
      rows.push({
        styleKey: entry.style_key,
        lineNumber: rowIndex + 1,
        label: currentLabel || entry.label,
      });
    }
    // 按行号升序
    rows.sort((a, b) => a.lineNumber - b.lineNumber);
    return rows;
  }, [
    styleFavorites,
    styleKeyByYIndex,
    grid.y_indexes,
    grid.y_labels,
    yPromptPartsByIndex,
  ]);

  // 面板点击跳转：复用既有行滚动 + hash 同步（lineNumber 为 1-based 行号）
  const handleJumpToFavorite = useCallback(
    (lineNumber: number) => {
      if (scrollToLineNumber(lineNumber)) {
        syncUrlHashWithLineNumber(lineNumber);
      }
    },
    [scrollToLineNumber, syncUrlHashWithLineNumber],
  );

  const searchMatches = useMemo(() => {
    const query = searchQuery.trim();
    if (!query) return [];
    const term = query.toLowerCase();
    const matches: { rowIndex: number; yIndex: number; label: string }[] = [];
    const yLabels = grid.y_labels ?? [];
    for (let i = 0; i < grid.y_indexes.length; i++) {
      const yIndex = grid.y_indexes[i] ?? i;
      const promptParts = yPromptPartsByIndex.get(yIndex);
      const searchableValues = promptParts
        ? [promptParts.artist, promptParts.commonPrompt]
        : [yLabels[i]];
      if (
        searchableValues.some(
          (value) =>
            typeof value === "string" && value.toLowerCase().includes(term),
        )
      ) {
        matches.push({
          rowIndex: i,
          yIndex,
          label: searchableValues.filter(Boolean).join(" "),
        });
      }
    }
    return matches;
  }, [searchQuery, grid.y_labels, grid.y_indexes, yPromptPartsByIndex]);

  const goToMatch = useCallback(
    (delta: number) => {
      if (searchMatches.length === 0) return;
      setActiveMatchIndex((prev) => {
        if (prev < 0) {
          // 从当前视口位置出发，找最近的匹配项（类似浏览器 Ctrl+F）
          const visibleItems = rowVirtualizer.getVirtualItems();
          const firstVisibleRow = visibleItems[0]?.index ?? 0;
          const lastVisibleRow =
            visibleItems[visibleItems.length - 1]?.index ?? 0;

          if (delta > 0) {
            // 找 firstVisibleRow 之后（含）的第一个匹配
            const target = searchMatches.find(
              (m) => m.rowIndex >= firstVisibleRow,
            );
            if (target) {
              return searchMatches.indexOf(target);
            }
            // 视口下方无匹配，回到第一个
            return 0;
          }

          // 上一个：找 lastVisibleRow 之前（含）的第一个匹配（从后往前）
          const target = searchMatches.findLast(
            (m) => m.rowIndex <= lastVisibleRow,
          );
          if (target) {
            return searchMatches.indexOf(target);
          }
          // 视口上方无匹配，跳到最后一个
          return searchMatches.length - 1;
        }
        return (prev + delta + searchMatches.length) % searchMatches.length;
      });
    },
    [searchMatches, rowVirtualizer],
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

  // 工具栏展开/收起的目标宽度，对应 toolsPanel 的 w-96 / w-10。
  const TOOLS_WIDTH_OPEN = 384;
  const TOOLS_WIDTH_CLOSED = 40;

  const toggleGridTools = useCallback(
    (nextOpen: boolean) => {
      if (nextOpen === gridToolsOpen) {
        return;
      }

      const scrollElement = scrollElementRef.current;
      if (scrollElement) {
        const pendingRestore = pendingRestoreRef.current;
        const anchor =
          pendingRestore?.anchor ??
          buildScrollAnchor(
            scrollElement.scrollTop,
            grid.y_indexes,
            rowHeight,
          );
        if (anchor) {
          if (!pendingRestore) {
            const token = restoreSessionTokenRef.current + 1;
            restoreSessionTokenRef.current = token;
            pendingRestoreRef.current = { anchor, token };
          }
          suppressScrollAnchorPersistRef.current = true;
        }

        // 预计算目标滚动宽度并在过渡起点立即提交，避免 debounce 到期后
        // 列宽突变引发的闪烁。同步 lastWidthRef 阻断过渡期间二次提交。
        const currentToolsWidth = gridToolsOpen
          ? TOOLS_WIDTH_OPEN
          : TOOLS_WIDTH_CLOSED;
        const targetToolsWidth = nextOpen
          ? TOOLS_WIDTH_OPEN
          : TOOLS_WIDTH_CLOSED;
        const targetScrollWidth =
          scrollElement.clientWidth + currentToolsWidth - targetToolsWidth;
        setScrollViewportWidthImmediate(targetScrollWidth);
      }
      setGridToolsOpen(nextOpen);
    },
    [grid.y_indexes, rowHeight, gridToolsOpen, setScrollViewportWidthImmediate],
  );

  const openGridToolsForSearch = useCallback(() => {
    toggleGridTools(true);
    setTimeout(() => searchInputRef.current?.focus(), 0);
  }, [toggleGridTools]);

  useEffect(() => {
    void rowHeight;
    rowVirtualizer.measure();

    const restoreSession = pendingRestoreRef.current;
    if (!restoreSession) {
      return;
    }
    const { anchor: restoreAnchor, token: restoreToken } = restoreSession;

    let initialFrameId: number | null = null;
    let releaseFrameId: number | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let cancelled = false;
    suppressScrollAnchorPersistRef.current = true;

    const releasePersistSuppression = () => {
      releaseFrameId = window.requestAnimationFrame(() => {
        if (
          !cancelled &&
          restoreSessionTokenRef.current === restoreToken
        ) {
          suppressScrollAnchorPersistRef.current = false;
        }
      });
    };

    function stopWaitingForLayout() {
      resizeObserver?.disconnect();
      toolsPanelRef.current?.removeEventListener(
        "transitionend",
        restoreWhenScrollRangeIsReady,
      );
    }

    function restoreWhenScrollRangeIsReady() {
      if (cancelled || pendingRestoreRef.current !== restoreSession) return;

      const scrollElement = scrollElementRef.current;
      if (!scrollElement) {
        pendingRestoreRef.current = null;
        stopWaitingForLayout();
        suppressScrollAnchorPersistRef.current = false;
        return;
      }

      rowVirtualizer.measure();
      const targetOffset = resolveScrollOffsetFromAnchor(
        restoreAnchor,
        grid.y_indexes,
        rowHeight,
      );
      if (targetOffset === null) {
        pendingRestoreRef.current = null;
        stopWaitingForLayout();
        suppressScrollAnchorPersistRef.current = false;
        return;
      }

      const currentMaxOffset = Math.max(
        0,
        scrollElement.scrollHeight - scrollElement.clientHeight,
      );
      const expectedMaxOffset = Math.max(
        0,
        grid.y_indexes.length * rowHeight - scrollElement.clientHeight,
      );
      const isWaitingForDomScrollRange =
        targetOffset <= expectedMaxOffset + SCROLL_OFFSET_EPSILON &&
        targetOffset > currentMaxOffset + SCROLL_OFFSET_EPSILON;

      if (isWaitingForDomScrollRange) {
        return;
      }

      pendingRestoreRef.current = null;
      stopWaitingForLayout();
      rowVirtualizer.scrollToOffset(targetOffset, { align: "start" });
      releasePersistSuppression();
    }

    resizeObserver = new ResizeObserver(restoreWhenScrollRangeIsReady);
    const scrollElement = scrollElementRef.current;
    if (scrollElement) {
      resizeObserver.observe(scrollElement);
      const scrollContent = scrollElement.firstElementChild;
      if (scrollContent instanceof HTMLElement) {
        resizeObserver.observe(scrollContent);
      }
    }
    toolsPanelRef.current?.addEventListener(
      "transitionend",
      restoreWhenScrollRangeIsReady,
    );

    initialFrameId = window.requestAnimationFrame(() => {
      restoreWhenScrollRangeIsReady();
    });

    return () => {
      cancelled = true;
      stopWaitingForLayout();
      if (initialFrameId !== null) {
        window.cancelAnimationFrame(initialFrameId);
      }
      if (releaseFrameId !== null) {
        window.cancelAnimationFrame(releaseFrameId);
      }
      if (
        pendingRestoreRef.current !== restoreSession &&
        restoreSessionTokenRef.current === restoreToken
      ) {
        suppressScrollAnchorPersistRef.current = false;
      }
    };
  }, [grid.y_indexes, rowHeight, rowVirtualizer, scrollViewportWidth]);

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
          toggleGridTools(false);
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
          toggleGridTools(false);
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
  }, [goToMatch, openGridToolsForSearch, toggleGridTools]);

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
        positivePrompt: positivePrompt ?? representative?.positive_prompt ?? "",
        items,
      });
      setDialogOpen(true);
    },
    [grid.prompts],
  );

  const copyRowLabel = useCallback(
    async (value: string) => {
      try {
        await navigator.clipboard.writeText(value);
        toast.success(t("copiedPrompt"));
      } catch {
        toast.error(t("copyFailed"));
      }
    },
    [t],
  );

  const copyPromptPart = useCallback(
    async (value: string, kind: "artist" | "common") => {
      try {
        await navigator.clipboard.writeText(value);
        toast.success(
          kind === "artist" ? t("copiedArtist") : t("copiedCommonPrompt"),
        );
      } catch {
        toast.error(t("copyFailed"));
      }
    },
    [t],
  );

  const toolsPanel = (
    <div
      ref={toolsPanelRef}
      className={cn(
        "flex flex-col border-l border-border/40 bg-background/95 backdrop-blur-sm transition-all duration-300 ease-in-out overflow-hidden",
        gridToolsOpen ? "w-96" : "w-10",
      )}
    >
      {!gridToolsOpen ? (
        <button
          type="button"
          onClick={() => toggleGridTools(true)}
          className="hover:bg-muted/50 group relative flex flex-1 flex-col items-center justify-center gap-1 py-3 transition-colors"
          title={t("openTools")}
          aria-label={t("openTools")}
        >
          <span
            aria-hidden="true"
            className="absolute left-0 top-1/2 h-8 w-0.5 -translate-y-1/2 rounded-full bg-primary/0 transition-colors group-hover:bg-primary/60"
          />
          <HugeiconsIcon
            icon={Settings02Icon}
            strokeWidth={2}
            className="size-4"
          />
          <span
            className="text-[10px] font-medium leading-tight"
            style={{ writingMode: "vertical-rl" }}
          >
            {t("toolsLabel")}
          </span>
          {searchQuery.trim() ? (
            <span
              aria-hidden="true"
              title={t("searchActiveLabel")}
              className="absolute top-1.5 right-1 flex min-w-4 h-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] font-semibold leading-none text-white"
            >
              {searchMatches.length > 99 ? "99+" : searchMatches.length}
            </span>
          ) : null}
        </button>
      ) : (
        <>
          <div className="flex items-center justify-between border-b border-border/40 px-3 py-2.5">
            <span className="flex items-center gap-1.5 text-sm font-medium">
              <HugeiconsIcon
                icon={Settings02Icon}
                strokeWidth={2}
                className="size-3.5 text-muted-foreground"
              />
              {t("gridTools")}
            </span>
            <Button
              type="button"
              size="icon-xs"
              variant="ghost"
              onClick={() => toggleGridTools(false)}
              title={t("collapseTools")}
              aria-label={t("collapseTools")}
            >
              <HugeiconsIcon
                icon={Cancel01Icon}
                strokeWidth={2}
                className="size-3.5"
              />
            </Button>
          </div>
          <div className="flex flex-1 flex-col gap-0 overflow-y-auto">
            {/* 搜索画师串 */}
            <Collapsible defaultOpen>
              <CollapsibleTrigger className="hover:bg-muted/40 flex w-full items-center justify-between border-b border-border/40 px-3 py-2 text-left text-xs font-medium transition-colors">
                <span className="flex items-center gap-1.5">
                  <HugeiconsIcon
                    icon={Search01Icon}
                    strokeWidth={2}
                    className="size-3 text-muted-foreground"
                  />
                  {t("searchPrompt")}
                </span>
                <span className="flex items-center gap-1.5">
                  <kbd className="rounded border border-border/40 bg-muted/30 px-1 py-0.5 text-[9px] font-medium text-muted-foreground/60">
                    /
                  </kbd>
                  <HugeiconsIcon
                    icon={ArrowDown01Icon}
                    strokeWidth={2}
                    className="size-3 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180"
                  />
                </span>
              </CollapsibleTrigger>
              <CollapsibleContent className="border-b border-border/40 bg-amber-500/[0.03]">
                <form
                  className="p-2.5"
                  onSubmit={(e) => {
                    e.preventDefault();
                    goToMatch(1);
                  }}
                >
                  <div className="relative">
                    <HugeiconsIcon
                      icon={Search01Icon}
                      strokeWidth={2}
                      className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground/50 pointer-events-none"
                    />
                    <Input
                      ref={searchInputRef}
                      type="text"
                      className="h-7 w-full rounded-none border-border/50 py-0 pl-7 pr-7 text-xs shadow-none placeholder:text-muted-foreground/50 focus-visible:ring-1 focus-visible:ring-ring/30"
                      placeholder={t("searchPlaceholder")}
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                    {searchQuery ? (
                      <Button
                        type="button"
                        size="icon-xs"
                        variant="ghost"
                        className="absolute right-1 top-1/2 -translate-y-1/2 size-5"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => {
                          setSearchQuery("");
                          setActiveMatchIndex(-1);
                        }}
                        title={t("clearSearch")}
                      >
                        <HugeiconsIcon
                          icon={Cancel01Icon}
                          strokeWidth={2}
                          className="size-3"
                        />
                      </Button>
                    ) : null}
                  </div>
                  <div className="mt-1.5 flex items-center justify-between">
                    <span className="text-[10px] tabular-nums text-muted-foreground/70">
                      {searchQuery.trim()
                        ? searchMatches.length > 0
                          ? t("matchCount", {
                              current:
                                activeMatchIndex >= 0
                                  ? activeMatchIndex + 1
                                  : 0,
                              total: searchMatches.length,
                            })
                          : t("noResults")
                        : t("searchShortcut")}
                    </span>
                    <div className="flex items-center gap-0.5">
                      <Button
                        type="button"
                        size="icon-xs"
                        variant="ghost"
                        className="size-5"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => goToMatch(-1)}
                        title={t("prevMatch")}
                        aria-label={t("prevMatch")}
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
                        title={t("nextMatch")}
                        aria-label={t("nextMatch")}
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
              </CollapsibleContent>
            </Collapsible>

            {/* 跳转到行 */}
            <Collapsible defaultOpen>
              <CollapsibleTrigger className="hover:bg-muted/40 flex w-full items-center justify-between border-b border-border/40 px-3 py-2 text-left text-xs font-medium transition-colors">
                <span className="flex items-center gap-1.5">
                  <HugeiconsIcon
                    icon={ArrowMoveUpRightIcon}
                    strokeWidth={2}
                    className="size-3 text-muted-foreground"
                  />
                  {t("jumpToRow")}
                </span>
                <HugeiconsIcon
                  icon={ArrowDown01Icon}
                  strokeWidth={2}
                  className="size-3 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180"
                />
              </CollapsibleTrigger>
              <CollapsibleContent className="border-b border-border/40">
                <form
                  className="flex items-end gap-2 p-2.5"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const lineNum = parseInt(jumpInputValue, 10);
                    if (scrollToLineNumber(lineNum)) {
                      syncUrlHashWithLineNumber(lineNum);
                      setJumpInputValue("");
                    } else {
                      toast.error(
                        t("rowRangeError", { max: grid.y_indexes.length }),
                      );
                    }
                  }}
                >
                  <label className="min-w-0 flex-1">
                    <Input
                      ref={jumpInputRef}
                      type="number"
                      min={1}
                      max={grid.y_indexes.length}
                      className="h-7 w-full rounded-none border-border/50 py-0 pl-2 pr-2 text-xs shadow-none placeholder:text-muted-foreground/50 focus-visible:ring-1 focus-visible:ring-ring/30 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none [-moz-appearance:textfield]"
                      placeholder={t("rowPlaceholder")}
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
                    {t("jumpButton")}
                  </Button>
                </form>
              </CollapsibleContent>
            </Collapsible>

            {/* 收藏的画师串 */}
            <GridFavoritesPanel
              isAuthenticated={!!user}
              rows={favoritePanelRows}
              onRequireLogin={() => setLoginDialogOpen(true)}
              onJumpToLine={handleJumpToFavorite}
            />

            {/* 列显示 */}
            <Collapsible>
              <CollapsibleTrigger className="hover:bg-muted/40 flex w-full items-center justify-between border-b border-border/40 px-3 py-2 text-left text-xs font-medium transition-colors">
                <span className="flex items-center gap-1.5">
                  <HugeiconsIcon
                    icon={LayoutThreeColumnIcon}
                    strokeWidth={2}
                    className="size-3 text-muted-foreground"
                  />
                  {t("columnVisibility")}
                </span>
                <HugeiconsIcon
                  icon={ArrowDown01Icon}
                  strokeWidth={2}
                  className="size-3 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180"
                />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="p-2.5">
                  <div className="mb-2 flex gap-2">
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={showAll}
                    >
                      {t("selectAll")}
                    </Button>
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={hideAll}
                    >
                      {t("selectNone")}
                    </Button>
                  </div>
                  <div className="flex max-h-48 flex-col gap-1 overflow-auto">
                    {grid.x_columns.map((col, originalIndex) => {
                      const label =
                        getXLabel(col) ||
                        t("columnLabel", { index: originalIndex + 1 });
                      const isHidden = hiddenColumns.has(originalIndex);
                      return (
                        <label
                          key={originalIndex}
                          className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 hover:bg-muted/30"
                        >
                          <Checkbox
                            checked={!isHidden}
                            onCheckedChange={() => toggleColumn(originalIndex)}
                          />
                          <span className="min-w-0 flex-1 truncate text-xs">
                            {label}
                          </span>
                          {col.type ? (
                            <span className="shrink-0 text-[10px] text-muted-foreground/60">
                              {col.type}
                            </span>
                          ) : null}
                        </label>
                      );
                    })}
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div
      className="flex h-full min-h-0 flex-row overflow-hidden border border-border/40 rounded-sm"
      data-testid="run-grid"
      data-row-count={grid.y_indexes.length}
      data-row-height={rowHeight}
    >
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
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
                />
                {visibleXColumns.map((col) => (
                  <div
                    key={col.key}
                    className="border-r border-border/40 bg-muted/10 px-3 py-2 flex items-start"
                  >
                    <p className="text-muted-foreground text-[10px] font-medium leading-relaxed tracking-wide wrap-break-word max-w-full">
                      {col.label}
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
                const promptParts = yPromptPartsByIndex.get(yIndex);
                const yLabel =
                  cachedRow && cachedRow.status === "ready"
                    ? (cachedRow.yValue ?? preloadedYLabel)
                    : preloadedYLabel;
                const styleKey = styleKeyByYIndex?.get(yIndex) ?? null;
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
                        promptParts={promptParts}
                        yLabel={yLabel}
                        virtualRowIndex={virtualRow.index}
                        onCopyRowLabel={copyRowLabel}
                        onCopyPromptPart={copyPromptPart}
                        highlightTerm={searchQuery.trim() || undefined}
                        favoriteStar={
                          styleKey
                            ? {
                                isFavorite: favoriteKeys.has(styleKey),
                                // label 快照与搜索摘要保持一致：Mixer 取
                                // artist + common 拼接，Legacy 取行标签串
                                onToggle: () =>
                                  handleToggleFavorite(
                                    styleKey,
                                    promptParts
                                      ? [
                                          promptParts.artist,
                                          promptParts.commonPrompt,
                                        ]
                                          .filter(Boolean)
                                          .join(" ")
                                      : yLabel,
                                  ),
                              }
                            : null
                        }
                      />

                      {visibleXColumns.map((col) => {
                        const xLabel = col.label;
                        const xKey = col.key;
                        const xIndex = col.originalIndex;
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
                            onRefreshViewAccess={onRefreshViewAccess}
                            onRequireLogin={() => setLoginDialogOpen(true)}
                            onOpenCellDialog={openCellDialog}
                            onThumbLoad={markThumbAsLoaded}
                            globallyLoadedKeys={loadedThumbKeysRef.current}
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
          onRefreshViewAccess={onRefreshViewAccess}
        />

        <AuthLoginDialog
          open={loginDialogOpen}
          onOpenChange={setLoginDialogOpen}
        />
      </div>
      {toolsPanel}
    </div>
  );
}
