create extension if not exists pgcrypto;

create table if not exists public.runs (
  id uuid primary key default gen_random_uuid(),
  run_dir text not null unique,
  created_at timestamptz not null default now(),
  run_json jsonb not null
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

create index if not exists images_run_id_idx on public.images(run_id);
create index if not exists images_category_idx on public.images(category);
create index if not exists image_variants_bucket_idx on public.image_variants(bucket);

alter table public.runs enable row level security;
alter table public.images enable row level security;
alter table public.image_variants enable row level security;

create policy anon_select_all_images
  on public.images
  for select
  to anon
  using (true);

create policy authenticated_select_all_images
  on public.images
  for select
  to authenticated
  using (true);

create policy anon_select_public_variants
  on public.image_variants
  for select
  to anon
  using (bucket = 'public');

create policy authenticated_select_all_image_variants
  on public.image_variants
  for select
  to authenticated
  using (true);

create policy anon_select_all_runs
  on public.runs
  for select
  to anon
  using (true);

create policy authenticated_select_all_runs
  on public.runs
  for select
  to authenticated
  using (true);
