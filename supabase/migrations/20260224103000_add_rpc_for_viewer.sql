-- 1) runs 列表（游标分页，按 created_at desc, run_dir desc）
create or replace function public.get_run_summaries(
  limit_count int default 50,
  cursor_created_at timestamptz default null,
  cursor_run_dir text default null
)
returns table (
  run_dir text,
  created_at timestamptz,
  x_count int,
  y_count int,
  total_cells int
)
language sql
stable
security invoker
as $$
  select
    r.run_dir,
    r.created_at,
    coalesce(nullif((r.run_json->'selection'->>'x_count')::int, 0),
             jsonb_array_length(coalesce(r.run_json->'selection'->'x_indexes', '[]'::jsonb))) as x_count,
    coalesce(nullif((r.run_json->'selection'->>'y_count')::int, 0),
             jsonb_array_length(coalesce(r.run_json->'selection'->'y_indexes', '[]'::jsonb))) as y_count,
    coalesce(nullif((r.run_json->'selection'->>'total_cells')::int, 0),
             (coalesce(nullif((r.run_json->'selection'->>'x_count')::int, 0),
                       jsonb_array_length(coalesce(r.run_json->'selection'->'x_indexes', '[]'::jsonb)))
              *
              coalesce(nullif((r.run_json->'selection'->>'y_count')::int, 0),
                       jsonb_array_length(coalesce(r.run_json->'selection'->'y_indexes', '[]'::jsonb))))) as total_cells
  from public.runs r
  where
    (cursor_created_at is null)
    or ((r.created_at, r.run_dir) < (cursor_created_at, coalesce(cursor_run_dir, '')))
  order by r.created_at desc, r.run_dir desc
  limit greatest(1, least(limit_count, 200));
$$;

grant execute on function public.get_run_summaries(int, timestamptz, text) to anon, authenticated;

-- 2) grid meta（列可见性依赖 RLS：anon 只会看到 normal images/variants）
create or replace function public.get_run_grid_meta(
  target_run_dir text
)
returns table (
  x_columns jsonb,
  y_labels text[],
  x_count int,
  y_count int
)
language sql
stable
security invoker
as $$
  with target as (
    select id, run_json
    from public.runs
    where run_dir = target_run_dir
    limit 1
  ),
  x_first as (
    select distinct on (i.x_index)
      i.x_index,
      i.category,
      i.metadata
    from public.images i
    join target t on t.id = i.run_id
    where i.batch_index = 0
    order by i.x_index asc, i.y_index asc
  ),
  x_visible as (
    select
      xf.x_index,
      xf.category,
      xf.metadata,
      row_number() over (order by xf.x_index) - 1 as visible_x_index
    from x_first xf
  ),
  y_first as (
    select distinct on (i.y_index)
      i.y_index,
      i.metadata
    from public.images i
    join target t on t.id = i.run_id
    where i.batch_index = 0
    order by i.y_index asc, i.x_index asc
  ),
  y_count_raw as (
    select
      coalesce(nullif((t.run_json->'selection'->>'y_count')::int, 0),
               jsonb_array_length(coalesce(t.run_json->'selection'->'y_indexes', '[]'::jsonb))) as y_count
    from target t
  )
  select
    (
      select coalesce(
        jsonb_agg(
          jsonb_build_object(
            'visible_x_index', xv.visible_x_index,
            'original_x_index', xv.x_index,
            'category', xv.category,
            'label',
              coalesce(
                nullif(trim(
                  concat_ws(' ',
                    nullif(trim(xv.metadata #>> '{x_fields,quality}'), ''),
                    nullif(trim(xv.metadata #>> '{x_fields,rating}'), ''),
                    nullif(trim(xv.metadata #>> '{x_fields,gender}'), ''),
                    nullif(trim(xv.metadata #>> '{x_fields,characters}'), ''),
                    nullif(trim(xv.metadata #>> '{x_fields,series}'), ''),
                    nullif(trim(xv.metadata #>> '{x_fields,general}'), '')
                  )
                ), ''),
                'x' || xv.x_index::text
              )
          )
          order by xv.x_index
        ),
        '[]'::jsonb
      )
      from x_visible xv
    ) as x_columns,
    (
      select array_agg(
        coalesce(
          nullif(trim(yf.metadata->>'y_value'), ''),
          'y' || yi::text
        )
        order by yi
      )
      from generate_series(0, (select y_count from y_count_raw) - 1) as yi
      left join y_first yf on yf.y_index = yi
    ) as y_labels,
    (select count(*) from x_first) as x_count,
    (select y_count from y_count_raw) as y_count
  from target t;
$$;

grant execute on function public.get_run_grid_meta(text) to anon, authenticated;

-- 3) grid chunk（返回 y 范围内的 cells；每个 cell 聚合 batch items；variant 用 id 做 proxy key）
create or replace function public.get_run_grid_chunk(
  target_run_dir text,
  y_from int,
  y_to int
)
returns table (
  x_index int,
  y_index int,
  status text,
  blurhash text,
  seed bigint,
  prompt_hash text,
  positive_prompt text,
  generation_params jsonb,
  items jsonb
)
language sql
stable
security invoker
as $$
  with target as (
    select id
    from public.runs
    where run_dir = target_run_dir
    limit 1
  ),
  rows as (
    select
      i.id as image_id,
      i.x_index,
      i.y_index,
      i.batch_index,
      i.blurhash,
      i.metadata
    from public.images i
    join target t on t.id = i.run_id
    where i.y_index between y_from and y_to
    order by i.y_index asc, i.x_index asc, i.batch_index asc
  ),
  v as (
    select
      iv.*, i.x_index, i.y_index, i.batch_index
    from public.image_variants iv
    join rows i on i.image_id = iv.image_id
  ),
  per_image as (
    select
      r.x_index,
      r.y_index,
      r.batch_index,
      r.blurhash,
      coalesce(nullif(trim(r.metadata->>'status'), ''), 'missing') as status,
      nullif(trim(r.metadata->>'prompt_hash'), '') as prompt_hash,
      nullif(trim(r.metadata->>'positive_prompt'), '') as positive_prompt,
      (r.metadata->'generation_params') as generation_params,
      case
        when (r.metadata->>'seed') ~ '^[0-9]+$' then (r.metadata->>'seed')::bigint
        else null
      end as seed,
      coalesce(vd_avif.id, vd_webp.id) as display_variant_id,
      coalesce(vd_avif.bucket, vd_webp.bucket) as display_bucket,
      coalesce(vd_avif.r2_key, vd_webp.r2_key) as display_r2_key,
      coalesce(vt_avif.id, vt_webp.id) as thumb_variant_id,
      coalesce(vt_avif.bucket, vt_webp.bucket) as thumb_bucket,
      coalesce(vt_avif.r2_key, vt_webp.r2_key) as thumb_r2_key,
      vo.id as original_variant_id,
      vo.bucket as original_bucket,
      vo.r2_key as original_r2_key
    from rows r
    left join v vd_avif on vd_avif.x_index=r.x_index and vd_avif.y_index=r.y_index and vd_avif.batch_index=r.batch_index and vd_avif.variant='display_avif'
    left join v vd_webp on vd_webp.x_index=r.x_index and vd_webp.y_index=r.y_index and vd_webp.batch_index=r.batch_index and vd_webp.variant='display_webp'
    left join v vt_avif on vt_avif.x_index=r.x_index and vt_avif.y_index=r.y_index and vt_avif.batch_index=r.batch_index and vt_avif.variant='thumb_avif'
    left join v vt_webp on vt_webp.x_index=r.x_index and vt_webp.y_index=r.y_index and vt_webp.batch_index=r.batch_index and vt_webp.variant='thumb_webp'
    left join v vo on vo.x_index=r.x_index and vo.y_index=r.y_index and vo.batch_index=r.batch_index and vo.variant='original_png'
  )
  select
    pi.x_index,
    pi.y_index,
    max(pi.status) filter (where pi.batch_index = 0) as status,
    max(pi.blurhash) filter (where pi.batch_index = 0) as blurhash,
    max(pi.seed) filter (where pi.batch_index = 0) as seed,
    max(pi.prompt_hash) filter (where pi.batch_index = 0) as prompt_hash,
    max(pi.positive_prompt) filter (where pi.batch_index = 0) as positive_prompt,
    (jsonb_agg(pi.generation_params) filter (where pi.batch_index = 0) -> 0) as generation_params,
    jsonb_agg(
      jsonb_build_object(
        'batch_index', pi.batch_index,
        'display', jsonb_build_object('variant_id', pi.display_variant_id, 'bucket', pi.display_bucket, 'r2_key', pi.display_r2_key),
        'thumb', jsonb_build_object('variant_id', pi.thumb_variant_id, 'bucket', pi.thumb_bucket, 'r2_key', pi.thumb_r2_key),
        'original', jsonb_build_object('variant_id', pi.original_variant_id, 'bucket', pi.original_bucket, 'r2_key', pi.original_r2_key)
      )
      order by pi.batch_index
    ) as items
  from per_image pi
  group by pi.x_index, pi.y_index
  order by pi.y_index asc, pi.x_index asc;
$$;

grant execute on function public.get_run_grid_chunk(text, int, int) to anon, authenticated;
