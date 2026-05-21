"use client";

import {
  useEffect,
  useMemo,
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

  useEffect(() => {
    const element = scrollElementRef.current;
    if (!element) {
      return;
    }

    let debounceTimer: ReturnType<typeof setTimeout> | null = null;

    const update = () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        setScrollViewportWidth(element.clientWidth);
      }, 200);
    };

    update();

    const observer = new ResizeObserver(() => {
      update();
    });

    observer.observe(element);

    return () => {
      observer.disconnect();
      if (debounceTimer) clearTimeout(debounceTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scrollElementRef is a stable ref
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
    xHeaders,
    cellWidth,
    previewHeight,
    rowHeight,
    gridTemplateColumns,
    gridMinWidth,
  } as const;
}