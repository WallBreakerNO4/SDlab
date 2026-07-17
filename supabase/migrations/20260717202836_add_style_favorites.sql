-- 画师提示词收藏（Style Favorites）：两张新表
-- user_style_favorites：用户收藏（身份 = style_key，跨 run 匹配只比较 style_key）
-- run_style_items：每个 run 的 y_index ↔ style_key 映射（反查收藏在哪些 run 可用）
-- 参考任务文档：tasks/spec-style-favorites.md

create table if not exists public.user_style_favorites (
  user_id uuid not null references auth.users(id) on delete cascade,
  style_key text not null,
  label text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, style_key),
  constraint user_style_favorites_style_key_check check (
    char_length(btrim(style_key)) > 0 and char_length(style_key) <= 200
  ),
  constraint user_style_favorites_label_check check (
    char_length(btrim(label)) > 0 and char_length(label) <= 1000
  )
);

alter table public.user_style_favorites enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_style_favorites' and policyname = 'authenticated_select_own_user_style_favorites'
  ) then
    create policy authenticated_select_own_user_style_favorites
      on public.user_style_favorites
      for select
      to authenticated
      using ((select auth.uid()) = user_id);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_style_favorites' and policyname = 'authenticated_insert_own_user_style_favorites'
  ) then
    create policy authenticated_insert_own_user_style_favorites
      on public.user_style_favorites
      for insert
      to authenticated
      with check ((select auth.uid()) = user_id);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_style_favorites' and policyname = 'authenticated_update_own_user_style_favorites'
  ) then
    create policy authenticated_update_own_user_style_favorites
      on public.user_style_favorites
      for update
      to authenticated
      using ((select auth.uid()) = user_id)
      with check ((select auth.uid()) = user_id);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_style_favorites' and policyname = 'authenticated_delete_own_user_style_favorites'
  ) then
    create policy authenticated_delete_own_user_style_favorites
      on public.user_style_favorites
      for delete
      to authenticated
      using ((select auth.uid()) = user_id);
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_style_favorites' and policyname = 'service_role_write_user_style_favorites'
  ) then
    create policy service_role_write_user_style_favorites
      on public.user_style_favorites
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end
$$;

grant select, insert, update, delete on table public.user_style_favorites to authenticated;
grant select, insert, update, delete on table public.user_style_favorites to service_role;

create table if not exists public.run_style_items (
  run_id uuid not null references public.runs(id) on delete cascade,
  run_dir text not null,
  style_key text not null,
  y_index integer not null,
  label text not null,
  created_at timestamptz not null default now(),
  primary key (run_id, style_key),
  constraint run_style_items_y_index_check check (y_index >= 0),
  constraint run_style_items_style_key_check check (
    char_length(btrim(style_key)) > 0 and char_length(style_key) <= 200
  ),
  constraint run_style_items_label_check check (
    char_length(btrim(label)) > 0 and char_length(label) <= 1000
  )
);

create index if not exists run_style_items_style_key_idx
  on public.run_style_items(style_key);

alter table public.run_style_items enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'run_style_items' and policyname = 'anon_select_all_run_style_items'
  ) then
    create policy anon_select_all_run_style_items
      on public.run_style_items
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
    where schemaname = 'public' and tablename = 'run_style_items' and policyname = 'authenticated_select_all_run_style_items'
  ) then
    create policy authenticated_select_all_run_style_items
      on public.run_style_items
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
    where schemaname = 'public' and tablename = 'run_style_items' and policyname = 'service_role_write_run_style_items'
  ) then
    create policy service_role_write_run_style_items
      on public.run_style_items
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end
$$;

grant select on table public.run_style_items to anon, authenticated;
grant select, insert, update, delete on table public.run_style_items to service_role;
