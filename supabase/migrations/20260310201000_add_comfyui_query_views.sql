create or replace view public.comfyui_grid_cells
with (security_invoker = true) as
select
  r.run_dir,
  r.x_columns,
  r.y_indexes,
  r.x_count,
  r.y_count,
  i.x_index,
  i.y_index,
  i.batch_index,
  i.category,
  i.width,
  i.height,
  i.blurhash
from public.runs as r
left join public.images as i on i.run_id = r.id;

create or replace view public.comfyui_row_items
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
  max(case when v.variant = 'original_png' then v.bucket end) as original_bucket,
  max(case when v.variant = 'original_png' then v.r2_key end) as original_r2_key,
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

grant select on public.comfyui_grid_cells to anon;
grant select on public.comfyui_grid_cells to authenticated;
grant select on public.comfyui_grid_cells to service_role;

grant select on public.comfyui_row_items to anon;
grant select on public.comfyui_row_items to authenticated;
grant select on public.comfyui_row_items to service_role;
