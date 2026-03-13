import { isValidRunDir } from "@/lib/comfyui-types";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type {
  JsonObject,
  JsonValue,
  SupabaseRunRow,
} from "@/lib/supabase-types";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ runDir: string }>;
};

function asJsonObject(value: JsonValue): JsonObject | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as JsonObject;
}

function getNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function getNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
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

export async function GET(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params;
    if (!isValidRunDir(runDir)) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const supabase = await createSupabaseAuthClient();
    const { data, error } = await supabase
      .from("runs")
      .select(
        "run_id, run_dir, created_at, x_columns, y_indexes, x_count, y_count, total_cells, model_name, model_description_zh, model_description_en, model_homepage, model_huggingface, model_civitai",
      )
      .eq("run_dir", runDir)
      .maybeSingle();

    if (error) {
      return Response.json(
        {
          error: "Failed to load run detail",
        },
        { status: 500 },
      );
    }

    const row = data as SupabaseRunRow | null;
    if (!row) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const runId = getNonEmptyString(row.run_id);
    const xColumnsRaw = row.x_columns;
    const yIndexesRaw = row.y_indexes;

    if (!runId || !Array.isArray(xColumnsRaw) || !Array.isArray(yIndexesRaw)) {
      return Response.json(
        {
          error: "Failed to load run detail",
        },
        { status: 500 },
      );
    }

    const x_columns: JsonObject[] = Array.isArray(xColumnsRaw)
      ? xColumnsRaw
          .map((item) => asJsonObject(item as JsonValue))
          .filter((item): item is JsonObject => item !== null)
      : [];

    const y_indexes: number[] = Array.isArray(yIndexesRaw)
      ? yIndexesRaw.filter((item): item is number => typeof item === "number")
      : [];

    const total_cells = getNumber(row.total_cells);

    if (total_cells === null) {
      return Response.json(
        {
          error: "Failed to load run detail",
        },
        { status: 500 },
      );
    }

    const xLabels = x_columns.map((col, index) => {
      const desc = asJsonObject(col.description as JsonValue);
      const zh = desc ? getNonEmptyString(desc.zh) : null;
      return zh ?? `X${index}`;
    });

    const yLabels = y_indexes.map((yIndex) => `Y${yIndex}`);

    return Response.json({
      run: {
        run_id: runId,
        created_at: row.created_at,
        run_dir: row.run_dir,
        selection: {
          total_cells,
        },
        model: readModelMetadata(row),
      },
      xLabels,
      yLabels,
      x_columns,
      y_indexes,
    });
  } catch {
    return Response.json(
      {
        error: "Failed to load run detail",
      },
      { status: 500 },
    );
  }
}
