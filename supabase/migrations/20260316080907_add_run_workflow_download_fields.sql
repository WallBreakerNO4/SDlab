alter table public.runs
  add column if not exists workflow_download_r2_key text,
  add column if not exists workflow_download_sha256 text;
