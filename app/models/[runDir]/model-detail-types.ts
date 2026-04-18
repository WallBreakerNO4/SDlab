import type {
  RunGridIndexData,
  RunGridXColumn,
} from "@/components/comfyui/virtual-grid";

export type ModelDetailSummary = {
  run_id: string;
  created_at: string;
  run_dir: string;
  selection: {
    total_cells: number;
  };
  model?: {
    name?: string | null;
    description?: {
      zh?: string | null;
      en?: string | null;
    } | null;
    links?: {
      homepage?: string | null;
      huggingface?: string | null;
      civitai?: string | null;
    } | null;
  } | null;
  workflow?: {
    sha256?: string | null;
    download_url?: string | null;
  } | null;
};

export type ModelDetailResponse = {
  run: ModelDetailSummary;
  xLabels: string[];
  yLabels: string[];
  x_columns: RunGridXColumn[];
  y_indexes: number[];
};

export type LoadState = "loading" | "ready" | "not-found" | "error";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function isModelDetailResponse(
  value: unknown,
): value is ModelDetailResponse {
  if (!isRecord(value)) {
    return false;
  }

  if (!isStringArray(value.xLabels) || !isStringArray(value.yLabels)) {
    return false;
  }

  if (!Array.isArray(value.x_columns) || !Array.isArray(value.y_indexes)) {
    return false;
  }

  if (!isRecord(value.run) || !isRecord(value.run.selection)) {
    return false;
  }

  const run = value.run;
  const selection = run.selection as Record<string, unknown>;

  return (
    typeof run.run_id === "string" &&
    typeof run.created_at === "string" &&
    typeof run.run_dir === "string" &&
    typeof selection.total_cells === "number"
  );
}

export function isRunGridIndexData(value: unknown): value is RunGridIndexData {
  if (!isRecord(value)) {
    return false;
  }

  if (!Array.isArray(value.x_columns) || !Array.isArray(value.y_indexes)) {
    return false;
  }

  const x_columns = value.x_columns as unknown[];
  const xColumnsOk = x_columns.every((col) => {
    if (!isRecord(col)) return false;
    const type = col.type;
    const typeOk = typeof type === "string" || type === null;
    const desc = col.description;
    const descOk = desc === null || isRecord(desc);
    return typeOk && descOk;
  });

  const y_indexes = value.y_indexes as unknown[];
  const yIndexesOk = y_indexes.every(
    (item) => typeof item === "number" && Number.isFinite(item) && item >= 0,
  );
  const yLabelsOk =
    value.y_labels === undefined || isStringArray(value.y_labels);

  const hasBlurhashCells = Array.isArray(value.blurhash_cells);

  return (
    xColumnsOk &&
    yIndexesOk &&
    yLabelsOk &&
    (hasBlurhashCells || !value.blurhash_cells)
  );
}
