export type JsonPrimitive = string | number | boolean | null;

export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];

export type JsonObject = { [key: string]: JsonValue };

export type ImageCategory = "normal" | "advance" | "nsfw";
export type RunAssetRole = "cover" | "homepage_card";

export type ImageVariantName =
  | "display_webp"
  | "display_avif"
  | "thumb_webp"
  | "thumb_avif";

export type R2Bucket = "public" | "private";

export interface SupabaseRunRow {
  run_id?: string | null;
  run_dir: string;
  created_at: string;
  x_columns?: JsonValue[] | null;
  y_indexes?: number[] | null;
  x_count?: number | null;
  y_count?: number | null;
  total_cells?: number | null;
  model_name?: string | null;
  model_description_zh?: string | null;
  model_description_en?: string | null;
  model_homepage?: string | null;
  model_huggingface?: string | null;
  model_civitai?: string | null;
  workflow_download_r2_key?: string | null;
  workflow_download_sha256?: string | null;
  run_json?: JsonValue | null;
}

export interface SupabaseImageRow {
  x_index: number;
  y_index: number;
  batch_index: number;
  category: ImageCategory;
  blurhash: string | null;
  seed?: string | null;
  prompt_hash?: string | null;
  positive_prompt?: string | null;
  y_value?: string | null;
  metadata: JsonObject;
}

export interface SupabaseImageVariantRow {
  variant: ImageVariantName;
  bucket: R2Bucket;
  r2_key: string;
  content_type: string;
}

export interface SupabaseRunAssetRow {
  asset_role: RunAssetRole;
  asset_index: number;
  source_path: string;
  source_sha256: string;
  blurhash: string | null;
  blurhash_width?: number | null;
  blurhash_height?: number | null;
  metadata: JsonObject;
}

export interface SupabaseRunAssetVariantRow {
  variant: ImageVariantName;
  bucket: R2Bucket;
  r2_key: string;
  content_type: string;
}
