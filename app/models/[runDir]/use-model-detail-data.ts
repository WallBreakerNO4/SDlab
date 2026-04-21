"use client";

import { useEffect, useState } from "react";

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

  useEffect(() => {
    const abortController = new AbortController();

    async function fetchAll() {
      setDetailLoadState("loading");
      setGridLoadState("loading");
      setViewAccess(null);

      const currentResponse = await fetch(
        publicObjectUrl(`runs/${runDir}/view/current.json`),
        {
          signal: abortController.signal,
          cache: "no-store",
        },
      );

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
      if (currentUserId) {
        const accessResponse = await fetch(
          `/api/comfyui/run/${encodeURIComponent(runDir)}/access`,
          {
            signal: abortController.signal,
            cache: "no-store",
          },
        );
        if (!accessResponse.ok) {
          throw new Error("error");
        }
        const accessRaw: unknown = await accessResponse.json();
        if (!isRunViewAccess(accessRaw)) {
          throw new Error("error");
        }
        access = accessRaw;
        if (!abortController.signal.aborted) {
          setViewAccess(accessRaw);
        }
      }

      const wantsPrivateNsfw = showNsfw && access?.viewer_variant === "auth_nsfw";
      const bootstrapUrl = wantsPrivateNsfw
        ? privateObjectProxyUrl(
            `runs/${runDir}/view/v2/${currentRaw.release_id}/bootstrap.nsfw.json`,
            access!.grant,
          )
        : publicObjectUrl(currentRaw.bootstrap_sfw_key);

      const bootstrapResponse = await fetch(bootstrapUrl, {
        signal: abortController.signal,
        cache: "no-store",
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
      abortController.abort();
    };
  }, [currentUserId, runDir, showNsfw]);

  return {
    detailLoadState,
    gridLoadState,
    detailData,
    gridData,
    currentView,
    viewAccess,
  };
}
