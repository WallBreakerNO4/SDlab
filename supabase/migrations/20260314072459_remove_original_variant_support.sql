delete from public.image_variants
where variant = 'original_png';

alter table public.image_variants
  drop constraint if exists image_variants_variant_check;

alter table public.image_variants
  add constraint image_variants_variant_check check (
    variant in ('display_webp', 'display_avif', 'thumb_webp', 'thumb_avif')
  );

drop view if exists public.comfyui_row_items;

create view public.comfyui_row_items
with (security_invoker = true) as
select
  r.run_dir,
  i.x_index,
  i.y_index,
  i.batch_index,
  i.category,
  i.width,
  i.height,
  i.blurhash,
  i.seed,
  i.prompt_hash,
  i.positive_prompt,
  i.y_value,
  max(case when v.variant = 'thumb_webp' then v.bucket end) as thumb_webp_bucket,
  max(case when v.variant = 'thumb_webp' then v.r2_key end) as thumb_webp_r2_key,
  max(case when v.variant = 'thumb_avif' then v.bucket end) as thumb_avif_bucket,
  max(case when v.variant = 'thumb_avif' then v.r2_key end) as thumb_avif_r2_key,
  max(case when v.variant = 'display_webp' then v.bucket end) as display_webp_bucket,
  max(case when v.variant = 'display_webp' then v.r2_key end) as display_webp_r2_key,
  max(case when v.variant = 'display_avif' then v.bucket end) as display_avif_bucket,
  max(case when v.variant = 'display_avif' then v.r2_key end) as display_avif_r2_key
from public.runs as r
join public.images as i on i.run_id = r.id
left join public.image_variants as v on v.image_id = i.id
group by
  r.run_dir,
  i.id,
  i.x_index,
  i.y_index,
  i.batch_index,
  i.category,
  i.width,
  i.height,
  i.blurhash,
  i.seed,
  i.prompt_hash,
  i.positive_prompt,
  i.y_value;

grant select on public.comfyui_row_items to anon;
grant select on public.comfyui_row_items to authenticated;
grant select on public.comfyui_row_items to service_role;
