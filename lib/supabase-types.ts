export type JsonPrimitive = string | number | boolean | null

export type JsonValue = JsonPrimitive | JsonObject | JsonValue[]

export type JsonObject = { [key: string]: JsonValue }

export type ImageCategory = 'normal' | 'advance' | 'nsfw'

export type ImageVariantName =
  | 'original_png'
  | 'display_webp'
  | 'display_avif'
  | 'thumb_webp'
  | 'thumb_avif'

export type R2Bucket = 'public' | 'private'

export interface SupabaseRunRow {
  run_id?: string | null
  run_dir: string
  created_at: string
  x_columns?: JsonValue[] | null
  y_indexes?: number[] | null
  x_count?: number | null
  y_count?: number | null
  total_cells?: number | null
  run_json: JsonValue
}

export interface SupabaseImageRow {
  x_index: number
  y_index: number
  batch_index: number
  category: ImageCategory
  blurhash: string | null
  seed?: number | string | null
  prompt_hash?: string | null
  positive_prompt?: string | null
  y_value?: string | null
  metadata: JsonObject
}

export interface SupabaseImageVariantRow {
  variant: ImageVariantName
  bucket: R2Bucket
  r2_key: string
  content_type: string
}
