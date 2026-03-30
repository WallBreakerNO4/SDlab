alter table public.run_assets
  drop constraint if exists run_assets_asset_role_check;

update public.run_assets
set asset_role = 'homepage_card'
where asset_role = 'homepage_thumb';

alter table public.run_assets
  add constraint run_assets_asset_role_check
  check (asset_role in ('cover', 'homepage_card'));
