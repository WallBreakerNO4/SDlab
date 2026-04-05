import { isValidRunDir } from "@/lib/comfyui-types";
import { buildVisibleRunGridColumns } from "@/lib/run-grid-visibility";
import { getViewerShowNsfwPreference } from "@/lib/server-user-preferences";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import type {
  ImageCategory,
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
    const showNsfw = await getViewerShowNsfwPreference(supabase);
    const PAGE_SIZE = 1000;
    const runMetaResult = await supabase
      .from("runs")
      .select("x_columns,y_indexes,x_count,y_count")
      .eq("run_dir", runDir)
      .maybeSingle();

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

    const visibleColumns = buildVisibleRunGridColumns(runMeta.x_columns, {
      showNsfw,
    });

    const firstPageResult =
      visibleColumns.allowedOriginalXIndexes.length === 0
        ? { data: [] satisfies SupabaseRunGridCellRow[], error: null }
        : await supabase
            .from("run_grid_cells")
            .select(
              "x_index,y_index,representative_batch_index,category,width,height,blurhash",
            )
            .eq("run_dir", runDir)
            .in("x_index", visibleColumns.allowedOriginalXIndexes)
            .order("y_index", { ascending: true })
            .order("x_index", { ascending: true })
            .range(0, PAGE_SIZE - 1);

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
      const remappedXIndex = visibleColumns.remapOriginalXIndex(
        row.x_index ?? -1,
      );
      if (
        remappedXIndex !== null &&
        typeof row.y_index === "number" &&
        typeof row.representative_batch_index === "number" &&
        typeof row.category === "string"
      ) {
        blurhash_cells.push({
          x_index: remappedXIndex,
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
        .in("x_index", visibleColumns.allowedOriginalXIndexes)
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
        const remappedXIndex = visibleColumns.remapOriginalXIndex(
          row.x_index ?? -1,
        );
        if (
          remappedXIndex !== null &&
          typeof row.y_index === "number" &&
          typeof row.representative_batch_index === "number" &&
          typeof row.category === "string"
        ) {
          blurhash_cells.push({
            x_index: remappedXIndex,
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

    const yIndexesRaw = runMeta.y_indexes;

    const y_indexes: number[] = Array.isArray(yIndexesRaw)
      ? yIndexesRaw.filter(
          (item): item is number =>
            typeof item === "number" && Number.isFinite(item),
        )
      : [];

    const x_count = visibleColumns.columns.length;
    const y_count =
      typeof runMeta.y_count === "number" ? runMeta.y_count : y_indexes.length;

    return Response.json({
      x_columns: visibleColumns.columns,
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
