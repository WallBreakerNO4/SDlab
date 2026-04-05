create table if not exists public.user_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  show_nsfw boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.user_preferences enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_preferences' and policyname = 'authenticated_select_own_user_preferences'
  ) then
    create policy authenticated_select_own_user_preferences
      on public.user_preferences
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
    where schemaname = 'public' and tablename = 'user_preferences' and policyname = 'authenticated_insert_own_user_preferences'
  ) then
    create policy authenticated_insert_own_user_preferences
      on public.user_preferences
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
    where schemaname = 'public' and tablename = 'user_preferences' and policyname = 'authenticated_update_own_user_preferences'
  ) then
    create policy authenticated_update_own_user_preferences
      on public.user_preferences
      for update
      to authenticated
      using ((select auth.uid()) = user_id)
      with check ((select auth.uid()) = user_id);
  end if;
end
$$;

grant select, insert, update on table public.user_preferences to authenticated;
grant select, insert, update on table public.user_preferences to service_role;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'user_preferences' and policyname = 'service_role_write_user_preferences'
  ) then
    create policy service_role_write_user_preferences
      on public.user_preferences
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end
$$;
