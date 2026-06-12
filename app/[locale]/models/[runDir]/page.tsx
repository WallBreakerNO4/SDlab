import type { Metadata } from "next";
import { isValidRunDir } from "@/lib/comfyui-types";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { hasLocale } from "next-intl";

import { routing } from "@/i18n/routing";
import { ModelDetailClientPage } from "@/app/models/[runDir]/model-detail-client";
import { getModelMetadata } from "@/lib/model-metadata";
import { buildSeoMetadata } from "@/lib/metadata-utils";

// ISR: 每 120 秒重新验证页面缓存（模型数据变化频率低于首页）
export const revalidate = 120;

function readRunDir(value: string | string[] | undefined): string {
  if (!value) {
    return "";
  }

  return Array.isArray(value) ? value[0] ?? "" : value;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; runDir: string | string[] }>;
}): Promise<Metadata> {
  const resolvedParams = await params;
  const { locale, runDir: rawRunDir } = resolvedParams;
  const runDir = readRunDir(rawRunDir);

  if (!isValidRunDir(runDir)) {
    return {};
  }

  const t = await getTranslations({ locale, namespace: "metadata.modelDetail" });
  const meta = await getModelMetadata(runDir);

  const modelName = meta?.name ?? runDir;
  const title = `${modelName}${t("titleSuffix")}`;

  const localizedDesc =
    locale === "zh" ? meta?.descriptionZh : meta?.descriptionEn;
  const description = localizedDesc ?? t("descriptionFallback");

  return buildSeoMetadata({
    locale,
    path: `/models/${runDir}`,
    title,
    description,
    ogImage: meta?.ogImage ?? undefined,
    ogType: "article",
  });
}

export default async function ModelDetailPage({
  params,
}: {
  params: Promise<{ locale: string; runDir: string | string[] }>;
}) {
  const resolvedParams = await params;
  const { locale, runDir: rawRunDir } = resolvedParams;

  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const runDir = readRunDir(rawRunDir);

  if (!isValidRunDir(runDir)) {
    notFound();
  }

  return <ModelDetailClientPage runDir={runDir} />;
}
