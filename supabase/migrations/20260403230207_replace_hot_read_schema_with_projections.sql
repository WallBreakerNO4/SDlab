alter table public.runs
  alter column run_json set default '{}'::jsonb;

create table if not exists public.run_snapshots (
  run_id uuid primary key references public.runs(id) on delete cascade,
  run_dir text not null unique,
  run_json jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.run_list_items (
  run_id uuid primary key references public.runs(id) on delete cascade,
  run_dir text not null unique,
  created_at timestamptz not null,
  x_count integer not null default 0,
  y_count integer not null default 0,
  total_cells integer not null default 0,
  model_name text,
  model_description_zh text,
  model_description_en text,
  model_homepage text,
  model_huggingface text,
  model_civitai text,
  cover jsonb,
  homepage_cards jsonb not null default '[]'::jsonb,
  constraint run_list_items_cover_shape_check check (
    cover is null or jsonb_typeof(cover) = 'object'
  ),
  constraint run_list_items_homepage_cards_shape_check check (
    jsonb_typeof(homepage_cards) = 'array'
  )
);

create table if not exists public.run_grid_items (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.runs(id) on delete cascade,
  run_dir text not null,
  x_index integer not null,
  y_index integer not null,
  batch_index integer not null default 0,
  category text not null,
  width integer,
  height integer,
  blurhash text,
  seed text,
  prompt_hash text,
  positive_prompt text,
  y_value text,
  thumb_webp_bucket text,
  thumb_webp_r2_key text,
  thumb_avif_bucket text,
  thumb_avif_r2_key text,
  display_webp_bucket text,
  display_webp_r2_key text,
  display_avif_bucket text,
  display_avif_r2_key text,
  created_at timestamptz not null default now(),
  constraint run_grid_items_run_id_x_y_batch_key unique (run_id, x_index, y_index, batch_index),
  constraint run_grid_items_category_check check (category in ('normal', 'advance', 'nsfw')),
  constraint run_grid_items_thumb_webp_bucket_check check (
    thumb_webp_bucket is null or thumb_webp_bucket in ('public', 'private')
  ),
  constraint run_grid_items_thumb_avif_bucket_check check (
    thumb_avif_bucket is null or thumb_avif_bucket in ('public', 'private')
  ),
  constraint run_grid_items_display_webp_bucket_check check (
    display_webp_bucket is null or display_webp_bucket in ('public', 'private')
  ),
  constraint run_grid_items_display_avif_bucket_check check (
    display_avif_bucket is null or display_avif_bucket in ('public', 'private')
  )
);

create table if not exists public.run_grid_item_snapshots (
  run_id uuid not null references public.runs(id) on delete cascade,
  run_dir text not null,
  x_index integer not null,
  y_index integer not null,
  batch_index integer not null default 0,
  metadata jsonb not null,
  created_at timestamptz not null default now(),
  primary key (run_id, x_index, y_index, batch_index)
);

create table if not exists public.run_grid_cells (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.runs(id) on delete cascade,
  run_dir text not null,
  x_index integer not null,
  y_index integer not null,
  representative_batch_index integer not null default 0,
  category text not null,
  width integer,
  height integer,
  blurhash text,
  created_at timestamptz not null default now(),
  constraint run_grid_cells_run_id_x_y_key unique (run_id, x_index, y_index),
  constraint run_grid_cells_category_check check (category in ('normal', 'advance', 'nsfw'))
);

create index if not exists run_snapshots_run_dir_idx
  on public.run_snapshots(run_dir);
create index if not exists run_list_items_created_at_desc_idx
  on public.run_list_items(created_at desc);
create index if not exists run_grid_items_run_dir_y_x_batch_idx
  on public.run_grid_items(run_dir, y_index, x_index, batch_index);
create index if not exists run_grid_items_run_id_y_x_batch_idx
  on public.run_grid_items(run_id, y_index, x_index, batch_index);
create index if not exists run_grid_item_snapshots_run_dir_y_x_batch_idx
  on public.run_grid_item_snapshots(run_dir, y_index, x_index, batch_index);
create index if not exists run_grid_cells_run_dir_y_x_idx
  on public.run_grid_cells(run_dir, y_index, x_index);
create index if not exists run_grid_cells_run_id_y_x_idx
  on public.run_grid_cells(run_id, y_index, x_index);

alter table public.run_snapshots enable row level security;
alter table public.run_list_items enable row level security;
alter table public.run_grid_items enable row level security;
alter table public.run_grid_item_snapshots enable row level security;
alter table public.run_grid_cells enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'run_list_items' and policyname = 'anon_select_all_run_list_items'
  ) then
    create policy anon_select_all_run_list_items
      on public.run_list_items
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
    where schemaname = 'public' and tablename = 'run_list_items' and policyname = 'authenticated_select_all_run_list_items'
  ) then
    create policy authenticated_select_all_run_list_items
      on public.run_list_items
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
    where schemaname = 'public' and tablename = 'run_grid_items' and policyname = 'anon_select_all_run_grid_items'
  ) then
    create policy anon_select_all_run_grid_items
      on public.run_grid_items
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
    where schemaname = 'public' and tablename = 'run_grid_items' and policyname = 'authenticated_select_all_run_grid_items'
  ) then
    create policy authenticated_select_all_run_grid_items
      on public.run_grid_items
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
    where schemaname = 'public' and tablename = 'run_grid_cells' and policyname = 'anon_select_all_run_grid_cells'
  ) then
    create policy anon_select_all_run_grid_cells
      on public.run_grid_cells
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
    where schemaname = 'public' and tablename = 'run_grid_cells' and policyname = 'authenticated_select_all_run_grid_cells'
  ) then
    create policy authenticated_select_all_run_grid_cells
      on public.run_grid_cells
      for select
      to authenticated
      using (true);
  end if;
end
$$;

grant select, insert, update on table public.run_snapshots to service_role;
grant select, insert, update on table public.run_list_items to service_role;
grant select, insert, update on table public.run_grid_items to service_role;
grant select, insert, update on table public.run_grid_item_snapshots to service_role;
grant select, insert, update on table public.run_grid_cells to service_role;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'run_snapshots' and policyname = 'service_role_write_run_snapshots'
  ) then
    create policy service_role_write_run_snapshots
      on public.run_snapshots
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
    where schemaname = 'public' and tablename = 'run_list_items' and policyname = 'service_role_write_run_list_items'
  ) then
    create policy service_role_write_run_list_items
      on public.run_list_items
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
    where schemaname = 'public' and tablename = 'run_grid_items' and policyname = 'service_role_write_run_grid_items'
  ) then
    create policy service_role_write_run_grid_items
      on public.run_grid_items
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
    where schemaname = 'public' and tablename = 'run_grid_item_snapshots' and policyname = 'service_role_write_run_grid_item_snapshots'
  ) then
    create policy service_role_write_run_grid_item_snapshots
      on public.run_grid_item_snapshots
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
    where schemaname = 'public' and tablename = 'run_grid_cells' and policyname = 'service_role_write_run_grid_cells'
  ) then
    create policy service_role_write_run_grid_cells
      on public.run_grid_cells
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end
$$;
