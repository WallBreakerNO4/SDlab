-- 修复 RLS 策略：anon 应能看到所有 images 的 metadata/blurhash
-- 目的：未登录用户看到 nsfw/advance 列的 blurhash 占位，但无法获取实际图片 URL
-- 图片文件本身由 R2 私有代理的 auth check 保护

-- ============================================================
-- runs: anon 可以看到所有 runs（不再限制"仅含 normal images 的 runs"）
-- ============================================================
drop policy if exists anon_select_runs_with_normal_images on public.runs;

create policy anon_select_all_runs
  on public.runs
  for select
  to anon
  using (true);

-- ============================================================
-- images: anon 可以看到所有 images（不再限制 category = 'normal'）
-- ============================================================
drop policy if exists anon_select_normal_images on public.images;

create policy anon_select_all_images
  on public.images
  for select
  to anon
  using (true);

-- ============================================================
-- image_variants: anon 只能看到 public bucket 的变体（不再限制关联 image 必须是 normal）
-- 效果：normal 的 display/thumb 可见；nsfw/advance 的变体（存在 private bucket）不可见
-- ============================================================
drop policy if exists anon_select_public_variants_for_normal_images on public.image_variants;

create policy anon_select_public_variants
  on public.image_variants
  for select
  to anon
  using (bucket = 'public');