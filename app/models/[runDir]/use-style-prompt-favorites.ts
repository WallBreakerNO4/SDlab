"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  isStylePromptFavoriteListResponse,
  isStylePromptFavoriteResponse,
  normalizeStyleKey,
  normalizeStylePromptText,
  type StylePromptFavorite,
} from "@/lib/style-prompt-favorites";

type UseStylePromptFavoritesOptions = {
  runDir: string;
  currentUserId: string | null;
};

type FavoriteCreateOptions = {
  styleKey: string;
  label: string;
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
  const [pendingStyleKeys, setPendingStyleKeys] = useState<Set<string>>(
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
  const visiblePendingStyleKeys = useMemo(
    () => (currentUserId ? pendingStyleKeys : new Set<string>()),
    [currentUserId, pendingStyleKeys],
  );

  const favoriteByStyleKey = useMemo(() => {
    const map = new Map<string, StylePromptFavorite>();
    for (const favorite of visibleFavorites) {
      const key = normalizeStyleKey(favorite.style_key);
      if (key) {
        map.set(key, favorite);
      }
    }
    return map;
  }, [visibleFavorites]);

  const setStyleKeyPending = useCallback((styleKey: string, pending: boolean) => {
    const key = normalizeStyleKey(styleKey);
    if (!key) return;
    setPendingStyleKeys((current) => {
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
    async ({ styleKey, label, sourceYIndex }: FavoriteCreateOptions) => {
      const normalizedStyleKey = normalizeStyleKey(styleKey);
      const normalizedLabel = normalizeStylePromptText(label);
      if (!currentUserId || !normalizedStyleKey || !normalizedLabel) {
        throw new Error("Authentication required");
      }

      setStyleKeyPending(normalizedStyleKey, true);
      try {
        const response = await fetch("/api/viewer/style-prompt-favorites", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          cache: "no-store",
          body: JSON.stringify({
            style_key: normalizedStyleKey,
            label: normalizedLabel,
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
            (favorite) => favorite.style_key !== raw.favorite.style_key,
          );
          next.unshift(raw.favorite);
          return sortFavorites(next);
        });
        setFavoritesUserId(currentUserId);

        return raw.favorite;
      } finally {
        setStyleKeyPending(normalizedStyleKey, false);
      }
    },
    [currentUserId, runDir, setStyleKeyPending],
  );

  const deleteFavorite = useCallback(
    async (favorite: StylePromptFavorite) => {
      if (!currentUserId) {
        throw new Error("Authentication required");
      }

      setStyleKeyPending(favorite.style_key, true);
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
        setStyleKeyPending(favorite.style_key, false);
      }
    },
    [currentUserId, setStyleKeyPending],
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
    favoriteByStyleKey,
    isLoading: Boolean(currentUserId) && isLoading,
    pendingStyleKeys: visiblePendingStyleKeys,
    createFavorite,
    deleteFavorite,
    markFavoriteUsed,
  } as const;
}
