"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  isStylePromptFavoriteListResponse,
  isStylePromptFavoriteResponse,
  normalizeStylePromptText,
  type StylePromptFavorite,
} from "@/lib/style-prompt-favorites";

type UseStylePromptFavoritesOptions = {
  runDir: string;
  currentUserId: string | null;
};

type FavoriteCreateOptions = {
  promptText: string;
  sourceYIndex: number | null;
};

function sortFavorites(favorites: StylePromptFavorite[]): StylePromptFavorite[] {
  return [...favorites].sort((a, b) => {
    const aTime = a.last_used_at ?? a.created_at;
    const bTime = b.last_used_at ?? b.created_at;
    return bTime.localeCompare(aTime);
  });
}

export function useStylePromptFavorites({
  runDir,
  currentUserId,
}: UseStylePromptFavoritesOptions) {
  const [favorites, setFavorites] = useState<StylePromptFavorite[]>([]);
  const [favoritesUserId, setFavoritesUserId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [shouldLoad, setShouldLoad] = useState(false);
  const [pendingPromptKeys, setPendingPromptKeys] = useState<Set<string>>(
    () => new Set(),
  );
  const deferTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!currentUserId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset deferred state on logout
      setShouldLoad(false);
      return () => {
        if (deferTimerRef.current !== null) {
          clearTimeout(deferTimerRef.current);
          deferTimerRef.current = null;
        }
      };
    }

    deferTimerRef.current = setTimeout(() => {
      setShouldLoad(true);
    }, 500);

    return () => {
      if (deferTimerRef.current !== null) {
        clearTimeout(deferTimerRef.current);
        deferTimerRef.current = null;
      }
    };
  }, [currentUserId]);

  useEffect(() => {
    const abortController = new AbortController();

    if (!currentUserId || !shouldLoad) {
      return () => abortController.abort();
    }

    async function fetchFavorites() {
      setIsLoading(true);
      const response = await fetch("/api/viewer/style-prompt-favorites", {
        signal: abortController.signal,
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error("Failed to load style prompt favorites");
      }

      const raw: unknown = await response.json();
      if (!isStylePromptFavoriteListResponse(raw)) {
        throw new Error("Invalid style prompt favorite payload");
      }

      if (!abortController.signal.aborted) {
        setFavoritesUserId(currentUserId);
        setFavorites(sortFavorites(raw.favorites));
      }
    }

    void fetchFavorites()
      .catch((error: unknown) => {
        if (abortController.signal.aborted) return;
        console.error("[style-prompt-favorites] Failed to load", error);
        setFavoritesUserId(currentUserId);
        setFavorites([]);
      })
      .finally(() => {
        if (!abortController.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => abortController.abort();
  }, [currentUserId, shouldLoad]);

  const visibleFavorites = useMemo(
    () => (favoritesUserId === currentUserId ? favorites : []),
    [currentUserId, favorites, favoritesUserId],
  );
  const visiblePendingPromptKeys = useMemo(
    () => (currentUserId ? pendingPromptKeys : new Set<string>()),
    [currentUserId, pendingPromptKeys],
  );

  const favoriteByPrompt = useMemo(() => {
    const map = new Map<string, StylePromptFavorite>();
    for (const favorite of visibleFavorites) {
      const key = normalizeStylePromptText(favorite.prompt_text);
      if (key) {
        map.set(key, favorite);
      }
    }
    return map;
  }, [visibleFavorites]);

  const setPromptPending = useCallback((promptText: string, pending: boolean) => {
    const key = normalizeStylePromptText(promptText);
    if (!key) return;
    setPendingPromptKeys((current) => {
      const next = new Set(current);
      if (pending) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  }, []);

  const createFavorite = useCallback(
    async ({ promptText, sourceYIndex }: FavoriteCreateOptions) => {
      const normalizedPrompt = normalizeStylePromptText(promptText);
      if (!currentUserId || !normalizedPrompt) {
        throw new Error("Authentication required");
      }

      setPromptPending(normalizedPrompt, true);
      try {
        const response = await fetch("/api/viewer/style-prompt-favorites", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          cache: "no-store",
          body: JSON.stringify({
            prompt_text: normalizedPrompt,
            source_run_dir: runDir,
            source_y_index: sourceYIndex,
          }),
        });

        if (!response.ok) {
          throw new Error("Failed to save style prompt favorite");
        }

        const raw: unknown = await response.json();
        if (!isStylePromptFavoriteResponse(raw)) {
          throw new Error("Invalid style prompt favorite payload");
        }

        setFavorites((current) => {
          const next = current.filter(
            (favorite) => favorite.prompt_key !== raw.favorite.prompt_key,
          );
          next.unshift(raw.favorite);
          return sortFavorites(next);
        });
        setFavoritesUserId(currentUserId);

        return raw.favorite;
      } finally {
        setPromptPending(normalizedPrompt, false);
      }
    },
    [currentUserId, runDir, setPromptPending],
  );

  const deleteFavorite = useCallback(
    async (favorite: StylePromptFavorite) => {
      if (!currentUserId) {
        throw new Error("Authentication required");
      }

      setPromptPending(favorite.prompt_text, true);
      try {
        const response = await fetch(
          `/api/viewer/style-prompt-favorites/${encodeURIComponent(favorite.id)}`,
          {
            method: "DELETE",
            cache: "no-store",
          },
        );

        if (!response.ok) {
          throw new Error("Failed to delete style prompt favorite");
        }

        setFavorites((current) =>
          current.filter((item) => item.id !== favorite.id),
        );
      } finally {
        setPromptPending(favorite.prompt_text, false);
      }
    },
    [currentUserId, setPromptPending],
  );

  const markFavoriteUsed = useCallback(
    async (favorite: StylePromptFavorite) => {
      if (!currentUserId) return;

      const now = new Date().toISOString();
      setFavorites((current) =>
        sortFavorites(
          current.map((item) =>
            item.id === favorite.id
              ? { ...item, last_used_at: now, updated_at: now }
              : item,
          ),
        ),
      );

      const response = await fetch(
        `/api/viewer/style-prompt-favorites/${encodeURIComponent(favorite.id)}`,
        {
          method: "PATCH",
          cache: "no-store",
        },
      );

      if (!response.ok) {
        throw new Error("Failed to update style prompt favorite");
      }
    },
    [currentUserId],
  );

  return {
    favorites: visibleFavorites,
    favoriteByPrompt,
    isLoading: Boolean(currentUserId) && isLoading,
    pendingPromptKeys: visiblePendingPromptKeys,
    createFavorite,
    deleteFavorite,
    markFavoriteUsed,
  } as const;
}
