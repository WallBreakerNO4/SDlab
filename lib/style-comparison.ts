import { isStyleKey, type StyleKey } from "@/lib/style-favorites";

export const STYLE_COMPARISON_DEFAULT_LIMIT = 40;
export const STYLE_COMPARISON_MAX_LIMIT = 40;
export const STYLE_COMPARISON_MAX_STYLE_KEYS = 40;
export const STYLE_COMPARISON_MAX_RUN_DIRS = 12;

export type StyleComparisonCursor = {
  created_at: string;
  style_key: StyleKey;
};

export type StyleComparisonXDescription = {
  [locale: string]: string | null | undefined;
  zh?: string | null;
  en?: string | null;
};

export type StyleComparisonXColumn = {
  x_index: number;
  type: string | null;
  description: StyleComparisonXDescription | null;
};

export type StyleComparisonModel = {
  run_dir: string;
  name: string | null;
  created_at: string;
  x_columns: StyleComparisonXColumn[];
};

export type StyleComparisonFavorite = {
  style_key: StyleKey;
  label: string;
  created_at: string;
};

export type StyleComparisonResponse = {
  favorites: StyleComparisonFavorite[];
  models?: StyleComparisonModel[];
  next_cursor?: string | null;
};

export type StyleComparisonDetailResponse = {
  favorite: StyleComparisonFavorite;
  models: StyleComparisonModel[];
};

export type StyleComparisonSliceRequest = {
  style_keys: StyleKey[];
  run_dirs: string[];
};

export type StyleComparisonAccess = {
  run_dir: string;
  release_id: string;
  viewer_variant: "auth_sfw" | "auth_nsfw";
  grant: string;
  expires_at: number;
};

export type StyleComparisonPlacement = {
  run_dir: string;
  y_index: number;
};

export type StyleComparisonSliceResponse = {
  access: StyleComparisonAccess[];
  placements: Record<string, StyleComparisonPlacement[]>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isDescription(
  value: unknown,
): value is StyleComparisonXDescription | null {
  if (value === null) return true;
  if (!isRecord(value)) return false;
  return (
    (value.zh === undefined ||
      value.zh === null ||
      typeof value.zh === "string") &&
    (value.en === undefined ||
      value.en === null ||
      typeof value.en === "string")
  );
}

function isXColumn(value: unknown): value is StyleComparisonXColumn {
  return (
    isRecord(value) &&
    isNonNegativeInteger(value.x_index) &&
    (typeof value.type === "string" || value.type === null) &&
    isDescription(value.description)
  );
}

function isFavorite(value: unknown): value is StyleComparisonFavorite {
  return (
    isRecord(value) &&
    isStyleKey(value.style_key) &&
    typeof value.label === "string" &&
    typeof value.created_at === "string"
  );
}

function isModel(value: unknown): value is StyleComparisonModel {
  return (
    isRecord(value) &&
    typeof value.run_dir === "string" &&
    (typeof value.name === "string" || value.name === null) &&
    typeof value.created_at === "string" &&
    Array.isArray(value.x_columns) &&
    value.x_columns.every(isXColumn)
  );
}

export function isStyleComparisonResponse(
  value: unknown,
): value is StyleComparisonResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.favorites) &&
    value.favorites.every(isFavorite) &&
    (value.models === undefined ||
      (Array.isArray(value.models) && value.models.every(isModel))) &&
    (value.next_cursor === undefined ||
      typeof value.next_cursor === "string" ||
      value.next_cursor === null)
  );
}

export function isStyleComparisonSliceResponse(
  value: unknown,
): value is StyleComparisonSliceResponse {
  if (
    !isRecord(value) ||
    !Array.isArray(value.access) ||
    !isRecord(value.placements)
  )
    return false;
  const accessOk = value.access.every((item) => {
    return (
      isRecord(item) &&
      typeof item.run_dir === "string" &&
      typeof item.release_id === "string" &&
      (item.viewer_variant === "auth_sfw" ||
        item.viewer_variant === "auth_nsfw") &&
      typeof item.grant === "string" &&
      typeof item.expires_at === "number" &&
      Number.isFinite(item.expires_at)
    );
  });
  if (!accessOk) return false;
  return Object.values(value.placements).every(
    (placements) =>
      Array.isArray(placements) &&
      placements.every(
        (item) =>
          isRecord(item) &&
          typeof item.run_dir === "string" &&
          isNonNegativeInteger(item.y_index),
      ),
  );
}

export function isStyleComparisonDetailResponse(
  value: unknown,
): value is StyleComparisonDetailResponse {
  return (
    isRecord(value) &&
    isFavorite(value.favorite) &&
    Array.isArray(value.models) &&
    value.models.every(isModel)
  );
}

export function parseStyleComparisonLimit(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return STYLE_COMPARISON_DEFAULT_LIMIT;
  if (!/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < 1) return null;
  return Math.min(value, STYLE_COMPARISON_MAX_LIMIT);
}

function encodeBase64Url(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function decodeBase64Url(value: string): string | null {
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(
      `${normalized}${"=".repeat((4 - (normalized.length % 4)) % 4)}`,
    );
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

export function encodeStyleComparisonCursor(
  cursor: StyleComparisonCursor,
): string {
  return encodeBase64Url(JSON.stringify(cursor));
}

export function decodeStyleComparisonCursor(
  value: string | null,
): StyleComparisonCursor | null {
  if (!value) return null;
  const decoded = decodeBase64Url(value);
  if (!decoded) return null;
  try {
    const parsed: unknown = JSON.parse(decoded);
    if (
      !isRecord(parsed) ||
      typeof parsed.created_at !== "string" ||
      !isStyleKey(parsed.style_key)
    )
      return null;
    return { created_at: parsed.created_at, style_key: parsed.style_key };
  } catch {
    return null;
  }
}

export function parseStyleComparisonSliceBody(
  value: unknown,
): StyleComparisonSliceRequest | null {
  if (
    !isRecord(value) ||
    !Array.isArray(value.style_keys) ||
    !Array.isArray(value.run_dirs)
  )
    return null;
  if (
    value.style_keys.length < 1 ||
    value.style_keys.length > STYLE_COMPARISON_MAX_STYLE_KEYS
  )
    return null;
  if (
    value.run_dirs.length < 1 ||
    value.run_dirs.length > STYLE_COMPARISON_MAX_RUN_DIRS
  )
    return null;
  if (!value.style_keys.every(isStyleKey)) return null;
  if (
    !value.run_dirs.every(
      (runDir) =>
        typeof runDir === "string" && runDir.length > 0 && runDir.length <= 200,
    )
  )
    return null;
  return {
    style_keys: [...new Set(value.style_keys)],
    run_dirs: [...new Set(value.run_dirs)],
  };
}

export function readViewerVariantFromCookie(
  cookieHeader: string | null,
): "auth_sfw" | "auth_nsfw" {
  const cookieValue = cookieHeader
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("sdslab_show_nsfw="))
    ?.slice("sdslab_show_nsfw=".length);
  return cookieValue === "1" ? "auth_nsfw" : "auth_sfw";
}

export function buildPrivateObjectCacheUrl(requestUrl: string): string {
  const url = new URL(requestUrl);
  const key = url.searchParams.get("key");
  url.search = "";
  if (key) url.searchParams.set("key", key);
  return url.toString();
}

export async function fetchStyleComparison(
  cursor?: string,
): Promise<StyleComparisonResponse | null> {
  try {
    const url = new URL("/api/viewer/style-comparison", window.location.origin);
    if (cursor) url.searchParams.set("cursor", cursor);
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    const payload: unknown = await response.json();
    return isStyleComparisonResponse(payload) ? payload : null;
  } catch {
    return null;
  }
}

export async function fetchStyleComparisonSlice(
  body: StyleComparisonSliceRequest,
): Promise<StyleComparisonSliceResponse | null> {
  try {
    const response = await fetch("/api/viewer/style-comparison/slice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(body),
    });
    if (!response.ok) return null;
    const payload: unknown = await response.json();
    return isStyleComparisonSliceResponse(payload) ? payload : null;
  } catch {
    return null;
  }
}

// Client comparison helpers are kept alongside the response guards so pages
// and tests share the same row ordering/visibility rules.
export type ComparisonModel = StyleComparisonModel;
export type ComparisonFavorite = StyleComparisonFavorite;
export type ComparisonSlice = StyleComparisonSliceResponse;
export type ComparisonCatalogPage = StyleComparisonResponse;

import type {
  RowCell,
  RowItem,
  RowPayload,
} from "@/components/comfyui/virtual-grid-types";

export type ComparisonSlide = {
  xIndex: number;
  batchIndex: number;
  item: RowItem;
  cell: RowCell;
};

export function mergeComparisonFavorites(
  pages: ComparisonCatalogPage[],
): ComparisonFavorite[] {
  const seen = new Set<string>();
  const result: ComparisonFavorite[] = [];
  for (const page of pages)
    for (const favorite of page.favorites) {
      if (seen.has(favorite.style_key)) continue;
      seen.add(favorite.style_key);
      result.push(favorite);
    }
  return result;
}

export function getVisibleModels(
  models: ComparisonModel[],
  hiddenRunDirs: ReadonlySet<string>,
): ComparisonModel[] {
  return models.filter((model) => !hiddenRunDirs.has(model.run_dir));
}

export function reconcileHiddenRunDirs(
  hiddenRunDirs: ReadonlySet<string>,
  models: ComparisonModel[],
): Set<string> {
  const available = new Set(models.map((model) => model.run_dir));
  return new Set([...hiddenRunDirs].filter((runDir) => available.has(runDir)));
}

export function flattenRowSlides(row: RowPayload | null): ComparisonSlide[] {
  if (!row) return [];
  return row.cells
    .slice()
    .sort((a, b) => a.x_index - b.x_index)
    .flatMap((cell) =>
      cell.items
        .slice()
        .sort((a, b) => a.batch_index - b.batch_index)
        .map((item) => ({
          xIndex: cell.x_index,
          batchIndex: item.batch_index,
          item,
          cell,
        })),
    );
}
