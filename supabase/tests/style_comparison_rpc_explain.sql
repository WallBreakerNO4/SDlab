-- 手工验收脚本：仅在本地或 staging 执行，不要在生产请求路径开启 EXPLAIN。
-- 用法：psql "$DATABASE_URL" -v viewer_id='<已有至少 40 个收藏的 auth.users.id>' \
--   -f supabase/tests/style_comparison_rpc_explain.sql
--
-- 脚本只接受真实 fixture：40 个 style 必须共同存在于至少 12 个已发布 run，
-- 最大 slice 必须返回 40 个 owned style、480 个 placement 和 12 个 run。
\if :{?viewer_id}
\else
\echo '必须通过 -v viewer_id=<uuid> 提供真实验收用户'
\quit 1
\endif

begin;

select coalesce(array_agg(style_key order by style_key), '{}'::text[]) as style_keys
from (
  select favorites.style_key
  from public.user_style_favorites as favorites
  inner join public.run_style_items as items using (style_key)
  inner join public.run_view_index as views using (run_dir)
  where favorites.user_id = :'viewer_id'::uuid
  group by favorites.style_key
  having count(distinct items.run_dir) >= 12
  order by favorites.style_key
  limit 40
) as selected_styles
\gset fixture_

select coalesce(array_agg(run_dir order by run_dir), '{}'::text[]) as run_dirs
from (
  select items.run_dir
  from public.run_style_items as items
  inner join public.run_view_index as views using (run_dir)
  where items.style_key = any(:'fixture_style_keys'::text[])
  group by items.run_dir
  having count(distinct items.style_key) = 40
  order by items.run_dir
  limit 12
) as selected_runs
\gset fixture_

select (
  cardinality(:'fixture_style_keys'::text[]) = 40
  and cardinality(:'fixture_run_dirs'::text[]) = 12
) as ready
\gset fixture_
\if :fixture_ready
\else
rollback;
\echo '真实 fixture 不满足共同覆盖 40 x 12，验收终止'
\quit 1
\endif

select set_config('request.jwt.claim.sub', :'viewer_id', true);
set local role authenticated;

-- 1 x 1：最小 slice。
explain (analyze, buffers)
select public.get_style_comparison_slice(
  (:'fixture_style_keys'::text[])[1:1],
  (:'fixture_run_dirs'::text[])[1:1]
);

-- 1 x 6：常见可见模型窗口。
explain (analyze, buffers)
select public.get_style_comparison_slice(
  (:'fixture_style_keys'::text[])[1:1],
  (:'fixture_run_dirs'::text[])[1:6]
);

-- 40 x 12：接口允许的最大 slice。
explain (analyze, buffers)
select public.get_style_comparison_slice(
  :'fixture_style_keys'::text[],
  :'fixture_run_dirs'::text[]
);

select public.get_style_comparison_slice(
  :'fixture_style_keys'::text[],
  :'fixture_run_dirs'::text[]
) as result
\gset rpc_

select
  jsonb_array_length(:'rpc_result'::jsonb -> 'owned_style_keys') = 40 as owned_ok,
  jsonb_array_length(:'rpc_result'::jsonb -> 'placements') = 480 as placements_ok,
  jsonb_array_length(:'rpc_result'::jsonb -> 'runs') = 12 as runs_ok
\gset verify_

\if :verify_owned_ok
\else
rollback;
\echo 'owned_style_keys 数量不是 40'
\quit 1
\endif
\if :verify_placements_ok
\else
rollback;
\echo 'placements 数量不是 480'
\quit 1
\endif
\if :verify_runs_ok
\else
rollback;
\echo 'runs 数量不是 12'
\quit 1
\endif

rollback;
