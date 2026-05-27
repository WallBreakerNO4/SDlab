import type { Metadata } from "next";
import ReactMarkdown from "react-markdown";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { hasLocale } from "next-intl";
import { notFound } from "next/navigation";

import { routing } from "@/i18n/routing";
import privacyZh from "@/data/privacy-policy-page.md";
import privacyEn from "@/data/privacy-policy-page.en.md";

export const dynamic = "force-static";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadata.privacy" });
  return {
    title: t("title"),
    description: t("description"),
  };
}

export default async function PrivacyPolicyPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const content = locale === "en" ? privacyEn : privacyZh;

  return (
    <main className="h-full w-full overflow-y-auto">
      <div className="container mx-auto px-4 py-12 md:py-24">
        <div className="prose-custom max-w-3xl mx-auto">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </main>
  );
}
