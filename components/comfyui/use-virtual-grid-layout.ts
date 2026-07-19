"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";

import type {
  BlurhashCell,
  CachedRow,
  RunGridIndexData,
} from "./virtual-grid-types";
import {
  getNonEmptyString,
  getPreferredAspectRatioFromCache,
  getXLabel,
} from "./virtual-grid-utils";

const CELL_MIN_WIDTH = 184;
const CELL_MAX_WIDTH = 400;
const LEFT_COLUMN_WIDTH = 220;
const CELL_PADDING_PX = 8;

export { CELL_MIN_WIDTH, CELL_MAX_WIDTH, LEFT_COLUMN_WIDTH };

type UseVirtualGridLayoutOptions = {
  scrollElementRef: RefObject<HTMLDivElement | null>;
  grid: RunGridIndexData;
  blurhashMap: Map<string, BlurhashCell>;
  rowCacheRef: RefObject<Map<number, CachedRow>>;
  rowCacheVersion: number;
  xHeaders?: { key: string; label: string }[];
};

export function useVirtualGridLayout({
  scrollElementRef,
  grid,
  blurhashMap,
  rowCacheRef,
  rowCacheVersion,
  xHeaders: externalXHeaders,
}: UseVirtualGridLayoutOptions) {
  "use no memo";
  const [scrollViewportWidth, setScrollViewportWidth] = useState<number | null>(
    null,
  );

  // 跟踪 ResizeObserver 已知的最新宽度，供 setScrollViewportWidthImmediate
  // 同步更新，避免工具栏过渡期间 debounce 到期后二次提交导致列宽突变。
  const lastWidthRef = useRef(0);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const element = scrollElementRef.current;
    if (!element) {
      return;
    }

    lastWidthRef.current = element.clientWidth;

    const commitWidth = (width: number) => {
      setScrollViewportWidth((previousWidth) =>
        previousWidth === width ? previousWidth : width,
      );
    };

    commitWidth(lastWidthRef.current);

    const update = () => {
      const nextWidth = element.clientWidth;
      if (nextWidth === lastWidthRef.current) return;
      lastWidthRef.current = nextWidth;

      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        debounceTimerRef.current = null;
        commitWidth(nextWidth);
      }, 200);
    };

    const observer = new ResizeObserver(() => {
      update();
    });

    observer.observe(element);

    return () => {
      observer.disconnect();
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scrollElementRef is a stable ref
  }, []);

  // 绕过 debounce 立即提交目标宽度，供工具栏展开/收起时预计算使用。
  // 同步 lastWidthRef 防止过渡期间 ResizeObserver 的 update 误触发二次提交。
  const setScrollViewportWidthImmediate = useCallback((width: number) => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    lastWidthRef.current = width;
    setScrollViewportWidth((previousWidth) =>
      previousWidth === width ? previousWidth : width,
    );
  }, []);

  const xHeaders = useMemo(() => {
    if (externalXHeaders) return externalXHeaders;
    return grid.x_columns.map((col, index) => {
      const label = getXLabel(col);
      const type = getNonEmptyString(col.type) ?? "x";
      return {
        key: `${index}:${type}:${label}`,
        label,
      };
    });
  }, [externalXHeaders, grid.x_columns]);

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
  }, [rowCacheVersion, blurhashMap, rowCacheRef]);

  const cellWidth = useMemo(() => {
    if (!scrollViewportWidth || scrollViewportWidth <= 0) {
      return CELL_MIN_WIDTH;
    }

    const xCount = Math.max(1, xHeaders.length);
    const available = scrollViewportWidth - LEFT_COLUMN_WIDTH;

    if (available <= 0) {
      return CELL_MIN_WIDTH;
    }

    return Math.min(
      CELL_MAX_WIDTH,
      Math.max(CELL_MIN_WIDTH, Math.floor(available / xCount)),
    );
  }, [scrollViewportWidth, xHeaders.length]);

  const previewHeight = useMemo(() => {
    const innerWidth = Math.max(1, cellWidth - CELL_PADDING_PX * 2);
    return Math.max(32, Math.round(innerWidth * preferredAspectRatio));
  }, [cellWidth, preferredAspectRatio]);

  const rowHeight = useMemo(() => {
    return CELL_PADDING_PX * 2 + previewHeight;
  }, [previewHeight]);

  const gridTemplateColumns = useMemo(
    () => `${LEFT_COLUMN_WIDTH}px repeat(${xHeaders.length}, ${cellWidth}px)`,
    [cellWidth, xHeaders.length],
  );

  const gridMinWidth = LEFT_COLUMN_WIDTH + xHeaders.length * CELL_MIN_WIDTH;

  return {
    scrollViewportWidth,
    setScrollViewportWidthImmediate,
    xHeaders,
    cellWidth,
    previewHeight,
    rowHeight,
    gridTemplateColumns,
    gridMinWidth,
  } as const;
}
