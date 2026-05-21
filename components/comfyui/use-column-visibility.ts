"use client";

import { useCallback, useMemo, useState } from "react";

const STORAGE_KEY = "sd-style-lab:column-visibility:v1";

function readStoredVisibility(runDir: string): Set<number> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as Record<string, number[]>;
    const arr = parsed[runDir];
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((n) => Number.isInteger(n) && n >= 0));
  } catch {
    return new Set();
  }
}

function writeStoredVisibility(runDir: string, hiddenColumns: Set<number>) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Record<string, number[]>) : {};
    parsed[runDir] = Array.from(hiddenColumns);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
  } catch {
    // ignore
  }
}

export type ColumnVisibilityOptions = {
  runDir: string;
  totalColumns: number;
};

export function useColumnVisibility({
  runDir,
  totalColumns,
}: ColumnVisibilityOptions) {
  const [hiddenColumns, setHiddenColumns] = useState<Set<number>>(() =>
    readStoredVisibility(runDir),
  );

  const toggleColumn = useCallback(
    (originalIndex: number) => {
      setHiddenColumns((prev) => {
        const next = new Set(prev);
        if (next.has(originalIndex)) {
          next.delete(originalIndex);
        } else {
          const currentlyVisible = totalColumns - next.size;
          if (currentlyVisible <= 1) return prev;
          next.add(originalIndex);
        }
        writeStoredVisibility(runDir, next);
        return next;
      });
    },
    [runDir, totalColumns],
  );

  const showAll = useCallback(() => {
    setHiddenColumns((prev) => {
      if (prev.size === 0) return prev;
      const next = new Set<number>();
      writeStoredVisibility(runDir, next);
      return next;
    });
  }, [runDir]);

  const hideAll = useCallback(() => {
    setHiddenColumns(() => {
      const next = new Set<number>();
      for (let i = 1; i < totalColumns; i++) {
        next.add(i);
      }
      writeStoredVisibility(runDir, next);
      return next;
    });
  }, [runDir, totalColumns]);

  const hasHiddenColumns = hiddenColumns.size > 0;

  const visibleOriginalIndexes = useMemo(() => {
    const result: number[] = [];
    for (let i = 0; i < totalColumns; i++) {
      if (!hiddenColumns.has(i)) {
        result.push(i);
      }
    }
    return result;
  }, [hiddenColumns, totalColumns]);

  return {
    hiddenColumns,
    visibleOriginalIndexes,
    visibleCount: visibleOriginalIndexes.length,
    hasHiddenColumns,
    toggleColumn,
    showAll,
    hideAll,
  } as const;
}
