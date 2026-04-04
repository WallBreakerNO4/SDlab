export type JsonPrimitive = string | number | boolean | null;

export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];

export type JsonObject = { [key: string]: JsonValue };

export type ImageCategory = "normal" | "advance" | "nsfw";

export type R2Bucket = "public" | "private";

export interface SupabaseRunRow {
  id?: string | null;
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

export interface SupabaseRunListItemRow {
  run_id?: string | null;
  run_dir: string;
  created_at: string;
  x_count: number | null;
  y_count: number | null;
  total_cells: number | null;
  model_name?: string | null;
  model_description_zh?: string | null;
  model_description_en?: string | null;
  model_homepage?: string | null;
  model_huggingface?: string | null;
  model_civitai?: string | null;
  cover?: JsonValue | null;
  homepage_cards?: JsonValue | null;
}

export interface SupabaseRunGridCellRow {
  x_index: number | null;
  y_index: number | null;
  representative_batch_index: number | null;
  category: ImageCategory | null;
  width: number | null;
  height: number | null;
  blurhash: string | null;
}

export interface SupabaseRunGridItemRow {
  run_dir: string;
  x_index: number;
  y_index: number;
  batch_index: number;
  category: ImageCategory;
  width: number | null;
  height: number | null;
  blurhash: string | null;
  seed?: string | null;
  prompt_hash?: string | null;
  positive_prompt?: string | null;
  y_value?: string | null;
  thumb_webp_bucket?: R2Bucket | null;
  thumb_webp_r2_key?: string | null;
  thumb_avif_bucket?: R2Bucket | null;
  thumb_avif_r2_key?: string | null;
  display_webp_bucket?: R2Bucket | null;
  display_webp_r2_key?: string | null;
  display_avif_bucket?: R2Bucket | null;
  display_avif_r2_key?: string | null;
}
