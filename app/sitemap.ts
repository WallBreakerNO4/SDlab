import type { MetadataRoute } from "next";

import { isValidRunDir } from "@/lib/comfyui-types";
import { modelGuides } from "@/lib/generated/model-guides";
import { buildGuideSitemapEntries } from "@/lib/model-guides-sitemap";
import { listRunSummaries } from "@/lib/run-list";
import { SITE_ORIGIN } from "@/lib/site-origin";
import { routing } from "@/i18n/routing";

export const dynamic = "force-static";

function toLastModified(value: string): Date | undefined {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? undefined : date;
}

/** 为给定路径生成两个 locale 的 hreflang 映射 */
function makeLanguages(path: string): Record<string, string> {
  const languages: Record<string, string> = {};
  for (const loc of routing.locales) {
    languages[loc] = `${SITE_ORIGIN}/${loc}${path}`;
  }
  return languages;
}

/** 生成一个页面在两个 locale 下的 sitemap 条目（含 hreflang） */
function makeLocaleEntries(params: {
  path: string;
  lastModified?: Date;
  changeFrequency?: MetadataRoute.Sitemap[number]["changeFrequency"];
  priority?: number;
}): MetadataRoute.Sitemap {
  const { path, lastModified, changeFrequency, priority } = params;
  const languages = makeLanguages(path);

  return routing.locales.map((locale) => ({
    url: languages[locale],
    lastModified,
    changeFrequency,
    priority,
    alternates: { languages },
  }));
}

export { buildGuideSitemapEntries } from "@/lib/model-guides-sitemap";

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

  const entries: MetadataRoute.Sitemap = [];

  // 首页 — daily, priority 1
  entries.push(
    ...makeLocaleEntries({
      path: "/",
      lastModified: latestModelModified,
      changeFrequency: "daily",
      priority: 1,
    }),
  );

  // 信息页 — monthly, priority 0.6
  entries.push(
    ...makeLocaleEntries({
      path: "/info",
      lastModified: latestModelModified,
      changeFrequency: "monthly",
      priority: 0.6,
    }),
  );

  // Prompt 法典 — monthly, priority 0.7
  entries.push(
    ...makeLocaleEntries({
      path: "/prompts",
      lastModified: latestModelModified,
      changeFrequency: "monthly",
      priority: 0.7,
    }),
  );

  // 隐私政策页 — monthly, priority 0.5
  entries.push(
    ...makeLocaleEntries({
      path: "/privacy-policy",
      lastModified: latestModelModified,
      changeFrequency: "monthly",
      priority: 0.5,
    }),
  );

  // 模型详情页 — weekly, priority 0.8
  const seenModelRunDirs = new Set<string>();
  for (const model of models) {
    if (
      !isValidRunDir(model.run_dir) ||
      seenModelRunDirs.has(model.run_dir)
    ) {
      continue;
    }

    seenModelRunDirs.add(model.run_dir);
    entries.push(
      ...makeLocaleEntries({
        path: `/models/${encodeURIComponent(model.run_dir)}`,
        lastModified: toLastModified(model.created_at),
        changeFrequency: "weekly",
        priority: 0.8,
      }),
    );
  }

  entries.push(...buildGuideSitemapEntries(modelGuides));

  return entries;
}
