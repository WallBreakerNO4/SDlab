import path from "node:path";
import { fileURLToPath } from "node:url";

import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";
import type { NextConfig } from "next";

// 本地 next dev 时启动 Miniflare，提供 R2/KV 等 Cloudflare binding
initOpenNextCloudflareForDev();

const repoRoot = path.dirname(fileURLToPath(import.meta.url));
const markdownLoaderPath = path.join(
  repoRoot,
  "app",
  "info",
  "markdown-source-loader.cjs",
);
const contentPageMarkdownPattern = /(^|[\\/])data[\\/].*-page\.md$/i;

const nextConfig: NextConfig = {
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

export default nextConfig;
