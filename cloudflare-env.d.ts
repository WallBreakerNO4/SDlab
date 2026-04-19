/**
 * Cloudflare Workers 绑定类型声明
 *
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
    NEXT_PUBLIC_R2_PUBLIC_BASE_URL: string;

    RUN_MEDIA_GRANT_SECRET?: string;
  }
}

export {};
