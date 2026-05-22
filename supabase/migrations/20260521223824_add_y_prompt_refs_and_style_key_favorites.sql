create table if not exists public.run_y_prompt_refs (
  run_id uuid not null references public.runs(id) on delete cascade,
  run_dir text not null references public.runs(run_dir) on delete cascade,
  y_index integer not null,
  style_key text not null,
  collection_id text not null,
  item_index integer not null,
  label text not null,
  source_y_path text,
  source_y_sha256 text,
  created_at timestamptz not null default now(),
  primary key (run_id, y_index),
  constraint run_y_prompt_refs_y_index_check check (y_index >= 0),
  constraint run_y_prompt_refs_style_key_check check (
    char_length(btrim(style_key)) > 0 and char_length(style_key) <= 512
  ),
  constraint run_y_prompt_refs_collection_id_check check (
    char_length(btrim(collection_id)) > 0 and char_length(collection_id) <= 200
  ),
  constraint run_y_prompt_refs_item_index_check check (item_index >= 0),
  constraint run_y_prompt_refs_label_check check (
    char_length(btrim(label)) > 0 and char_length(label) <= 4000
  ),
  constraint run_y_prompt_refs_source_y_sha256_check check (
    source_y_sha256 is null or char_length(source_y_sha256) = 64
  )
);

create index if not exists run_y_prompt_refs_run_dir_y_index_idx
  on public.run_y_prompt_refs(run_dir, y_index);

create index if not exists run_y_prompt_refs_style_key_idx
  on public.run_y_prompt_refs(style_key);

alter table public.run_y_prompt_refs enable row level security;

drop policy if exists "run_y_prompt_refs_select_public" on public.run_y_prompt_refs;
create policy "run_y_prompt_refs_select_public"
  on public.run_y_prompt_refs
  for select
  to anon, authenticated
  using (true);

drop policy if exists "run_y_prompt_refs_service_role_all" on public.run_y_prompt_refs;
create policy "run_y_prompt_refs_service_role_all"
  on public.run_y_prompt_refs
  for all
  to service_role
  using (true)
  with check (true);

grant select on table public.run_y_prompt_refs to anon, authenticated;
grant select, insert, update, delete on table public.run_y_prompt_refs to service_role;

delete from public.user_style_prompt_favorites;

alter table public.user_style_prompt_favorites
  drop constraint if exists user_style_prompt_favorites_user_prompt_key_key,
  drop constraint if exists user_style_prompt_favorites_prompt_key_check,
  drop constraint if exists user_style_prompt_favorites_prompt_text_check;

alter table public.user_style_prompt_favorites
  drop column if exists prompt_key,
  drop column if exists prompt_text,
  add column if not exists style_key text,
  add column if not exists label text;

alter table public.user_style_prompt_favorites
  alter column style_key set not null,
  alter column label set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'user_style_prompt_favorites_style_key_check'
  ) then
    alter table public.user_style_prompt_favorites
      add constraint user_style_prompt_favorites_style_key_check check (
        char_length(btrim(style_key)) > 0 and char_length(style_key) <= 512
      );
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'user_style_prompt_favorites_label_check'
  ) then
    alter table public.user_style_prompt_favorites
      add constraint user_style_prompt_favorites_label_check check (
        char_length(btrim(label)) > 0 and char_length(label) <= 4000
      );
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'user_style_prompt_favorites_user_style_key_key'
  ) then
    alter table public.user_style_prompt_favorites
      add constraint user_style_prompt_favorites_user_style_key_key unique (
        user_id,
        style_key
      );
  end if;
end
$$;

create index if not exists user_style_prompt_favorites_user_style_key_idx
  on public.user_style_prompt_favorites(user_id, style_key);
