-- `20260720130000` 使用了晚于 CLI 当前 UTC 的时间戳。此文件先由 CLI 创建，
-- 再经明确批准调整为 14:00，以保证三参数 overload 在原始 RPC 迁移之后执行。
-- 两参数版本暂时保留，避免 migration 与 Worker 滚动部署期间旧实例调用失败。

create or replace function public.get_style_comparison_slice(
  p_style_keys text[],
  p_run_dirs text[],
  p_include_nsfw boolean
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

  if p_include_nsfw is null
    or coalesce(cardinality(p_style_keys), 0) not between 1 and 40
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
    with requested_styles as materialized (
      select distinct style_key
      from unnest(p_style_keys) as style_key
    ),
    requested_runs as materialized (
      select distinct run_dir
      from unnest(p_run_dirs) as run_dir
    ),
    owned_styles as materialized (
      select favorites.style_key
      from public.user_style_favorites as favorites
      inner join requested_styles using (style_key)
      where favorites.user_id = viewer_id
    ),
    target_placements as materialized (
      select distinct on (items.style_key, items.run_dir)
        items.style_key,
        items.run_dir,
        items.run_id,
        items.y_index
      from public.run_style_items as items
      inner join owned_styles using (style_key)
      inner join requested_runs using (run_dir)
      order by items.style_key, items.run_dir, items.y_index, items.run_id
    ),
    placement_rows as (
      select
        placements.style_key,
        placements.run_dir,
        placements.y_index,
        coalesce(
          jsonb_agg(
            jsonb_build_array(
              grid.x_index,
              grid.batch_index,
              grid.blurhash
            )
            order by grid.x_index, grid.batch_index
          ) filter (where grid.blurhash is not null),
          '[]'::jsonb
        ) as blurhashes
      from target_placements as placements
      left join public.run_grid_items as grid
        on grid.run_id = placements.run_id
        and grid.y_index = placements.y_index
        and nullif(btrim(grid.blurhash), '') is not null
        and (p_include_nsfw or grid.category <> 'nsfw')
      group by placements.style_key, placements.run_dir, placements.y_index
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
              'y_index', y_index,
              'blurhashes', blurhashes
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

revoke execute on function public.get_style_comparison_slice(text[], text[], boolean) from public, anon;
grant execute on function public.get_style_comparison_slice(text[], text[], boolean) to authenticated;
