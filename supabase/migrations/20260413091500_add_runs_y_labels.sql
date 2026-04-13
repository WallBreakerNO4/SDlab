alter table public.runs
  add column if not exists y_labels text[] not null default '{}'::text[];

update public.runs as r
set y_labels = coalesce(
  (
    select array_agg(coalesce(labels.y_value, '') order by ord.ordinality)
    from unnest(coalesce(r.y_indexes, '{}'::integer[])) with ordinality as ord(y_index, ordinality)
    left join lateral (
      select i.y_value
      from public.run_grid_items as i
      where
        i.run_id = r.id
        and i.y_index = ord.y_index
        and i.y_value is not null
        and btrim(i.y_value) <> ''
      order by i.x_index asc, i.batch_index asc
      limit 1
    ) as labels on true
  ),
  '{}'::text[]
);
