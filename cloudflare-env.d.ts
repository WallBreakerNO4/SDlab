/**
 * Cloudflare Workers 绑定类型声明
 *
 * 在 Next.js 服务端代码中通过 getCloudflareContext() 访问：
 *   import { getCloudflareContext } from "@opennextjs/cloudflare";
 *   const { env } = getCloudflareContext();
 *   const bucket = env.R2_PRIVATE_BUCKET;
 *
 * 所有变量均在 wrangler.jsonc 的 vars 中配置（无 wrangler secret）。
 */
declare global {
  interface CloudflareEnv {
    // --- R2 存储桶绑定（wrangler.jsonc r2_buckets 配置） ---
    R2_PUBLIC_BUCKET: R2Bucket;
    R2_PRIVATE_BUCKET: R2Bucket;

    // --- Supabase 客户端公开（wrangler.jsonc vars） ---
    NEXT_PUBLIC_SUPABASE_URL: string;
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: string;

    // --- R2 公开链接 base URL（wrangler.jsonc vars） ---
    R2_PUBLIC_BASE_URL: string;
  }
}

export {};
