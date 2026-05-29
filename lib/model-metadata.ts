import "server-only";

import { unstable_cache } from "next/cache";
import { createClient } from "@supabase/supabase-js";

import { getPublicEnv } from "@/lib/env/public";
import { publicObjectUrl } from "@/lib/r2-url";

/** 用于 generateMetadata 的模型 SEO 信息 */
export type ModelSeoMetadata = {
  name: string | null;
  descriptionZh: string | null;
  descriptionEn: string | null;
  /** 封面图完整 R2 URL，用于 og:image */
  ogImage: string | null;
};

function getNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * 从 run_list_items 表中按 run_dir 查询单行模型的 SEO 元数据。
 * 只取 name / description / cover 三个轻量字段，避免全表扫描。
 */
async function getModelMetadataUncached(
  runDir: string,
): Promise<ModelSeoMetadata | null> {
  const { supabaseUrl, supabasePublishableKey } = getPublicEnv();

  const supabase = createClient(supabaseUrl, supabasePublishableKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  });

  const { data, error } = await supabase
    .from("run_list_items")
    .select(
      "model_name, model_description_zh, model_description_en, cover",
    )
    .eq("run_dir", runDir)
    .maybeSingle();

  if (error) {
    console.error(
      `[model-metadata] 查询模型元数据失败 run_dir=${runDir}:`,
      error.message,
    );
    return null;
  }

  if (!data) return null;

  const name = getNonEmptyString(data.model_name);

  // 从 cover JSONB 中提取 R2 key → 构建完整 URL
  let ogImage: string | null = null;
  const cover = data.cover as Record<string, unknown> | null;
  if (cover && typeof cover === "object") {
    const displayAvifKey = getNonEmptyString(cover.display_avif_r2_key);
    const displayWebpKey = getNonEmptyString(cover.display_webp_r2_key);
    const thumbAvifKey = getNonEmptyString(cover.thumb_avif_r2_key);
    const thumbWebpKey = getNonEmptyString(cover.thumb_webp_r2_key);

    // 优先级：display > thumb；avif > webp（OG 需要高质量图）
    const bestKey =
      displayAvifKey ?? displayWebpKey ?? thumbAvifKey ?? thumbWebpKey;
    if (bestKey) {
      ogImage = publicObjectUrl(bestKey);
    }
  }

  return {
    name,
    descriptionZh: getNonEmptyString(data.model_description_zh),
    descriptionEn: getNonEmptyString(data.model_description_en),
    ogImage,
  };
}

/**
 * 带缓存的模型元数据查询。
 *
 * 模型详情页几乎不会有变动，因此设置 1 小时（3600 秒）的缓存 TTL。
 * 同时注入了 `model-metadata` 标签，方便后续需要时通过 revalidateTag 手动刷新。
 */
export const getModelMetadata = unstable_cache(
  getModelMetadataUncached,
  ["model-metadata"],
  { revalidate: 3600, tags: ["model-metadata"] },
);
