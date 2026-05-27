import { isValidRunDir } from "@/lib/comfyui-types";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";
import { hasLocale } from "next-intl";

import { routing } from "@/i18n/routing";
import { ModelDetailClientPage } from "@/app/models/[runDir]/model-detail-client";

function readRunDir(value: string | string[] | undefined): string {
  if (!value) {
    return "";
  }

  return Array.isArray(value) ? value[0] ?? "" : value;
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
