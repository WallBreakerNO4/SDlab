import type { MetadataRoute } from "next";

import { isValidRunDir } from "@/lib/comfyui-types";
import { listRunSummaries } from "@/lib/run-list";

const SITE_ORIGIN = "https://sdlab.wall-breaker-no4.xyz";

function toLastModified(value: string): Date | undefined {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? undefined : date;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  let models: Awaited<ReturnType<typeof listRunSummaries>> = [];

  try {
    models = await listRunSummaries();
  } catch {
    models = [];
  }

  const latestModelModified = models[0]
    ? toLastModified(models[0].created_at)
    : undefined;

  const entries: MetadataRoute.Sitemap = [
    {
      url: SITE_ORIGIN,
      lastModified: latestModelModified,
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${SITE_ORIGIN}/info`,
      changeFrequency: "monthly",
      priority: 0.6,
    },
  ];

  const seenModelRunDirs = new Set<string>();
  for (const model of models) {
    if (
      !isValidRunDir(model.run_dir) ||
      seenModelRunDirs.has(model.run_dir)
    ) {
      continue;
    }

    seenModelRunDirs.add(model.run_dir);
    entries.push({
      url: `${SITE_ORIGIN}/models/${encodeURIComponent(model.run_dir)}`,
      lastModified: toLastModified(model.created_at),
      changeFrequency: "weekly",
      priority: 0.8,
    });
  }

  return entries;
}
