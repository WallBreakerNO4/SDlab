"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { CachedRow, RowCell, RowMeta } from "./virtual-grid-types";
import { normalizeRowPayload } from "./virtual-grid-utils";

type UseVirtualGridRowsOptions = {
  runDir: string;
  showNsfw: boolean;
};

export function useVirtualGridRows({
  runDir,
  showNsfw,
}: UseVirtualGridRowsOptions) {
  const rowCacheRef = useRef<Map<number, CachedRow>>(new Map());
  const rowRequestsRef = useRef<Map<number, AbortController>>(new Map());
  const [rowCacheVersion, setRowCacheVersion] = useState(0);

  const requestRow = useCallback(
    async (yIndex: number) => {
      if (!Number.isFinite(yIndex) || yIndex < 0) return;
      if (rowCacheRef.current.has(yIndex)) return;
      if (rowRequestsRef.current.has(yIndex)) return;

      const controller = new AbortController();
      rowRequestsRef.current.set(yIndex, controller);

      try {
        const preferenceRequestKey = showNsfw ? "nsfw-on" : "nsfw-off";
        const response = await fetch(
          `/api/comfyui/run/${encodeURIComponent(runDir)}/row?y_index=${encodeURIComponent(String(yIndex))}&viewer_nsfw=${encodeURIComponent(preferenceRequestKey)}`,
          {
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
    [runDir, showNsfw],
  );

  useEffect(() => {
    const requests = rowRequestsRef.current;
    return () => {
      for (const controller of requests.values()) {
        controller.abort();
      }
      requests.clear();
    };
  }, []);

  return { rowCacheRef, rowCacheVersion, requestRow } as const;
}
