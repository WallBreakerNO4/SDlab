import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { getTranslations, setRequestLocale } from "next-intl/server"
import { hasLocale } from "next-intl"

import { routing } from "@/i18n/routing"
import { buildSeoMetadata } from "@/lib/metadata-utils"
import FavoriteComparisonDetail from "@/components/favorites/favorite-comparison-detail"

type Props = { params: Promise<{ locale: string; styleKey: string }> }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params
  const t = await getTranslations({ locale, namespace: "styleFavorites" })
  return { ...buildSeoMetadata({ locale, path: "/favorites", title: t("comparisonDetailTitle"), description: t("comparisonDescription") }), robots: { index: false } }
}

export default async function FavoriteComparisonDetailPage({ params }: Props) {
  const { locale, styleKey } = await params
  if (!hasLocale(routing.locales, locale)) notFound()
  setRequestLocale(locale)
  return <FavoriteComparisonDetail styleKey={decodeURIComponent(styleKey)} />
}
