-- 对比目录返回评测状态：进行中评测在对比页以禁用条目展示，矩阵列与 slice 只消费已完结评测。
-- 目录排序对齐首页，改用 published_at（缺省回退 created_at）；其余列、安全性与 grants 保持不变。
-- 新增返回列无法通过 create or replace 完成，先 drop 再重建，并重新声明同一组最小权限 grants。

drop function if exists public.get_style_comparison_models();

create or replace function public.get_style_comparison_models()
returns table (
  run_dir text,
  name text,
  created_at text,
  published_at text,
  status text,
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
    coalesce(list_items.published_at, list_items.created_at)::text as published_at,
    coalesce(list_items.status, 'complete') as status,
    coalesce(runs.x_columns, '[]'::jsonb) as x_columns
  from public.run_view_index as views
  left join public.run_list_items as list_items using (run_dir)
  left join public.runs as runs using (run_dir)
  order by
    coalesce(list_items.published_at, list_items.created_at) desc nulls last,
    views.run_dir;
$function$;

revoke execute on function public.get_style_comparison_models() from public;
grant execute on function public.get_style_comparison_models() to anon, authenticated;
