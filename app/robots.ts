import type { MetadataRoute } from "next";

const SITE_ORIGIN = "https://sdlab.wall-breaker-no4.xyz";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/api/", "/auth/"],
    },
    sitemap: `${SITE_ORIGIN}/sitemap.xml`,
  };
}
