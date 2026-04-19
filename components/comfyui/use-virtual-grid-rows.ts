"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { RunViewAccess } from "@/app/models/[runDir]/model-detail-types";
import {
  privateObjectProxyUrl,
  publicObjectUrl,
} from "@/lib/r2-url";

import type { CachedRow, RowCell, RowMeta } from "./virtual-grid-types";
import { normalizeRowPayload } from "./virtual-grid-utils";

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
  const [rowCacheVersion, setRowCacheVersion] = useState(0);

  const requestRow = useCallback(
    async (yIndex: number) => {
      if (!Number.isFinite(yIndex) || yIndex < 0 || !releaseId) return;
      if (rowCacheRef.current.has(yIndex)) return;
      if (rowRequestsRef.current.has(yIndex)) return;

      const controller = new AbortController();
      rowRequestsRef.current.set(yIndex, controller);

      try {
        const response = await fetch(
          buildRowManifestUrl({
            runDir,
            yIndex,
            releaseId,
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

        rowCacheRef.current.set(yIndex, {
          status: "ready",
          yIndex,
          yValue: representativeMeta?.y_value ?? null,
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
    [releaseId, runDir, showNsfw, viewAccess],
  );

  useEffect(() => {
    rowRequestsRef.current.forEach((controller) => controller.abort());
    rowRequestsRef.current.clear();
  }, []);

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
