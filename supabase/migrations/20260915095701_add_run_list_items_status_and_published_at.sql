-- 预发布核心：首页目录新增评测状态、已产出格数与最近发布时间。
-- 历史行按已完结回填：status = 'complete'、generated_cells = total_cells、published_at = created_at。
alter table public.run_list_items
  add column if not exists status text,
  add column if not exists generated_cells integer,
  add column if not exists published_at timestamptz;

update public.run_list_items
  set status = 'complete'
  where status is null;

update public.run_list_items
  set generated_cells = total_cells
  where generated_cells is null;

update public.run_list_items
  set published_at = created_at
  where published_at is null;

alter table public.run_list_items
  alter column status set default 'complete',
  alter column status set not null,
  alter column generated_cells set default 0,
  alter column generated_cells set not null,
  alter column published_at set default now(),
  alter column published_at set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'run_list_items_status_check'
      and conrelid = 'public.run_list_items'::regclass
  ) then
    alter table public.run_list_items
      add constraint run_list_items_status_check
      check (status in ('in_progress', 'complete'));
  end if;
end
$$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'run_list_items_generated_cells_check'
      and conrelid = 'public.run_list_items'::regclass
  ) then
    alter table public.run_list_items
      add constraint run_list_items_generated_cells_check
      check (generated_cells >= 0);
  end if;
end
$$;

create index if not exists run_list_items_published_at_desc_idx
  on public.run_list_items(published_at desc);
