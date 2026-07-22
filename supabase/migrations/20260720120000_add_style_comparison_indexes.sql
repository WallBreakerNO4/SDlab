-- Indexes for keyset favorite pagination and bounded style/run placement lookups.
create index if not exists user_style_favorites_user_created_style_idx
  on public.user_style_favorites (user_id, created_at desc, style_key);

create index if not exists run_style_items_style_run_y_idx
  on public.run_style_items (style_key, run_dir) include (y_index);
