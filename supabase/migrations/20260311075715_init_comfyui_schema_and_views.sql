create extension if not exists pgcrypto;

create table if not exists public.runs (
  id uuid primary key default gen_random_uuid(),
  run_dir text not null unique,
  run_id text not null,
  created_at timestamptz not null default now(),
  run_json jsonb not null,
  x_columns jsonb not null default '[]'::jsonb,
  y_indexes integer[] not null default '{}'::integer[],
  x_count integer not null default 0,
  y_count integer not null default 0,
  total_cells integer not null default 0
);

create table if not exists public.images (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.runs(id) on delete cascade,
  x_index integer not null,
  y_index integer not null,
  batch_index integer not null default 0,
  category text not null,
  width integer,
  height integer,
  blurhash text,
  seed bigint,
  prompt_hash text,
  positive_prompt text,
  y_value text,
  metadata jsonb not null,
  created_at timestamptz not null default now(),
  constraint images_run_id_x_y_batch_key unique (run_id, x_index, y_index, batch_index),
  constraint images_category_check check (category in ('normal', 'advance', 'nsfw'))
);

create table if not exists public.image_variants (
  id uuid primary key default gen_random_uuid(),
  image_id uuid not null references public.images(id) on delete cascade,
  variant text not null,
  bucket text not null,
  r2_key text not null,
  content_type text not null,
  byte_size bigint,
  sha256 text,
  width integer,
  height integer,
  webp_quality integer,
  avif_quality integer,
  avif_speed integer,
  created_at timestamptz not null default now(),
  constraint image_variants_image_id_variant_key unique (image_id, variant),
  constraint image_variants_variant_check check (
    variant in ('original_png', 'display_webp', 'display_avif', 'thumb_webp', 'thumb_avif')
  ),
  constraint image_variants_bucket_check check (bucket in ('public', 'private'))
);

create index if not exists runs_created_at_desc_idx on public.runs(created_at desc);
create index if not exists images_run_id_idx on public.images(run_id);
create index if not exists images_category_idx on public.images(category);
create index if not exists images_run_id_y_index_x_index_batch_index_idx
  on public.images(run_id, y_index, x_index, batch_index);
create index if not exists image_variants_bucket_idx on public.image_variants(bucket);
create index if not exists image_variants_image_id_idx on public.image_variants(image_id);

alter table public.runs enable row level security;
alter table public.images enable row level security;
alter table public.image_variants enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'images' and policyname = 'anon_select_all_images'
  ) then
    create policy anon_select_all_images
      on public.images
      for select
      to anon
      using (true);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'images' and policyname = 'authenticated_select_all_images'
  ) then
    create policy authenticated_select_all_images
      on public.images
      for select
      to authenticated
      using (true);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'image_variants' and policyname = 'anon_select_public_variants'
  ) then
    create policy anon_select_public_variants
      on public.image_variants
      for select
      to anon
      using (bucket = 'public');
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'image_variants' and policyname = 'authenticated_select_all_image_variants'
  ) then
    create policy authenticated_select_all_image_variants
      on public.image_variants
      for select
      to authenticated
      using (true);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'runs' and policyname = 'anon_select_all_runs'
  ) then
    create policy anon_select_all_runs
      on public.runs
      for select
      to anon
      using (true);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'runs' and policyname = 'authenticated_select_all_runs'
  ) then
    create policy authenticated_select_all_runs
      on public.runs
      for select
      to authenticated
      using (true);
  end if;
end
$$;

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
