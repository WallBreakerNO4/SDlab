export type StylePromptFavorite = {
  id: string;
  prompt_key: string;
  prompt_text: string;
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

export const STYLE_PROMPT_MAX_LENGTH = 4000;

export function normalizeStylePromptText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function isStylePromptFavorite(value: unknown): value is StylePromptFavorite {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<StylePromptFavorite>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.prompt_key === "string" &&
    typeof candidate.prompt_text === "string" &&
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
