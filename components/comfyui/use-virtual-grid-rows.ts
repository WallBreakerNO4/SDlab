"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { RunViewAccess } from "@/app/models/[runDir]/model-detail-types";
import {
  privateObjectProxyUrl,
  publicObjectUrl,
} from "@/lib/r2-url";

import type { CachedRow, RowCell, RowMeta } from "./virtual-grid-types";
import { normalizeRowPayload } from "./virtual-grid-utils";

const MAX_CONCURRENT = 4;

const globalRowCache = new Map<string, CachedRow>();

function makeGlobalCacheKey(
  runDir: string,
  releaseId: string,
  viewerVariant: string,
  yIndex: number,
): string {
  return `${runDir}/${releaseId}/${viewerVariant}/${yIndex}`;
}

type UseVirtualGridRowsOptions = {
  runDir: string;
  showNsfw: boolean;
  releaseId: string | null;
  viewAccess: RunViewAccess | null;
};

function buildRowManifestUrl(options: {
  runDir: string;
  yIndex: number;
  releaseId: string;
  showNsfw: boolean;
  viewAccess: RunViewAccess | null;
}): string {
  const { runDir, yIndex, releaseId, showNsfw, viewAccess } = options;
  if (!viewAccess) {
    return publicObjectUrl(
      `runs/${runDir}/view/v2/${releaseId}/rows/public/${yIndex}.json`,
    );
  }

  const viewerVariant = showNsfw ? "auth_nsfw" : "auth_sfw";
  return privateObjectProxyUrl(
    `runs/${runDir}/view/v2/${releaseId}/rows/${viewerVariant}/${yIndex}.json`,
    viewAccess.grant,
  );
}

function pickRepresentativeMeta(cell: RowCell): RowMeta | null {
  return (
    cell.items.find((item) => item.display || item.thumb)?.meta ??
    cell.items[0]?.meta ??
    null
  );
}

export function useVirtualGridRows({
  runDir,
  showNsfw,
  releaseId,
  viewAccess,
}: UseVirtualGridRowsOptions) {
  const rowCacheRef = useRef<Map<number, CachedRow>>(new Map());
  const rowRequestsRef = useRef<Map<number, AbortController>>(new Map());
  const pendingYIndexesRef = useRef<Set<number>>(new Set());
  const runningCountRef = useRef(0);
  const flushPendingRef = useRef<() => void>(() => {});
  const [rowCacheVersion, setRowCacheVersion] = useState(0);

  const viewerVariant = viewAccess
    ? showNsfw
      ? "auth_nsfw"
      : "auth_sfw"
    : "public";

  useEffect(() => {
    if (!releaseId) return;
    let didHydrate = false;
    const prefix = `${runDir}/${releaseId}/${viewerVariant}/`;
    for (const [key, cached] of globalRowCache) {
      if (key.startsWith(prefix) && !rowCacheRef.current.has(cached.yIndex)) {
        rowCacheRef.current.set(cached.yIndex, cached);
        didHydrate = true;
      }
    }
    if (didHydrate) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydration triggers re-render
      setRowCacheVersion((value) => value + 1);
    }
  }, [runDir, releaseId, viewerVariant]);

  const doFetchRow = useCallback(
    async (yIndex: number): Promise<void> => {
      const rid = releaseId;
      if (!rid) return;

      const controller = new AbortController();
      rowRequestsRef.current.set(yIndex, controller);

      try {
        const response = await fetch(
          buildRowManifestUrl({
            runDir,
            yIndex,
            releaseId: rid,
            showNsfw,
            viewAccess,
          }),
          {
            signal: controller.signal,
            cache: "force-cache",
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
          if (cell.items.length === 0) {
            continue;
          }
          cellsByX.set(cell.x_index, cell);
          if (!representativeMeta) {
            representativeMeta = pickRepresentativeMeta(cell);
          }
        }

        const readyRow: CachedRow = {
          status: "ready",
          yIndex,
          yValue: representativeMeta?.y_value ?? null,
          representativeMeta,
          cellsByX,
        };
        rowCacheRef.current.set(yIndex, readyRow);
        globalRowCache.set(
          makeGlobalCacheKey(
            runDir,
            rid,
            viewAccess
              ? showNsfw
                ? "auth_nsfw"
                : "auth_sfw"
              : "public",
            yIndex,
          ),
          readyRow,
        );
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
        runningCountRef.current -= 1;
        flushPendingRef.current();
      }
    },
    [releaseId, runDir, showNsfw, viewAccess],
  );

  const requestRow = useCallback(
    async (yIndex: number) => {
      if (!Number.isFinite(yIndex) || yIndex < 0 || !releaseId) return;
      if (rowCacheRef.current.has(yIndex)) return;
      if (rowRequestsRef.current.has(yIndex)) return;
      if (pendingYIndexesRef.current.has(yIndex)) return;

      pendingYIndexesRef.current.add(yIndex);
      flushPendingRef.current();
    },
    [releaseId],
  );

  useEffect(() => {
    flushPendingRef.current = () => {
      while (
        runningCountRef.current < MAX_CONCURRENT &&
        pendingYIndexesRef.current.size > 0
      ) {
        const iterator = pendingYIndexesRef.current.values();
        const next = iterator.next();
        if (next.done) break;
        const yIndex = next.value;
        pendingYIndexesRef.current.delete(yIndex);
        runningCountRef.current += 1;
        void doFetchRow(yIndex);
      }
    };
  });

  useEffect(() => {
    for (const controller of rowRequestsRef.current.values()) {
      controller.abort();
    }
    rowRequestsRef.current.clear();
    pendingYIndexesRef.current.clear();
    runningCountRef.current = 0;
  }, []);

  useEffect(() => {
    const requests = rowRequestsRef.current;
    const pending = pendingYIndexesRef.current;
    return () => {
      for (const controller of requests.values()) {
        controller.abort();
      }
      requests.clear();
      pending.clear();
      runningCountRef.current = 0;
    };
  }, []);

  return { rowCacheRef, rowCacheVersion, requestRow } as const;
}
