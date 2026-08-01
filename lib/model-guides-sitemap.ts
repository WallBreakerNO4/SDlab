import { SITE_ORIGIN } from "@/lib/site-origin";
import type { MetadataRoute } from "next";

/** 只为实际存在的指南语言生成 sitemap 条目和 hreflang。 */
export function buildGuideSitemapEntries(
  guides: ReadonlyArray<{
    modelKey: string;
    locale: string;
  }>,
): MetadataRoute.Sitemap {
  const byModel = new Map<string, Map<string, string>>();
  for (const guide of guides) {
    const locales = byModel.get(guide.modelKey) ?? new Map<string, string>();
    locales.set(
      guide.locale,
      `${SITE_ORIGIN}/${guide.locale}/guides/${encodeURIComponent(guide.modelKey)}`,
    );
    byModel.set(guide.modelKey, locales);
  }

  const entries: MetadataRoute.Sitemap = [];
  for (const locales of byModel.values()) {
    const languages = Object.fromEntries(locales);
    for (const url of locales.values()) {
      entries.push({
        url,
        changeFrequency: "monthly",
        priority: 0.6,
        alternates: { languages },
      });
    }
  }
  return entries;
}
