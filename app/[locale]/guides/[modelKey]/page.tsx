import type { Metadata } from "next";
import ReactMarkdown, { type Components } from "react-markdown";
import { hasLocale } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { notFound, redirect } from "next/navigation";

import { routing } from "@/i18n/routing";
import { buildSeoMetadata } from "@/lib/metadata-utils";
import { SITE_ORIGIN } from "@/lib/site-origin";
import {
  buildGuideIndex,
  getModelGuide,
  resolveGuideLocale,
  type ModelGuideLocale,
} from "@/lib/model-guides";
import { modelGuides } from "@/lib/generated/model-guides";

const guideIndex = buildGuideIndex(modelGuides);
const guideMarkdownComponents: Components = { h1: "h2" };

function readModelKey(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) return "";
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

export function generateStaticParams() {
  return modelGuides.map((guide) => ({
    locale: guide.locale,
    modelKey: guide.modelKey,
  }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; modelKey: string | string[] }>;
}): Promise<Metadata> {
  const { locale, modelKey: rawModelKey } = await params;
  const modelKey = readModelKey(rawModelKey);
  if (!hasLocale(routing.locales, locale)) return {};
  const resolvedLocale = resolveGuideLocale(
    guideIndex,
    modelKey,
    locale as ModelGuideLocale,
  );
  if (!resolvedLocale) return {};
  const guide = getModelGuide(guideIndex, modelKey, resolvedLocale);
  if (!guide) return {};
  const languages: Record<string, string> = {};
  const entries = guideIndex[modelKey];
  for (const availableLocale of routing.locales) {
    if (entries?.[availableLocale]) {
      languages[availableLocale] =
        `${SITE_ORIGIN}/${availableLocale}/guides/${encodeURIComponent(modelKey)}`;
    }
  }
  const metadata = buildSeoMetadata({
    locale: guide.locale,
    path: `/guides/${encodeURIComponent(modelKey)}`,
    title: guide.title,
    description: guide.title,
    ogType: "article",
  });
  return { ...metadata, alternates: { ...metadata.alternates, languages } };
}

export default async function ModelGuidePage({
  params,
}: {
  params: Promise<{ locale: string; modelKey: string | string[] }>;
}) {
  const { locale, modelKey: rawModelKey } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const modelKey = readModelKey(rawModelKey);
  const resolvedLocale = resolveGuideLocale(
    guideIndex,
    modelKey,
    locale as ModelGuideLocale,
  );
  if (!resolvedLocale) notFound();
  if (resolvedLocale !== locale)
    redirect(`/${resolvedLocale}/guides/${encodeURIComponent(modelKey)}`);
  const guide = guideIndex[modelKey]?.[resolvedLocale];
  if (!guide) notFound();
  return (
    <main className="h-full w-full overflow-y-auto">
      <div className="container mx-auto px-4 py-12 md:py-24">
        <article className="prose-custom mx-auto max-w-3xl">
          <h1>{guide.title}</h1>
          <ReactMarkdown components={guideMarkdownComponents}>
            {guide.content}
          </ReactMarkdown>
        </article>
      </div>
    </main>
  );
}
