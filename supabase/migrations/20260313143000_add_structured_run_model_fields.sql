alter table public.runs
  add column if not exists model_name text,
  add column if not exists model_description_zh text,
  add column if not exists model_description_en text,
  add column if not exists model_homepage text,
  add column if not exists model_huggingface text,
  add column if not exists model_civitai text;

update public.runs
set
  model_name = case
    when jsonb_typeof(run_json -> 'model') = 'object'
      then nullif(btrim(run_json -> 'model' ->> 'name'), '')
    else model_name
  end,
  model_description_zh = case
    when jsonb_typeof(run_json -> 'model' -> 'description') = 'object'
      then nullif(btrim(run_json -> 'model' -> 'description' ->> 'zh'), '')
    else model_description_zh
  end,
  model_description_en = case
    when jsonb_typeof(run_json -> 'model' -> 'description') = 'object'
      then nullif(btrim(run_json -> 'model' -> 'description' ->> 'en'), '')
    else model_description_en
  end,
  model_homepage = case
    when jsonb_typeof(run_json -> 'model' -> 'links') = 'object'
      then nullif(btrim(run_json -> 'model' -> 'links' ->> 'homepage'), '')
    else model_homepage
  end,
  model_huggingface = case
    when jsonb_typeof(run_json -> 'model' -> 'links') = 'object'
      then nullif(btrim(run_json -> 'model' -> 'links' ->> 'huggingface'), '')
    else model_huggingface
  end,
  model_civitai = case
    when jsonb_typeof(run_json -> 'model' -> 'links') = 'object'
      then nullif(btrim(run_json -> 'model' -> 'links' ->> 'civitai'), '')
    else model_civitai
  end;
