import { privateObjectProxyUrl } from "@/lib/r2-url";
import { normalizeRowPayload } from "@/components/comfyui/virtual-grid-utils";
import type { RowPayload } from "@/components/comfyui/virtual-grid-types";
import type {
  ComparisonCatalogPage,
  ComparisonSlice,
} from "@/lib/style-comparison";
import {
  isStyleComparisonResponse,
  isStyleComparisonSliceResponse,
} from "@/lib/style-comparison";

export async function fetchComparisonCatalog(
  cursor: string | null,
  limit = 40,
  signal?: AbortSignal,
): Promise<ComparisonCatalogPage> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  const response = await fetch(`/api/viewer/style-comparison?${query}`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error("comparison-catalog-failed");
  const raw: unknown = await response.json();
  if (!isStyleComparisonResponse(raw)) {
    throw new Error("comparison-catalog-invalid");
  }
  return raw;
}

export async function fetchComparisonSlice(
  styleKeys: string[],
  runDirs: string[],
  signal?: AbortSignal,
): Promise<ComparisonSlice> {
  const response = await fetch("/api/viewer/style-comparison/slice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    signal,
    body: JSON.stringify({
      style_keys: styleKeys.slice(0, 40),
      run_dirs: runDirs.slice(0, 12),
    }),
  });
  if (!response.ok) throw new Error("comparison-slice-failed");
  const raw: unknown = await response.json();
  if (!isStyleComparisonSliceResponse(raw)) {
    throw new Error("comparison-slice-invalid");
  }
  return raw;
}

const rowCache = new Map<string, RowPayload>();

export type ComparisonRowRequest = {
  key: string;
  runDir: string;
  releaseId: string;
  viewerVariant: string;
  grant: string;
  yIndex: number;
};

export async function mapWithConcurrency<T>(
  values: T[],
  worker: (value: T) => Promise<void>,
  concurrency = 4,
): Promise<void> {
  const queue = [...values];
  const runners = Array.from(
    { length: Math.max(1, Math.min(concurrency, values.length)) },
    async () => {
      while (queue.length) {
        const value = queue.shift();
        if (value !== undefined) await worker(value);
      }
    },
  );
  await Promise.all(runners);
}

export async function fetchComparisonRow(
  runDir: string,
  releaseId: string,
  viewerVariant: string,
  grant: string,
  yIndex: number,
  signal?: AbortSignal,
): Promise<RowPayload | null> {
  const cacheKey = `${runDir}/${releaseId}/${viewerVariant}/${yIndex}`;
  const cached = rowCache.get(cacheKey);
  if (cached) return cached;
  const url = privateObjectProxyUrl(
    `runs/${runDir}/view/v2/${releaseId}/rows/${viewerVariant}/${yIndex}.json`,
    grant,
  );
  const response = await fetch(url, { cache: "force-cache", signal });
  if (!response.ok) return null;
  const payload = normalizeRowPayload(await response.json(), yIndex);
  if (payload) rowCache.set(cacheKey, payload);
  return payload;
}

export async function fetchComparisonRows(
  requests: ComparisonRowRequest[],
  signal?: AbortSignal,
  concurrency = 6,
): Promise<Array<{ key: string; row: RowPayload | null }>> {
  if (requests.length === 0) return [];
  const results: Array<{ key: string; row: RowPayload | null }> = [];
  let cursor = 0;
  const workerCount = Math.min(Math.max(1, concurrency), requests.length);
  const worker = async () => {
    while (!signal?.aborted) {
      const index = cursor++;
      if (index >= requests.length) return;
      const request = requests[index];
      const row = await fetchComparisonRow(
        request.runDir,
        request.releaseId,
        request.viewerVariant,
        request.grant,
        request.yIndex,
        signal,
      );
      if (signal?.aborted) return;
      results.push({ key: request.key, row });
    }
  };
  await Promise.all(Array.from({ length: workerCount }, worker));
  return results;
}

export function clearComparisonRowCache() {
  rowCache.clear();
}
