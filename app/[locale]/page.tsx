import { getTranslations, setRequestLocale } from "next-intl/server";
import { hasLocale } from "next-intl";
import { notFound } from "next/navigation";

import { routing } from "@/i18n/routing";
import { listRunSummaries } from "@/lib/run-list";
import { buildSeoMetadata } from "@/lib/metadata-utils";
import HomePageClient from "../home-page-client";

// ISR: 每 60 秒重新验证页面缓存，大幅降低 SSR 的 CPU 消耗
export const revalidate = 60;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadata.home" });
  const title = t("title");
  const description = t("description");
  return buildSeoMetadata({ locale, path: "/", title, description });
}

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const models = await listRunSummaries();
  return <HomePageClient models={models} />;
}
