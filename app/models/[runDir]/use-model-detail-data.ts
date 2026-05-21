"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  publicObjectUrl,
  privateObjectProxyUrl,
} from "@/lib/r2-url";

import type { RunGridIndexData } from "@/components/comfyui/virtual-grid";

import {
  isCurrentRunView,
  isModelDetailResponse,
  isRunGridIndexData,
  isRunViewAccess,
  type CurrentRunView,
  type LoadState,
  type ModelDetailResponse,
  type RunViewAccess,
} from "./model-detail-types";

type UseModelDetailDataOptions = {
  runDir: string;
  showNsfw: boolean;
  currentUserId: string | null;
};

const ACCESS_REFRESH_SKEW_MS = 60 * 1000;
const ACCESS_REFRESH_MIN_DELAY_MS = 5 * 1000;
const SHORT_ACCESS_REFRESH_SKEW_MS = 5 * 1000;

function getAccessRefreshDelayMs(expiresAtSeconds: number): number {
  const timeUntilExpiryMs = expiresAtSeconds * 1000 - Date.now();
  if (!Number.isFinite(timeUntilExpiryMs) || timeUntilExpiryMs <= 0) {
    return ACCESS_REFRESH_MIN_DELAY_MS;
  }

  const skewMs =
    timeUntilExpiryMs > ACCESS_REFRESH_SKEW_MS
      ? ACCESS_REFRESH_SKEW_MS
      : SHORT_ACCESS_REFRESH_SKEW_MS;
  return Math.max(ACCESS_REFRESH_MIN_DELAY_MS, timeUntilExpiryMs - skewMs);
}

async function fetchRunViewAccess(
  runDir: string,
  signal?: AbortSignal,
): Promise<RunViewAccess> {
  const response = await fetch(
    `/api/comfyui/run/${encodeURIComponent(runDir)}/access`,
    {
      signal,
      cache: "no-store",
    },
  );
  if (!response.ok) {
    throw new Error("error");
  }

  const raw: unknown = await response.json();
  if (!isRunViewAccess(raw)) {
    throw new Error("error");
  }

  return raw;
}

export function useModelDetailData({
  runDir,
  showNsfw,
  currentUserId,
}: UseModelDetailDataOptions) {
  const [detailLoadState, setDetailLoadState] = useState<LoadState>("loading");
  const [gridLoadState, setGridLoadState] = useState<LoadState>("loading");
  const [detailData, setDetailData] = useState<ModelDetailResponse | null>(null);
  const [gridData, setGridData] = useState<RunGridIndexData | null>(null);
  const [currentView, setCurrentView] = useState<CurrentRunView | null>(null);
  const [viewAccess, setViewAccess] = useState<RunViewAccess | null>(null);
  const refreshPromiseRef = useRef<Promise<RunViewAccess | null> | null>(null);

  const refreshViewAccess = useCallback(async () => {
    if (!currentUserId) {
      setViewAccess(null);
      return null;
    }

    if (refreshPromiseRef.current) {
      return refreshPromiseRef.current;
    }

    const refreshPromise = fetchRunViewAccess(runDir)
      .then((access) => {
        setViewAccess(access);
        return access;
      })
      .finally(() => {
        refreshPromiseRef.current = null;
      });

    refreshPromiseRef.current = refreshPromise;
    return refreshPromise;
  }, [currentUserId, runDir]);

  useEffect(() => {
    const abortController = new AbortController();

    async function fetchAll() {
      setDetailLoadState("loading");
      setGridLoadState("loading");
      setViewAccess(null);

      const currentPromise = fetch(
        publicObjectUrl(`runs/${runDir}/view/current.json`),
        {
          signal: abortController.signal,
          cache: "no-store",
        },
      );

      const accessPromise = currentUserId
        ? fetchRunViewAccess(runDir, abortController.signal)
        : null;

      // 防止 cleanup 时 abort 导致的 rejection 成为 unhandled rejection
      if (accessPromise) void accessPromise.catch(() => {});

      const currentResponse = await currentPromise;

      if (currentResponse.status === 404) {
        throw new Error("not-found");
      }
      if (!currentResponse.ok) {
        throw new Error("error");
      }

      const currentRaw: unknown = await currentResponse.json();
      if (!isCurrentRunView(currentRaw)) {
        throw new Error("error");
      }
      if (abortController.signal.aborted) return;
      setCurrentView(currentRaw);

      let access: RunViewAccess | null = null;
      if (accessPromise) {
        access = await accessPromise;
        if (!abortController.signal.aborted) {
          setViewAccess(access);
        }
      }

      const wantsPrivateNsfw = showNsfw && access?.viewer_variant === "auth_nsfw";
      const bootstrapUrl = wantsPrivateNsfw
        ? privateObjectProxyUrl(
            `runs/${runDir}/view/v2/${currentRaw.release_id}/bootstrap.nsfw.json`,
            access!.grant,
          )
        : publicObjectUrl(currentRaw.bootstrap_sfw_key);

      const bootstrapCache = wantsPrivateNsfw
        ? ("no-store" as const)
        : ("force-cache" as const);

      const bootstrapResponse = await fetch(bootstrapUrl, {
        signal: abortController.signal,
        cache: bootstrapCache,
      });

      if (bootstrapResponse.status === 404) {
        throw new Error("not-found");
      }
      if (!bootstrapResponse.ok) {
        throw new Error("error");
      }

      const bootstrapRaw: unknown = await bootstrapResponse.json();
      if (
        !isModelDetailResponse(bootstrapRaw) ||
        !isRunGridIndexData(bootstrapRaw)
      ) {
        throw new Error("error");
      }

      // Production bootstrap JSON uses camelCase `yLabels` (ModelDetailResponse).
      // Grid components expect snake_case `y_labels` (RunGridIndexData).
      // Normalize here so downstream consumers don't need dual-field handling.
      if (
        !bootstrapRaw.y_labels &&
        Array.isArray((bootstrapRaw as Record<string, unknown>).yLabels)
      ) {
        (bootstrapRaw as { y_labels?: string[] }).y_labels = (
          bootstrapRaw as Record<string, unknown>
        ).yLabels as string[];
      }

      if (abortController.signal.aborted) return;
      setDetailData(bootstrapRaw);
      setGridData(bootstrapRaw);
      setDetailLoadState("ready");
      setGridLoadState("ready");
    }

    void fetchAll().catch((err: unknown) => {
      if (abortController.signal.aborted) return;
      console.error("[model-detail] Failed to load run view", err);
      const state =
        err instanceof Error && err.message === "not-found"
          ? "not-found"
          : "error";
      setDetailLoadState(state);
      setGridLoadState(state);
    });

    return () => {
      abortController.abort("cleanup");
    };
  }, [currentUserId, runDir, showNsfw]);

  useEffect(() => {
    if (!currentUserId || !viewAccess) {
      return;
    }

    const delayMs = getAccessRefreshDelayMs(viewAccess.expires_at);
    const timeoutId = window.setTimeout(() => {
      void refreshViewAccess().catch((error: unknown) => {
        console.error("[model-detail] Failed to refresh run view access", error);
      });
    }, delayMs);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [currentUserId, refreshViewAccess, viewAccess]);

  return {
    detailLoadState,
    gridLoadState,
    detailData,
    gridData,
    currentView,
    viewAccess,
    refreshViewAccess,
  };
}
