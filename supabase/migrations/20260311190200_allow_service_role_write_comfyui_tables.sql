grant usage on schema public to service_role;

grant select, insert, update on table public.runs to service_role;
grant select, insert, update on table public.images to service_role;
grant select, insert, update on table public.image_variants to service_role;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public' and tablename = 'runs' and policyname = 'service_role_write_runs'
  ) then
    create policy service_role_write_runs
      on public.runs
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
    where schemaname = 'public' and tablename = 'images' and policyname = 'service_role_write_images'
  ) then
    create policy service_role_write_images
      on public.images
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
    where schemaname = 'public' and tablename = 'image_variants' and policyname = 'service_role_write_image_variants'
  ) then
    create policy service_role_write_image_variants
      on public.image_variants
      for all
      to service_role
      using (true)
      with check (true);
  end if;
end
$$;
