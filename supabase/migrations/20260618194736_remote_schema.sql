drop index if exists "public"."runs_created_at_desc_idx";

set check_function_bodies = off;

CREATE OR REPLACE FUNCTION public.rls_auto_enable()
 RETURNS event_trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$function$
;

grant delete on table "public"."run_grid_cells" to "anon";

grant insert on table "public"."run_grid_cells" to "anon";

grant select on table "public"."run_grid_cells" to "anon";

grant update on table "public"."run_grid_cells" to "anon";

grant delete on table "public"."run_grid_cells" to "authenticated";

grant insert on table "public"."run_grid_cells" to "authenticated";

grant select on table "public"."run_grid_cells" to "authenticated";

grant update on table "public"."run_grid_cells" to "authenticated";

grant delete on table "public"."run_grid_cells" to "service_role";

grant delete on table "public"."run_grid_item_snapshots" to "anon";

grant insert on table "public"."run_grid_item_snapshots" to "anon";

grant select on table "public"."run_grid_item_snapshots" to "anon";

grant update on table "public"."run_grid_item_snapshots" to "anon";

grant delete on table "public"."run_grid_item_snapshots" to "authenticated";

grant insert on table "public"."run_grid_item_snapshots" to "authenticated";

grant select on table "public"."run_grid_item_snapshots" to "authenticated";

grant update on table "public"."run_grid_item_snapshots" to "authenticated";

grant delete on table "public"."run_grid_item_snapshots" to "service_role";

grant delete on table "public"."run_grid_items" to "anon";

grant insert on table "public"."run_grid_items" to "anon";

grant select on table "public"."run_grid_items" to "anon";

grant update on table "public"."run_grid_items" to "anon";

grant delete on table "public"."run_grid_items" to "authenticated";

grant insert on table "public"."run_grid_items" to "authenticated";

grant select on table "public"."run_grid_items" to "authenticated";

grant update on table "public"."run_grid_items" to "authenticated";

grant delete on table "public"."run_grid_items" to "service_role";

grant delete on table "public"."run_list_items" to "anon";

grant insert on table "public"."run_list_items" to "anon";

grant select on table "public"."run_list_items" to "anon";

grant update on table "public"."run_list_items" to "anon";

grant delete on table "public"."run_list_items" to "authenticated";

grant insert on table "public"."run_list_items" to "authenticated";

grant select on table "public"."run_list_items" to "authenticated";

grant update on table "public"."run_list_items" to "authenticated";

grant delete on table "public"."run_list_items" to "service_role";

grant delete on table "public"."run_prompts" to "anon";

grant insert on table "public"."run_prompts" to "anon";

grant select on table "public"."run_prompts" to "anon";

grant update on table "public"."run_prompts" to "anon";

grant delete on table "public"."run_prompts" to "authenticated";

grant insert on table "public"."run_prompts" to "authenticated";

grant select on table "public"."run_prompts" to "authenticated";

grant update on table "public"."run_prompts" to "authenticated";

grant delete on table "public"."run_prompts" to "service_role";

grant insert on table "public"."run_prompts" to "service_role";

grant select on table "public"."run_prompts" to "service_role";

grant update on table "public"."run_prompts" to "service_role";

grant delete on table "public"."run_snapshots" to "anon";

grant insert on table "public"."run_snapshots" to "anon";

grant select on table "public"."run_snapshots" to "anon";

grant update on table "public"."run_snapshots" to "anon";

grant delete on table "public"."run_snapshots" to "authenticated";

grant insert on table "public"."run_snapshots" to "authenticated";

grant select on table "public"."run_snapshots" to "authenticated";

grant update on table "public"."run_snapshots" to "authenticated";

grant delete on table "public"."run_snapshots" to "service_role";

grant delete on table "public"."run_view_index" to "anon";

grant insert on table "public"."run_view_index" to "anon";

grant select on table "public"."run_view_index" to "anon";

grant update on table "public"."run_view_index" to "anon";

grant delete on table "public"."run_view_index" to "authenticated";

grant insert on table "public"."run_view_index" to "authenticated";

grant select on table "public"."run_view_index" to "authenticated";

grant update on table "public"."run_view_index" to "authenticated";

grant delete on table "public"."run_view_index" to "service_role";

grant insert on table "public"."run_view_index" to "service_role";

grant select on table "public"."run_view_index" to "service_role";

grant update on table "public"."run_view_index" to "service_role";

grant delete on table "public"."runs" to "anon";

grant insert on table "public"."runs" to "anon";

grant select on table "public"."runs" to "anon";

grant update on table "public"."runs" to "anon";

grant delete on table "public"."runs" to "authenticated";

grant insert on table "public"."runs" to "authenticated";

grant select on table "public"."runs" to "authenticated";

grant update on table "public"."runs" to "authenticated";

grant delete on table "public"."runs" to "service_role";

grant delete on table "public"."user_preferences" to "anon";

grant insert on table "public"."user_preferences" to "anon";

grant select on table "public"."user_preferences" to "anon";

grant update on table "public"."user_preferences" to "anon";

grant delete on table "public"."user_preferences" to "authenticated";

grant delete on table "public"."user_preferences" to "service_role";


