import type { MetadataRoute } from "next";

import { isValidRunDir } from "@/lib/comfyui-types";
import { listRunSummaries } from "@/lib/run-list";

const SITE_ORIGIN = "https://sdlab.wall-breaker-no4.xyz";

function toLastModified(value: string): Date | undefined {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? undefined : date;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  let runs: Awaited<ReturnType<typeof listRunSummaries>> = [];

  try {
    runs = await listRunSummaries();
  } catch {
    runs = [];
  }

  const latestRunModified = runs[0]
    ? toLastModified(runs[0].created_at)
    : undefined;

  const entries: MetadataRoute.Sitemap = [
    {
      url: SITE_ORIGIN,
      lastModified: latestRunModified,
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${SITE_ORIGIN}/info`,
      changeFrequency: "monthly",
      priority: 0.6,
    },
  ];

  const seenRunDirs = new Set<string>();
  for (const run of runs) {
    if (!isValidRunDir(run.run_dir) || seenRunDirs.has(run.run_dir)) {
      continue;
    }

    seenRunDirs.add(run.run_dir);
    entries.push({
      url: `${SITE_ORIGIN}/runs/${encodeURIComponent(run.run_dir)}`,
      lastModified: toLastModified(run.created_at),
      changeFrequency: "weekly",
      priority: 0.8,
    });
  }

  return entries;
}
