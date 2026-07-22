import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { hasLocale } from "next-intl";

import { routing } from "@/i18n/routing";
import { buildSeoMetadata } from "@/lib/metadata-utils";
import FavoritesPage from "@/components/favorites/favorites-page";

interface FavoritesPageProps {
  params: Promise<{ locale: string }>;
}

export async function generateMetadata({
  params,
}: FavoritesPageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "styleFavorites" });

  // 收藏页是用户私有页：在统一 SEO 标签之上关闭搜索引擎索引
  return {
    ...buildSeoMetadata({
      locale,
      path: "/favorites",
      title: t("title"),
      description: t("description"),
    }),
    robots: { index: false },
  };
}

export default async function FavoritesPageShell({
  params,
}: FavoritesPageProps) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);

  return <FavoritesPage />;
}
