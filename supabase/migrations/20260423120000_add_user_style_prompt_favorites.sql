create table if not exists public.user_style_prompt_favorites (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  prompt_key text not null,
  prompt_text text not null,
  source_run_dir text,
  source_y_index integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_used_at timestamptz,
  constraint user_style_prompt_favorites_prompt_key_check check (
    char_length(prompt_key) = 64
  ),
  constraint user_style_prompt_favorites_prompt_text_check check (
    char_length(btrim(prompt_text)) > 0 and char_length(prompt_text) <= 4000
  ),
  constraint user_style_prompt_favorites_source_y_index_check check (
    source_y_index is null or source_y_index >= 0
  ),
  constraint user_style_prompt_favorites_user_prompt_key_key unique (
    user_id,
    prompt_key
  )
);

create index if not exists user_style_prompt_favorites_user_created_idx
  on public.user_style_prompt_favorites(user_id, created_at desc);

create index if not exists user_style_prompt_favorites_user_last_used_idx
  on public.user_style_prompt_favorites(user_id, last_used_at desc nulls last);

alter table public.user_style_prompt_favorites enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_style_prompt_favorites' and policyname = 'authenticated_select_own_user_style_prompt_favorites'
  ) then
    create policy authenticated_select_own_user_style_prompt_favorites
      on public.user_style_prompt_favorites
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
    where schemaname = 'public' and tablename = 'user_style_prompt_favorites' and policyname = 'authenticated_insert_own_user_style_prompt_favorites'
  ) then
    create policy authenticated_insert_own_user_style_prompt_favorites
      on public.user_style_prompt_favorites
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
    where schemaname = 'public' and tablename = 'user_style_prompt_favorites' and policyname = 'authenticated_update_own_user_style_prompt_favorites'
  ) then
    create policy authenticated_update_own_user_style_prompt_favorites
      on public.user_style_prompt_favorites
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
    where schemaname = 'public' and tablename = 'user_style_prompt_favorites' and policyname = 'authenticated_delete_own_user_style_prompt_favorites'
  ) then
    create policy authenticated_delete_own_user_style_prompt_favorites
      on public.user_style_prompt_favorites
      for delete
      to authenticated
      using ((select auth.uid()) = user_id);
  end if;
end
$$;

grant select, insert, update, delete on table public.user_style_prompt_favorites to authenticated;
grant select, insert, update, delete on table public.user_style_prompt_favorites to service_role;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_style_prompt_favorites' and policyname = 'service_role_write_user_style_prompt_favorites'
  ) then
    create policy service_role_write_user_style_prompt_favorites
      on public.user_style_prompt_favorites
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end
$$;
