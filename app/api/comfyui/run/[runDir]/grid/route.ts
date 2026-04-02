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

function pickXColumn(raw: JsonObject): {
  type: string | null;
  description: JsonObject | null;
} {
  const type = getNonEmptyString(raw.type);
  const description = asJsonObject(raw.description as JsonValue);
  return { type, description };
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
    const PAGE_SIZE = 1000;
    const allRows: GridCellRow[] = [];
    let pageOffset = 0;
    let hasMore = true;

    while (hasMore) {
      const { data: pageData, error: pageError } = await supabase
        .from("comfyui_grid_cells")
        .select(
          "run_dir,x_columns,y_indexes,x_count,y_count,x_index,y_index,batch_index,category,width,height,blurhash",
        )
        .eq("run_dir", runDir)
        .order("y_index", { ascending: true })
        .order("x_index", { ascending: true })
        .order("batch_index", { ascending: true })
        .range(pageOffset, pageOffset + PAGE_SIZE - 1);

      if (pageError) {
        return Response.json(
          { error: "Failed to load run grid" },
          { status: 500 },
        );
      }

      const rows = (pageData ?? []) as GridCellRow[];
      allRows.push(...rows);

      if (rows.length < PAGE_SIZE) {
        hasMore = false;
      } else {
        pageOffset += PAGE_SIZE;
      }
    }

    if (allRows.length === 0) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const firstRow = allRows[0];
    const xColumnsRaw = firstRow.x_columns;
    const yIndexesRaw = firstRow.y_indexes;

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
      typeof firstRow.x_count === "number"
        ? firstRow.x_count
        : x_columns.length;
    const y_count =
      typeof firstRow.y_count === "number"
        ? firstRow.y_count
        : y_indexes.length;

    type BlurhashRow = {
      x_index: number;
      y_index: number;
      batch_index: number;
      category: ImageCategory;
      width: number | null;
      height: number | null;
      blurhash: string | null;
    };

    const blurhash_cells: BlurhashRow[] = allRows
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
