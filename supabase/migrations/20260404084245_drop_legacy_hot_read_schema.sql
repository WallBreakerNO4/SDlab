drop view if exists public.comfyui_grid_cells;
drop view if exists public.comfyui_row_items;

drop table if exists public.run_asset_variants;
drop table if exists public.run_assets;
drop table if exists public.image_variants;
drop table if exists public.images;

alter table public.runs
  drop column if exists run_json;
