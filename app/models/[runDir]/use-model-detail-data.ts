"use client";

import { useEffect, useState } from "react";

import type { RunGridIndexData } from "@/components/comfyui/virtual-grid";

import {
  isModelDetailResponse,
  isRunGridIndexData,
  type LoadState,
  type ModelDetailResponse,
} from "./model-detail-types";

export function useModelDetailData(runDir: string, showNsfw: boolean) {
  const [detailLoadState, setDetailLoadState] = useState<LoadState>("loading");
  const [gridLoadState, setGridLoadState] = useState<LoadState>("loading");
  const [detailData, setDetailData] = useState<ModelDetailResponse | null>(null);
  const [gridData, setGridData] = useState<RunGridIndexData | null>(null);

  useEffect(() => {
    const abortController = new AbortController();
    const preferenceRequestKey = showNsfw ? "nsfw-on" : "nsfw-off";

    async function fetchAll() {
      setDetailLoadState("loading");
      setGridLoadState("loading");

      const detailPromise = fetch(
        `/api/comfyui/run/${encodeURIComponent(runDir)}?viewer_nsfw=${preferenceRequestKey}`,
        {
          cache: "no-store",
          signal: abortController.signal,
        },
      ).then(async (res) => {
        if (res.status === 404) throw new Error("not-found");
        if (!res.ok) throw new Error("error");
        const data = await res.json();
        if (!isModelDetailResponse(data)) throw new Error("error");
        return data;
      });

      const gridPromise = fetch(
        `/api/comfyui/run/${encodeURIComponent(runDir)}/grid?viewer_nsfw=${preferenceRequestKey}`,
        {
          cache: "no-store",
          signal: abortController.signal,
        },
      ).then(async (res) => {
        if (res.status === 404) throw new Error("not-found");
        if (!res.ok) throw new Error("error");
        const data = await res.json();
        if (!isRunGridIndexData(data)) throw new Error("error");
        return data;
      });

      detailPromise
        .then((data) => {
          if (abortController.signal.aborted) return;
          setDetailData(data);
          setDetailLoadState("ready");
        })
        .catch((err) => {
          if (abortController.signal.aborted) return;
          if (err.name === "AbortError") return;
          setDetailLoadState(err.message === "not-found" ? "not-found" : "error");
        });

      gridPromise
        .then((data) => {
          if (abortController.signal.aborted) return;
          setGridData(data);
          setGridLoadState("ready");
        })
        .catch((err) => {
          if (abortController.signal.aborted) return;
          if (err.name === "AbortError") return;
          setGridLoadState(err.message === "not-found" ? "not-found" : "error");
        });
    }

    void fetchAll();

    return () => {
      abortController.abort();
    };
  }, [runDir, showNsfw]);

  return {
    detailLoadState,
    gridLoadState,
    detailData,
    gridData,
  };
}
