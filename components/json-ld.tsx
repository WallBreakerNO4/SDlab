"use client";

/**
 * JSON-LD 结构化数据组件集合。
 *
 * 这些组件是客户端组件（"use client"），仅在浏览器中注入
 * `<script type="application/ld+json">` 标签，不消耗 Cloudflare Worker CPU 时间。
 */

type JsonLdWebsiteProps = {
  origin: string;
  /** 站点简短描述 */
  description: string;
};

/** WebSite schema — 帮助搜索引擎理解站点结构 */
export function JsonLdWebsite({ origin, description }: JsonLdWebsiteProps) {
  const payload = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "SD Style Lab",
    url: origin,
    description,
    inLanguage: ["zh", "en"],
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }}
    />
  );
}

type JsonLdBreadcrumbListProps = {
  items: { name: string; url: string }[];
};

/** BreadcrumbList schema — 帮助搜索引擎理解页面层级关系 */
export function JsonLdBreadcrumbList({ items }: JsonLdBreadcrumbListProps) {
  const payload = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem" as const,
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }}
    />
  );
}
