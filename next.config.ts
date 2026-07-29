import path from "node:path";
import { fileURLToPath } from "node:url";

import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";
import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

// 仅在 next dev 时启动 Miniflare，提供 R2/KV 等 Cloudflare binding
// build 阶段跳过，避免触发 Wrangler remote proxy（401）
// NODE_ENV 由 next dev / next build 自动设置，比 argv 解析可靠
if (process.env.NODE_ENV === "development") {
  initOpenNextCloudflareForDev();
}

const repoRoot = path.dirname(fileURLToPath(import.meta.url));
const markdownLoaderPath = path.join(
  repoRoot,
  "loaders",
  "markdown-source-loader.cjs",
);
const markdownPattern = /(^|[\\/])data[\\/](?:.*-page(?:\.en)?|model-guides[\\/].+)\.md$/i;

const nextConfig: NextConfig = {
  // 显式关闭浏览器端 source map，避免源码泄露与扫描流量
  productionBrowserSourceMaps: false,
  env: {
    NEXT_PUBLIC_R2_PUBLIC_BASE_URL: process.env.R2_PUBLIC_BASE_URL,
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "images.unsplash.com",
      },
    ],
  },
  webpack(config) {
    config.module.rules.push({
      test: markdownPattern,
      use: [markdownLoaderPath],
    });

    return config;
  },
  turbopack: {
    rules: {
      "*.md": {
        condition: {
          path: markdownPattern,
        },
        loaders: [markdownLoaderPath],
        as: "*.js",
      },
    },
  },
};

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

export default withNextIntl(nextConfig);
