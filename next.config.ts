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
const contentPageMarkdownPattern = /(^|[\\/])data[\\/].*-page(?:\.en)?\.md$/i;

const nextConfig: NextConfig = {
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
      test: contentPageMarkdownPattern,
      use: [markdownLoaderPath],
    });

    return config;
  },
  turbopack: {
    rules: {
      "*.md": {
        condition: {
          path: contentPageMarkdownPattern,
        },
        loaders: [markdownLoaderPath],
        as: "*.js",
      },
    },
  },
};

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

export default withNextIntl(nextConfig);
