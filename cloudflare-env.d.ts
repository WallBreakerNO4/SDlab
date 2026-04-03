/**
 * Cloudflare Workers 绑定类型声明
 *
 */
declare global {
  interface CloudflareEnv {
    // --- R2 存储桶绑定（wrangler.jsonc r2_buckets 配置） ---
    R2_PUBLIC_BUCKET: R2Bucket;

    // --- Supabase 客户端公开（wrangler.jsonc vars） ---
    NEXT_PUBLIC_SUPABASE_URL: string;
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: string;

    // --- R2 公开链接 base URL（wrangler.jsonc vars） ---
    R2_PUBLIC_BASE_URL: string;

    R2_ENDPOINT?: string;
    R2_PRIVATE_BUCKET?: string;
    R2_ACCESS_KEY_ID?: string;
    R2_SECRET_ACCESS_KEY?: string;
    R2_SIGNED_URL_TTL_SECONDS?: string;
  }
}

export {};
