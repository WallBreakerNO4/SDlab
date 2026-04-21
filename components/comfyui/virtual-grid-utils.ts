import type {
  CachedRow,
  ImageVariantSource,
  RowCell,
  RowItem,
  RowMeta,
  RowPayload,
  RunGridXColumn,
  SavedScrollAnchor,
  VariantSources,
} from "./virtual-grid-types";

const SCROLL_ANCHOR_STORAGE_VERSION = 1 as const;
const SCROLL_ANCHOR_STORAGE_PREFIX = "sd-style-lab:model-grid-anchor:";
const MAX_ROW_OFFSET_RATIO = 0.999999;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function getNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function getFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function parseLineNumberFromHash(
  rawHash: string,
  maxLineNumber: number,
): number | null {
  if (typeof rawHash !== "string" || maxLineNumber < 1) {
    return null;
  }

  const rawValue = rawHash.startsWith("#") ? rawHash.slice(1) : rawHash;
  if (rawValue.length === 0) {
    return null;
  }

  try {
    const decodedValue = decodeURIComponent(rawValue).trim();
    if (!/^\d+$/.test(decodedValue)) {
      return null;
    }

    const lineNumber = Number(decodedValue);
    if (
      !Number.isSafeInteger(lineNumber) ||
      lineNumber < 1 ||
      lineNumber > maxLineNumber
    ) {
      return null;
    }

    return lineNumber;
  } catch {
    return null;
  }
}

function getScrollAnchorStorageKey(runDir: string): string {
  return `${SCROLL_ANCHOR_STORAGE_PREFIX}${runDir}`;
}

function parseSavedScrollAnchor(raw: string | null): SavedScrollAnchor | null {
  if (!raw) return null;

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) return null;
    const version = getFiniteNumber(parsed.version);
    const yIndex = getFiniteNumber(parsed.yIndex);
    const rowOffsetRatio = getFiniteNumber(parsed.rowOffsetRatio);
    if (
      version !== SCROLL_ANCHOR_STORAGE_VERSION ||
      yIndex === null ||
      yIndex < 0 ||
      rowOffsetRatio === null
    ) {
      return null;
    }

    return {
      version: SCROLL_ANCHOR_STORAGE_VERSION,
      yIndex,
      rowOffsetRatio: clampNumber(rowOffsetRatio, 0, MAX_ROW_OFFSET_RATIO),
    };
  } catch {
    return null;
  }
}

export function loadSavedScrollAnchor(
  runDir: string,
): SavedScrollAnchor | null {
  if (typeof window === "undefined" || runDir.trim().length === 0) {
    return null;
  }

  try {
    return parseSavedScrollAnchor(
      window.localStorage.getItem(getScrollAnchorStorageKey(runDir)),
    );
  } catch {
    return null;
  }
}

export function saveScrollAnchor(
  runDir: string,
  anchor: SavedScrollAnchor,
): void {
  if (typeof window === "undefined" || runDir.trim().length === 0) {
    return;
  }

  try {
    window.localStorage.setItem(
      getScrollAnchorStorageKey(runDir),
      JSON.stringify(anchor),
    );
  } catch {
    // Ignore storage failures (private mode / quota / disabled storage).
  }
}

export function buildScrollAnchor(
  scrollOffset: number,
  yIndexes: number[],
  rowHeight: number,
): SavedScrollAnchor | null {
  if (
    !Number.isFinite(scrollOffset) ||
    !Number.isFinite(rowHeight) ||
    rowHeight <= 0 ||
    yIndexes.length === 0
  ) {
    return null;
  }

  const listIndex = clampNumber(
    Math.floor(scrollOffset / rowHeight),
    0,
    yIndexes.length - 1,
  );
  const yIndex = yIndexes[listIndex];
  if (typeof yIndex !== "number" || !Number.isFinite(yIndex) || yIndex < 0) {
    return null;
  }

  const rowOffsetRatio = clampNumber(
    (scrollOffset - listIndex * rowHeight) / rowHeight,
    0,
    MAX_ROW_OFFSET_RATIO,
  );

  return {
    version: SCROLL_ANCHOR_STORAGE_VERSION,
    yIndex,
    rowOffsetRatio,
  };
}

export function resolveScrollOffsetFromAnchor(
  anchor: SavedScrollAnchor,
  yIndexes: number[],
  rowHeight: number,
): number | null {
  if (!Number.isFinite(rowHeight) || rowHeight <= 0 || yIndexes.length === 0) {
    return null;
  }

  let listIndex = yIndexes.indexOf(anchor.yIndex);
  if (listIndex < 0) {
    const nextIndex = yIndexes.findIndex((value) => value > anchor.yIndex);
    listIndex =
      nextIndex === -1 ? yIndexes.length - 1 : Math.max(0, nextIndex - 1);
  }

  return listIndex * rowHeight + anchor.rowOffsetRatio * rowHeight;
}

function getSeedString(value: unknown): string | null {
  if (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Number.isInteger(value)
  ) {
    return String(value);
  }
  return getNonEmptyString(value);
}

export function getXLabel(column: RunGridXColumn | null | undefined): string {
  const raw = column?.description;
  const zh =
    raw && typeof raw.zh === "string" ? getNonEmptyString(raw.zh) : null;
  return zh ?? "";
}

export function pickBestVariants(
  primary: VariantSources | null,
  fallback: VariantSources | null,
): VariantSources | null {
  const candidate = primary ?? fallback;
  if (!candidate) return null;
  const hasWebp = isImageVariantSource(candidate.webp);
  const hasAvif = isImageVariantSource(candidate.avif);
  if (!hasWebp && !hasAvif) return null;
  return {
    webp: hasWebp ? candidate.webp : undefined,
    avif: hasAvif ? candidate.avif : undefined,
  };
}

export function getPreferredVariantCacheKey(
  variants: VariantSources | null | undefined,
): string | null {
  if (isImageVariantSource(variants?.webp)) {
    return variants.webp.cache_key;
  }
  if (isImageVariantSource(variants?.avif)) {
    return variants.avif.cache_key;
  }
  return null;
}

export function getPreferredVariantSource(
  variants: VariantSources | null | undefined,
): ImageVariantSource | null {
  if (isImageVariantSource(variants?.webp)) {
    return variants.webp;
  }
  if (isImageVariantSource(variants?.avif)) {
    return variants.avif;
  }
  return null;
}

export function getPreferredAspectRatioFromCache(
  rows: Iterable<CachedRow>,
): number {
  for (const row of rows) {
    if (row.status !== "ready") continue;
    for (const cell of row.cellsByX.values()) {
      for (const item of cell.items) {
        const width = item.width;
        const height = item.height;
        if (
          typeof width === "number" &&
          typeof height === "number" &&
          Number.isFinite(width) &&
          Number.isFinite(height) &&
          width > 0 &&
          height > 0
        ) {
          return height / width;
        }
      }
    }
  }
  return 1;
}

function isImageVariantSource(value: unknown): value is ImageVariantSource {
  return (
    isRecord(value) &&
    (value.bucket === "public" || value.bucket === "private") &&
    getNonEmptyString(value.cache_key) !== null &&
    getNonEmptyString(value.key) !== null
  );
}

function parseImageVariantSource(value: unknown): ImageVariantSource | null {
  if (!isRecord(value)) return null;
  const bucket = value.bucket;
  const cacheKey = getNonEmptyString(value.cache_key);
  const key = getNonEmptyString(value.key);
  if (
    (bucket !== "public" && bucket !== "private") ||
    cacheKey === null ||
    key === null
  ) {
    return null;
  }
  return {
    bucket,
    cache_key: cacheKey,
    key,
  };
}

function parseVariantSources(value: unknown): VariantSources | null {
  if (!isRecord(value)) return null;
  const webp = parseImageVariantSource(value.webp);
  const avif = parseImageVariantSource(value.avif);
  if (!webp && !avif) return null;
  return {
    webp: webp ?? undefined,
    avif: avif ?? undefined,
  };
}

function parseRowMeta(value: unknown): RowMeta {
  if (!isRecord(value)) {
    return {
      seed: null,
      prompt_id: null,
      prompt_hash: null,
      positive_prompt: null,
      y_value: null,
    };
  }

  return {
    seed: getSeedString(value.seed),
    prompt_id: getFiniteNumber(value.prompt_id),
    prompt_hash: getNonEmptyString(value.prompt_hash),
    positive_prompt: getNonEmptyString(value.positive_prompt),
    y_value: getNonEmptyString(value.y_value),
  };
}

export function normalizeRowPayload(
  raw: unknown,
  requestedYIndex: number,
): RowPayload | null {
  if (!isRecord(raw)) return null;

  const rawCells = raw.cells;
  const cells: RowCell[] = Array.isArray(rawCells)
    ? rawCells
        .map((cell) => {
          if (!isRecord(cell)) return null;
          const xIndex = getFiniteNumber(cell.x_index);
          const yIndex = getFiniteNumber(cell.y_index);
          if (xIndex === null || yIndex === null) return null;
          const itemsRaw = cell.items;
          const items: RowItem[] = Array.isArray(itemsRaw)
            ? itemsRaw
                .map((item) => {
                  if (!isRecord(item)) return null;
                  const batchIndex = getFiniteNumber(item.batch_index);
                  if (batchIndex === null) return null;
                  const meta = parseRowMeta(item.meta);
                  const thumb = parseVariantSources(item.thumb);
                  const display = parseVariantSources(item.display);
                  if (!thumb && !display) return null;
                  return {
                    batch_index: batchIndex,
                    category: getNonEmptyString(item.category),
                    width: getFiniteNumber(item.width),
                    height: getFiniteNumber(item.height),
                    blurhash: getNonEmptyString(item.blurhash),
                    meta,
                    thumb,
                    display,
                  };
                })
                .filter((value): value is RowItem => value !== null)
            : [];

          items.sort((a, b) => a.batch_index - b.batch_index);
          return { x_index: xIndex, y_index: yIndex, items };
        })
        .filter((value): value is RowCell => value !== null)
    : [];

  const yIndexValue = getFiniteNumber(raw.y_index) ?? requestedYIndex;
  const runDir = getNonEmptyString(raw.run_dir) ?? "";

  return {
    run_dir: runDir,
    y_index: yIndexValue,
    cells,
  };
}

export function formatValue(
  value: string | number | null | undefined,
): string {
  return value === null || value === undefined || value === ""
    ? "-"
    : String(value);
}

export function parseDialogImagePayload(raw: unknown): VariantSources | null {
  if (!isRecord(raw) || !("image" in raw)) {
    return null;
  }

  return parseVariantSources(raw.image);
}
