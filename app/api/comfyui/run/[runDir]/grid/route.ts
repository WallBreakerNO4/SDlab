import { isValidRunDir } from "@/lib/comfyui-types";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type {
  ImageCategory,
  JsonObject,
  JsonValue,
} from "@/lib/supabase-types";

export const runtime = "nodejs";

type GridCellRow = {
  run_dir: string;
  x_columns: JsonValue[] | null;
  y_indexes: number[] | null;
  x_count: number | null;
  y_count: number | null;
  x_index: number | null;
  y_index: number | null;
  batch_index: number | null;
  category: ImageCategory | null;
  width: number | null;
  height: number | null;
  blurhash: string | null;
};

type RouteContext = {
  params: Promise<{ runDir: string }>;
};

type GridMetaRow = {
  x_columns: JsonValue[] | null;
  y_indexes: number[] | null;
  x_count: number | null;
  y_count: number | null;
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

function parseNonNegativeInt(raw: string | null): number | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!/^[0-9]+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value < 0) return null;
  return value;
}

function pickXColumn(raw: JsonObject): {
  type: string | null;
  description: JsonObject | null;
} {
  const type = getNonEmptyString(raw.type);
  const description = asJsonObject(raw.description as JsonValue);
  return { type, description };
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { runDir } = await context.params;
    if (!isValidRunDir(runDir)) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const supabase = await createSupabaseAuthClient();
    const { data: metaData, error: metaError } = await supabase
      .from("runs")
      .select("x_columns,y_indexes,x_count,y_count")
      .eq("run_dir", runDir)
      .maybeSingle();

    if (metaError) {
      return Response.json(
        { error: "Failed to load run grid" },
        { status: 500 },
      );
    }

    const metaRow = (metaData as GridMetaRow | null) ?? null;
    if (!metaRow) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const xColumnsRaw = metaRow.x_columns;
    const yIndexesRaw = metaRow.y_indexes;

    const x_columns = Array.isArray(xColumnsRaw)
      ? xColumnsRaw
          .map((item) => asJsonObject(item as JsonValue))
          .filter((item): item is JsonObject => item !== null)
          .map(pickXColumn)
      : [];

    const y_indexes: number[] = Array.isArray(yIndexesRaw)
      ? yIndexesRaw.filter(
          (item): item is number =>
            typeof item === "number" && Number.isFinite(item),
        )
      : [];

    const x_count =
      typeof metaRow.x_count === "number" ? metaRow.x_count : x_columns.length;
    const y_count =
      typeof metaRow.y_count === "number" ? metaRow.y_count : y_indexes.length;

    const url = new URL(request.url);
    const yOffset = parseNonNegativeInt(url.searchParams.get("y_offset"));
    const yLimit = parseNonNegativeInt(url.searchParams.get("y_limit"));

    if ((yOffset === null) !== (yLimit === null)) {
      return Response.json({ error: "Invalid grid range" }, { status: 400 });
    }

    const selectedYIndexes =
      yOffset !== null && yLimit !== null
        ? y_indexes.slice(yOffset, yOffset + Math.min(yLimit, 64))
        : [];

    let gridRows: GridCellRow[] = [];

    if (selectedYIndexes.length > 0) {
      const { data: gridData, error: gridError } = await supabase
        .from("comfyui_grid_cells")
        .select(
          "run_dir,x_columns,y_indexes,x_count,y_count,x_index,y_index,batch_index,category,width,height,blurhash",
        )
        .eq("run_dir", runDir)
        .in("y_index", selectedYIndexes)
        .order("y_index", { ascending: true })
        .order("x_index", { ascending: true })
        .order("batch_index", { ascending: true });

      if (gridError) {
        return Response.json(
          { error: "Failed to load run grid" },
          { status: 500 },
        );
      }

      gridRows = (gridData ?? []) as GridCellRow[];
    }

    type BlurhashRow = {
      x_index: number;
      y_index: number;
      batch_index: number;
      category: ImageCategory;
      width: number | null;
      height: number | null;
      blurhash: string | null;
    };

    const blurhash_cells: BlurhashRow[] = gridRows
      .filter(
        (
          item,
        ): item is GridCellRow & {
          x_index: number;
          y_index: number;
          batch_index: number;
          category: ImageCategory;
        } =>
          typeof item.x_index === "number" &&
          typeof item.y_index === "number" &&
          typeof item.batch_index === "number" &&
          typeof item.category === "string",
      )
      .map((item) => ({
        x_index: item.x_index,
        y_index: item.y_index,
        batch_index: item.batch_index,
        category: item.category,
        width: item.width,
        height: item.height,
        blurhash: item.blurhash,
      }));

    return Response.json({
      x_columns,
      y_indexes,
      x_count,
      y_count,
      cells: {},
      blurhash_cells,
      y_offset: yOffset,
      y_limit: selectedYIndexes.length,
    });
  } catch {
    return Response.json(
      {
        error: "Failed to load run grid",
      },
      { status: 500 },
    );
  }
}
