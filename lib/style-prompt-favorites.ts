export type StylePromptFavorite = {
  id: string;
  style_key: string;
  label: string;
  source_run_dir: string | null;
  source_y_index: number | null;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
};

export type StylePromptFavoriteListResponse = {
  favorites: StylePromptFavorite[];
};

export type StylePromptFavoriteResponse = {
  favorite: StylePromptFavorite;
};

export type YPromptRef = {
  y_index: number;
  style_key: string;
  collection_id: string;
  item_index: number;
  label: string;
  source_y_path?: string;
  source_y_sha256?: string;
};

export const STYLE_PROMPT_LABEL_MAX_LENGTH = 4000;
export const STYLE_PROMPT_KEY_MAX_LENGTH = 512;

export function normalizeStylePromptText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function normalizeStyleKey(value: string): string {
  return value.trim();
}

export function isYPromptRef(value: unknown): value is YPromptRef {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<YPromptRef>;
  return (
    typeof candidate.y_index === "number" &&
    Number.isInteger(candidate.y_index) &&
    candidate.y_index >= 0 &&
    typeof candidate.style_key === "string" &&
    typeof candidate.collection_id === "string" &&
    typeof candidate.item_index === "number" &&
    Number.isInteger(candidate.item_index) &&
    candidate.item_index >= 0 &&
    typeof candidate.label === "string" &&
    (candidate.source_y_path === undefined ||
      typeof candidate.source_y_path === "string") &&
    (candidate.source_y_sha256 === undefined ||
      typeof candidate.source_y_sha256 === "string")
  );
}

export function isStylePromptFavorite(value: unknown): value is StylePromptFavorite {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<StylePromptFavorite>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.style_key === "string" &&
    typeof candidate.label === "string" &&
    (typeof candidate.source_run_dir === "string" ||
      candidate.source_run_dir === null) &&
    (typeof candidate.source_y_index === "number" ||
      candidate.source_y_index === null) &&
    typeof candidate.created_at === "string" &&
    typeof candidate.updated_at === "string" &&
    (typeof candidate.last_used_at === "string" ||
      candidate.last_used_at === null)
  );
}

export function isStylePromptFavoriteListResponse(
  value: unknown,
): value is StylePromptFavoriteListResponse {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<StylePromptFavoriteListResponse>;
  return (
    Array.isArray(candidate.favorites) &&
    candidate.favorites.every(isStylePromptFavorite)
  );
}

export function isStylePromptFavoriteResponse(
  value: unknown,
): value is StylePromptFavoriteResponse {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  return isStylePromptFavorite(
    (value as Partial<StylePromptFavoriteResponse>).favorite,
  );
}
