create or replace function public.get_style_comparison_slice(
  p_style_keys text[],
  p_run_dirs text[]
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
as $function$
declare
  viewer_id uuid := (select auth.uid());
begin
  if viewer_id is null then
    raise exception using
      errcode = '42501',
      message = 'authentication required';
  end if;

  if coalesce(cardinality(p_style_keys), 0) not between 1 and 40
    or coalesce(cardinality(p_run_dirs), 0) not between 1 and 12
    or array_position(p_style_keys, null) is not null
    or array_position(p_run_dirs, null) is not null
    or exists (
      select 1
      from unnest(p_style_keys) as style_key
      where char_length(style_key) > 200
        or style_key !~ '^[^:]+:[0-9]+$'
    )
    or exists (
      select 1
      from unnest(p_run_dirs) as run_dir
      where char_length(run_dir) > 200
        or run_dir !~ '^[a-z0-9]+(-[a-z0-9]+)*$'
    )
  then
    raise exception using
      errcode = '22023',
      message = 'invalid style comparison slice input';
  end if;

  return (
    with requested_styles as (
      select distinct style_key
      from unnest(p_style_keys) as style_key
    ),
    requested_runs as (
      select distinct run_dir
      from unnest(p_run_dirs) as run_dir
    ),
    owned_styles as (
      select favorites.style_key
      from public.user_style_favorites as favorites
      inner join requested_styles using (style_key)
      where favorites.user_id = viewer_id
    ),
    placement_rows as (
      select distinct on (items.style_key, items.run_dir)
        items.style_key,
        items.run_dir,
        items.y_index
      from public.run_style_items as items
      inner join owned_styles using (style_key)
      inner join requested_runs using (run_dir)
      order by items.style_key, items.run_dir, items.y_index
    ),
    published_runs as (
      select
        views.run_dir,
        views.release_id,
        views.media_access_version
      from public.run_view_index as views
      inner join requested_runs using (run_dir)
    )
    select jsonb_build_object(
      'owned_style_keys', coalesce(
        (
          select jsonb_agg(style_key order by style_key)
          from owned_styles
        ),
        '[]'::jsonb
      ),
      'placements', coalesce(
        (
          select jsonb_agg(
            jsonb_build_object(
              'style_key', style_key,
              'run_dir', run_dir,
              'y_index', y_index
            )
            order by style_key, run_dir
          )
          from placement_rows
        ),
        '[]'::jsonb
      ),
      'runs', coalesce(
        (
          select jsonb_agg(
            jsonb_build_object(
              'run_dir', run_dir,
              'release_id', release_id,
              'media_access_version', media_access_version
            )
            order by run_dir
          )
          from published_runs
        ),
        '[]'::jsonb
      )
    )
  );
end;
$function$;

revoke execute on function public.get_style_comparison_slice(text[], text[]) from public, anon;
grant execute on function public.get_style_comparison_slice(text[], text[]) to authenticated;

create or replace function public.get_style_comparison_models()
returns table (
  run_dir text,
  name text,
  created_at text,
  x_columns jsonb
)
language sql
stable
security invoker
set search_path = ''
as $function$
  select
    views.run_dir,
    list_items.model_name as name,
    coalesce(list_items.created_at::text, '') as created_at,
    coalesce(runs.x_columns, '[]'::jsonb) as x_columns
  from public.run_view_index as views
  left join public.run_list_items as list_items using (run_dir)
  left join public.runs as runs using (run_dir)
  order by list_items.created_at desc nulls last, views.run_dir;
$function$;

revoke execute on function public.get_style_comparison_models() from public;
grant execute on function public.get_style_comparison_models() to anon, authenticated;
