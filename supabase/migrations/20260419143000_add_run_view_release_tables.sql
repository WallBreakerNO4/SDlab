create table if not exists public.run_view_index (
  run_id uuid primary key references public.runs(id) on delete cascade,
  run_dir text not null unique references public.runs(run_dir) on delete cascade,
  schema_version integer not null,
  release_id text not null,
  current_r2_key text not null,
  bootstrap_sfw_r2_key text not null,
  bootstrap_nsfw_r2_key text not null,
  media_access_version integer not null default 1,
  updated_at timestamptz not null default now()
);

create index if not exists run_view_index_run_dir_idx
  on public.run_view_index (run_dir);

create table if not exists public.run_prompts (
  run_id uuid not null references public.runs(id) on delete cascade,
  run_dir text not null references public.runs(run_dir) on delete cascade,
  prompt_id integer not null,
  prompt_hash text,
  positive_prompt text not null,
  created_at timestamptz not null default now(),
  primary key (run_id, prompt_id),
  unique (run_id, prompt_hash, positive_prompt)
);

create index if not exists run_prompts_run_dir_prompt_id_idx
  on public.run_prompts (run_dir, prompt_id);

alter table public.run_view_index enable row level security;
alter table public.run_prompts enable row level security;

drop policy if exists "run_view_index_select_public" on public.run_view_index;
create policy "run_view_index_select_public"
  on public.run_view_index
  for select
  to anon, authenticated
  using (true);

drop policy if exists "run_prompts_service_role_all" on public.run_prompts;
create policy "run_prompts_service_role_all"
  on public.run_prompts
  for all
  to service_role
  using (true)
  with check (true);
