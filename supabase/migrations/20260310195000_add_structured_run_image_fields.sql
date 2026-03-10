alter table public.runs
  add column if not exists run_id text,
  add column if not exists x_columns jsonb not null default '[]'::jsonb,
  add column if not exists y_indexes integer[] not null default '{}'::integer[],
  add column if not exists x_count integer not null default 0,
  add column if not exists y_count integer not null default 0,
  add column if not exists total_cells integer not null default 0;

alter table public.images
  add column if not exists seed bigint,
  add column if not exists prompt_hash text,
  add column if not exists positive_prompt text,
  add column if not exists y_value text;

with extracted_runs as (
  select
    r.id,
    coalesce(
      case when jsonb_typeof(r.run_json -> 'selection') = 'object' then r.run_json -> 'selection' end,
      case
        when jsonb_typeof(r.run_json -> 'config_snapshot' -> 'selection') = 'object'
          then r.run_json -> 'config_snapshot' -> 'selection'
      end
    ) as selection,
    nullif(btrim(r.run_json ->> 'run_id'), '') as extracted_run_id
  from public.runs as r
)
update public.runs as r
set
  run_id = coalesce(er.extracted_run_id, r.run_dir),
  x_columns = case
    when er.selection is not null and jsonb_typeof(er.selection -> 'x_columns') = 'array'
      then er.selection -> 'x_columns'
    else r.x_columns
  end,
  y_indexes = coalesce(
    case
      when er.selection is not null and jsonb_typeof(er.selection -> 'y_indexes') = 'array'
        then (
          select coalesce(array_agg(value::integer order by ordinality), '{}'::integer[])
          from jsonb_array_elements_text(er.selection -> 'y_indexes') with ordinality as y(value, ordinality)
          where value ~ '^-?\d+$'
        )
    end,
    r.y_indexes
  ),
  x_count = coalesce(
    case
      when er.selection is not null and jsonb_typeof(er.selection -> 'x_count') = 'number'
        then (er.selection ->> 'x_count')::integer
    end,
    case
      when er.selection is not null and jsonb_typeof(er.selection -> 'x_columns') = 'array'
        then jsonb_array_length(er.selection -> 'x_columns')
    end,
    r.x_count
  ),
  y_count = coalesce(
    case
      when er.selection is not null and jsonb_typeof(er.selection -> 'y_count') = 'number'
        then (er.selection ->> 'y_count')::integer
    end,
    case
      when er.selection is not null and jsonb_typeof(er.selection -> 'y_indexes') = 'array'
        then jsonb_array_length(er.selection -> 'y_indexes')
    end,
    r.y_count
  ),
  total_cells = coalesce(
    case
      when er.selection is not null and jsonb_typeof(er.selection -> 'total_cells') = 'number'
        then (er.selection ->> 'total_cells')::integer
    end,
    (
      coalesce(
        case
          when er.selection is not null and jsonb_typeof(er.selection -> 'x_count') = 'number'
            then (er.selection ->> 'x_count')::integer
        end,
        case
          when er.selection is not null and jsonb_typeof(er.selection -> 'x_columns') = 'array'
            then jsonb_array_length(er.selection -> 'x_columns')
        end,
        r.x_count
      )
      *
      coalesce(
        case
          when er.selection is not null and jsonb_typeof(er.selection -> 'y_count') = 'number'
            then (er.selection ->> 'y_count')::integer
        end,
        case
          when er.selection is not null and jsonb_typeof(er.selection -> 'y_indexes') = 'array'
            then jsonb_array_length(er.selection -> 'y_indexes')
        end,
        r.y_count
      )
    ),
    r.total_cells
  )
from extracted_runs as er
where er.id = r.id;

update public.images
set
  seed = coalesce(
    case when jsonb_typeof(metadata -> 'seed') = 'number' then (metadata ->> 'seed')::bigint end,
    seed
  ),
  prompt_hash = coalesce(nullif(btrim(metadata ->> 'prompt_hash'), ''), prompt_hash),
  positive_prompt = coalesce(nullif(btrim(metadata ->> 'positive_prompt'), ''), positive_prompt),
  y_value = coalesce(nullif(btrim(metadata ->> 'y_value'), ''), y_value);

alter table public.runs
  alter column run_id set not null;

create index if not exists runs_created_at_desc_idx on public.runs(created_at desc);
create index if not exists images_run_id_y_index_x_index_batch_index_idx
  on public.images(run_id, y_index, x_index, batch_index);
create index if not exists image_variants_image_id_idx on public.image_variants(image_id);
