create table if not exists public.run_assets (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.runs(id) on delete cascade,
  asset_role text not null,
  asset_index integer not null default 0,
  source_path text not null,
  source_sha256 text not null,
  width integer,
  height integer,
  blurhash text,
  blurhash_width integer,
  blurhash_height integer,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint run_assets_run_id_asset_role_asset_index_key unique (run_id, asset_role, asset_index),
  constraint run_assets_asset_role_check check (asset_role in ('cover', 'homepage_thumb'))
);

create table if not exists public.run_asset_variants (
  id uuid primary key default gen_random_uuid(),
  run_asset_id uuid not null references public.run_assets(id) on delete cascade,
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
  constraint run_asset_variants_run_asset_id_variant_key unique (run_asset_id, variant),
  constraint run_asset_variants_variant_check check (
    variant in ('display_webp', 'display_avif', 'thumb_webp', 'thumb_avif')
  ),
  constraint run_asset_variants_bucket_check check (bucket in ('public', 'private'))
);

create index if not exists run_assets_run_id_idx on public.run_assets(run_id);
create index if not exists run_assets_run_id_asset_role_asset_index_idx
  on public.run_assets(run_id, asset_role, asset_index);
create index if not exists run_assets_asset_role_idx on public.run_assets(asset_role);
create index if not exists run_asset_variants_bucket_idx on public.run_asset_variants(bucket);
create index if not exists run_asset_variants_run_asset_id_idx on public.run_asset_variants(run_asset_id);

alter table public.run_assets enable row level security;
alter table public.run_asset_variants enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'run_assets' and policyname = 'anon_select_all_run_assets'
  ) then
    create policy anon_select_all_run_assets
      on public.run_assets
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
    where schemaname = 'public' and tablename = 'run_assets' and policyname = 'authenticated_select_all_run_assets'
  ) then
    create policy authenticated_select_all_run_assets
      on public.run_assets
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
    where schemaname = 'public' and tablename = 'run_asset_variants' and policyname = 'anon_select_public_run_asset_variants'
  ) then
    create policy anon_select_public_run_asset_variants
      on public.run_asset_variants
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
    where schemaname = 'public' and tablename = 'run_asset_variants' and policyname = 'authenticated_select_all_run_asset_variants'
  ) then
    create policy authenticated_select_all_run_asset_variants
      on public.run_asset_variants
      for select
      to authenticated
      using (true);
  end if;
end
$$;

grant select, insert, update on table public.run_assets to service_role;
grant select, insert, update on table public.run_asset_variants to service_role;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'run_assets' and policyname = 'service_role_write_run_assets'
  ) then
    create policy service_role_write_run_assets
      on public.run_assets
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'run_asset_variants' and policyname = 'service_role_write_run_asset_variants'
  ) then
    create policy service_role_write_run_asset_variants
      on public.run_asset_variants
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end
$$;
