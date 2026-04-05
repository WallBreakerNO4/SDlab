import type { JsonObject, JsonValue } from "@/lib/supabase-types";

export type VisibleRunGridXColumn = {
  type: string | null;
  description: JsonObject | null;
};

type ParsedRunGridXColumn = VisibleRunGridXColumn & {
  originalIndex: number;
};

export type VisibleRunGridColumns = {
  columns: VisibleRunGridXColumn[];
  allowedOriginalXIndexes: number[];
  remapOriginalXIndex: (originalXIndex: number) => number | null;
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

function parseRunGridXColumn(
  rawColumn: JsonValue,
  originalIndex: number,
): ParsedRunGridXColumn | null {
  const column = asJsonObject(rawColumn);
  if (!column) {
    return null;
  }

  return {
    originalIndex,
    type: getNonEmptyString(column.type),
    description: asJsonObject(column.description as JsonValue),
  };
}

export function buildVisibleRunGridColumns(
  rawColumns: JsonValue[] | null | undefined,
  options: {
    showNsfw: boolean;
  },
): VisibleRunGridColumns {
  const { showNsfw } = options;
  const parsedColumns = Array.isArray(rawColumns)
    ? rawColumns
        .map((rawColumn, originalIndex) =>
          parseRunGridXColumn(rawColumn as JsonValue, originalIndex),
        )
        .filter((column): column is ParsedRunGridXColumn => column !== null)
    : [];

  const remappedIndexes = new Map<number, number>();
  const columns: VisibleRunGridXColumn[] = [];

  for (const column of parsedColumns) {
    if (!showNsfw && column.type === "nsfw") {
      continue;
    }

    remappedIndexes.set(column.originalIndex, columns.length);
    columns.push({
      type: column.type,
      description: column.description,
    });
  }

  return {
    columns,
    allowedOriginalXIndexes: Array.from(remappedIndexes.keys()),
    remapOriginalXIndex(originalXIndex: number) {
      return remappedIndexes.get(originalXIndex) ?? null;
    },
  };
}
