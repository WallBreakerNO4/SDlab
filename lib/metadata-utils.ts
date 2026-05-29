import type { Metadata } from "next";

import { routing } from "@/i18n/routing";
import { SITE_ORIGIN } from "@/lib/site-origin";

type BuildSeoMetadataParams = {
  /** 当前页面 locale */
  locale: string;
  /** 当前页面的无前缀路径，例如 "/"、"/info"、"/models/xxx" */
  path: string;
  title: string;
  description: string;
  /** og:image 完整 URL（可选） */
  ogImage?: string;
  /** og:type，默认为 "website" */
  ogType?: "website" | "article";
};

/**
 * 为给定页面构建 OpenGraph、Twitter Card、canonical 和 hreflang
 * 元数据字段。各页面的 `generateMetadata` 调用本函数即可获得一致的
 * SEO 标签，无需重复手写。
 */
export function buildSeoMetadata(params: BuildSeoMetadataParams): Metadata {
  const {
    locale,
    path,
    title,
    description,
    ogImage,
    ogType = "website",
  } = params;

  const canonicalUrl = `${SITE_ORIGIN}/${locale}${path === "/" ? "" : path}`;

  const ogLocale = locale === "zh" ? "zh_CN" : "en_US";

  const languages: Record<string, string> = {};
  for (const loc of routing.locales) {
    languages[loc] = `${SITE_ORIGIN}/${loc}${path === "/" ? "" : path}`;
  }

  const metadata: Metadata = {
    openGraph: {
      title,
      description,
      url: canonicalUrl,
      siteName: "SD Style Lab",
      locale: ogLocale,
      type: ogType,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
    alternates: {
      canonical: canonicalUrl,
      languages,
    },
  };

  if (ogImage) {
    metadata.openGraph = {
      ...metadata.openGraph,
      images: [{ url: ogImage }],
    };
    metadata.twitter = {
      ...metadata.twitter,
      images: [ogImage],
    } as Metadata["twitter"];
  }

  return metadata;
}
