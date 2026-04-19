create extension if not exists pgcrypto with schema extensions;

alter table public.run_grid_items
  add column if not exists thumb_webp_cache_key text,
  add column if not exists thumb_avif_cache_key text,
  add column if not exists display_webp_cache_key text,
  add column if not exists display_avif_cache_key text;

update public.run_grid_items
set
  thumb_webp_cache_key = case
    when thumb_webp_bucket is not null and thumb_webp_r2_key is not null then
      encode(
        extensions.digest(
          format('v1:%s:%s', thumb_webp_bucket, thumb_webp_r2_key),
          'sha256'
        ),
        'hex'
      )
    else null
  end,
  thumb_avif_cache_key = case
    when thumb_avif_bucket is not null and thumb_avif_r2_key is not null then
      encode(
        extensions.digest(
          format('v1:%s:%s', thumb_avif_bucket, thumb_avif_r2_key),
          'sha256'
        ),
        'hex'
      )
    else null
  end,
  display_webp_cache_key = case
    when display_webp_bucket is not null and display_webp_r2_key is not null then
      encode(
        extensions.digest(
          format('v1:%s:%s', display_webp_bucket, display_webp_r2_key),
          'sha256'
        ),
        'hex'
      )
    else null
  end,
  display_avif_cache_key = case
    when display_avif_bucket is not null and display_avif_r2_key is not null then
      encode(
        extensions.digest(
          format('v1:%s:%s', display_avif_bucket, display_avif_r2_key),
          'sha256'
        ),
        'hex'
      )
    else null
  end;

alter table public.run_grid_items
  drop constraint if exists run_grid_items_thumb_webp_cache_key_check,
  drop constraint if exists run_grid_items_thumb_avif_cache_key_check,
  drop constraint if exists run_grid_items_display_webp_cache_key_check,
  drop constraint if exists run_grid_items_display_avif_cache_key_check;

alter table public.run_grid_items
  add constraint run_grid_items_thumb_webp_cache_key_check check (
    (thumb_webp_bucket is null and thumb_webp_r2_key is null and thumb_webp_cache_key is null)
    or
    (thumb_webp_bucket is not null and thumb_webp_r2_key is not null and thumb_webp_cache_key is not null)
  ),
  add constraint run_grid_items_thumb_avif_cache_key_check check (
    (thumb_avif_bucket is null and thumb_avif_r2_key is null and thumb_avif_cache_key is null)
    or
    (thumb_avif_bucket is not null and thumb_avif_r2_key is not null and thumb_avif_cache_key is not null)
  ),
  add constraint run_grid_items_display_webp_cache_key_check check (
    (display_webp_bucket is null and display_webp_r2_key is null and display_webp_cache_key is null)
    or
    (display_webp_bucket is not null and display_webp_r2_key is not null and display_webp_cache_key is not null)
  ),
  add constraint run_grid_items_display_avif_cache_key_check check (
    (display_avif_bucket is null and display_avif_r2_key is null and display_avif_cache_key is null)
    or
    (display_avif_bucket is not null and display_avif_r2_key is not null and display_avif_cache_key is not null)
  );
