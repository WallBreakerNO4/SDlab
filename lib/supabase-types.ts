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
  run_dir: string
  created_at: string
  run_json: JsonValue
}

export interface SupabaseImageRow {
  x_index: number
  y_index: number
  batch_index: number
  category: ImageCategory
  blurhash: string | null
  metadata: JsonObject
}

export interface SupabaseImageVariantRow {
  variant: ImageVariantName
  bucket: R2Bucket
  r2_key: string
  content_type: string
}
