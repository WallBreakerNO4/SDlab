import { isValidRunDir } from "@/lib/comfyui-types";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type {
  ImageCategory,
  JsonObject,
  JsonValue,
  SupabaseRunGridCellRow,
} from "@/lib/supabase-types";

export const runtime = "nodejs";

type RunGridMetaRow = {
  x_columns: JsonValue[] | null;
  y_indexes: number[] | null;
  x_count: number | null;
  y_count: number | null;
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
    const [runMetaResult, firstPageResult] = await Promise.all([
      supabase
        .from("runs")
        .select("x_columns,y_indexes,x_count,y_count")
        .eq("run_dir", runDir)
        .maybeSingle(),
      supabase
        .from("run_grid_cells")
        .select(
          "x_index,y_index,representative_batch_index,category,width,height,blurhash",
        )
        .eq("run_dir", runDir)
        .order("y_index", { ascending: true })
        .order("x_index", { ascending: true })
        .range(0, PAGE_SIZE - 1),
    ]);

    if (runMetaResult.error) {
      return Response.json(
        { error: "Failed to load run grid" },
        { status: 500 },
      );
    }

    const runMeta = runMetaResult.data as RunGridMetaRow | null;
    if (!runMeta) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    if (firstPageResult.error) {
      return Response.json(
        { error: "Failed to load run grid" },
        { status: 500 },
      );
    }

    const rows: SupabaseRunGridCellRow[] =
      (firstPageResult.data as SupabaseRunGridCellRow[] | null) ?? [];
    const blurhash_cells: Array<{
      x_index: number;
      y_index: number;
      batch_index: number;
      category: ImageCategory;
      width: number | null;
      height: number | null;
      blurhash: string | null;
    }> = [];

    for (const row of rows) {
      if (
        typeof row.x_index === "number" &&
        typeof row.y_index === "number" &&
        typeof row.representative_batch_index === "number" &&
        typeof row.category === "string"
      ) {
        blurhash_cells.push({
          x_index: row.x_index,
          y_index: row.y_index,
          batch_index: row.representative_batch_index,
          category: row.category,
          width: row.width,
          height: row.height,
          blurhash: row.blurhash,
        });
      }
    }

    let pageOffset = PAGE_SIZE;
    let hasMore = rows.length === PAGE_SIZE;
    while (hasMore) {
      const { data: pageData, error: pageError } = await supabase
        .from("run_grid_cells")
        .select(
          "x_index,y_index,representative_batch_index,category,width,height,blurhash",
        )
        .eq("run_dir", runDir)
        .order("y_index", { ascending: true })
        .order("x_index", { ascending: true })
        .range(pageOffset, pageOffset + PAGE_SIZE - 1);

      if (pageError) {
        return Response.json(
          { error: "Failed to load run grid" },
          { status: 500 },
        );
      }

      const pageRows = (pageData as SupabaseRunGridCellRow[] | null) ?? [];
      for (const row of pageRows) {
        if (
          typeof row.x_index === "number" &&
          typeof row.y_index === "number" &&
          typeof row.representative_batch_index === "number" &&
          typeof row.category === "string"
        ) {
          blurhash_cells.push({
            x_index: row.x_index,
            y_index: row.y_index,
            batch_index: row.representative_batch_index,
            category: row.category,
            width: row.width,
            height: row.height,
            blurhash: row.blurhash,
          });
        }
      }

      if (pageRows.length < PAGE_SIZE) {
        hasMore = false;
      } else {
        pageOffset += PAGE_SIZE;
      }
    }

    if (blurhash_cells.length === 0) {
      return Response.json({ error: "Run not found" }, { status: 404 });
    }

    const xColumnsRaw = runMeta.x_columns;
    const yIndexesRaw = runMeta.y_indexes;

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
      typeof runMeta.x_count === "number" ? runMeta.x_count : x_columns.length;
    const y_count =
      typeof runMeta.y_count === "number" ? runMeta.y_count : y_indexes.length;

    return Response.json({
      x_columns,
      y_indexes,
      x_count,
      y_count,
      cells: {},
      blurhash_cells,
    });
  } catch {
    return Response.json({ error: "Failed to load run grid" }, { status: 500 });
  }
}
