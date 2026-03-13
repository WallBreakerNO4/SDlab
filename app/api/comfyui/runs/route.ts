import type { RunSummary } from "@/lib/comfyui-types";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type { SupabaseRunRow } from "@/lib/supabase-types";

export const runtime = "nodejs";

function getNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function getNonNegativeInteger(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    return null;
  }
  return value;
}

function readModelMetadata(row: SupabaseRunRow) {
  return {
    name: getNonEmptyString(row.model_name),
    description: {
      zh: getNonEmptyString(row.model_description_zh),
      en: getNonEmptyString(row.model_description_en),
    },
    links: {
      homepage: getNonEmptyString(row.model_homepage),
      huggingface: getNonEmptyString(row.model_huggingface),
      civitai: getNonEmptyString(row.model_civitai),
    },
  };
}

export async function GET(): Promise<Response> {
  try {
    const supabase = await createSupabaseAuthClient();
    const { data, error } = await supabase
      .from("runs")
      .select(
        "run_id, run_dir, created_at, x_count, y_count, total_cells, model_name, model_description_zh, model_description_en, model_homepage, model_huggingface, model_civitai",
      )
      .order("created_at", { ascending: false });

    if (error) {
      return Response.json(
        {
          error: "Failed to load runs",
        },
        { status: 500 },
      );
    }

    const rows = (data as SupabaseRunRow[] | null) ?? [];
    const runs: RunSummary[] = [];
    for (const row of rows) {
      const runId = getNonEmptyString(row.run_id);
      const xCount = getNonNegativeInteger(row.x_count);
      const yCount = getNonNegativeInteger(row.y_count);
      const totalCells = getNonNegativeInteger(row.total_cells);

      if (!runId || xCount === null || yCount === null || totalCells === null) {
        return Response.json(
          {
            error: "Failed to load runs",
          },
          { status: 500 },
        );
      }

      runs.push({
        run_id: runId,
        created_at: row.created_at,
        run_dir: row.run_dir,
        x_count: xCount,
        y_count: yCount,
        total_cells: totalCells,
        model: readModelMetadata(row),
      });
    }

    return Response.json(runs);
  } catch {
    return Response.json(
      {
        error: "Failed to load runs",
      },
      { status: 500 },
    );
  }
}
