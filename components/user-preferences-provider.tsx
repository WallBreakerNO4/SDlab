"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useAuth } from "@/components/auth-provider";

type UserPreferencesContextValue = {
  showNsfw: boolean;
  setShowNsfw: (value: boolean) => Promise<void>;
};

const UserPreferencesContext =
  createContext<UserPreferencesContextValue | null>(null);

export function useUserPreferences() {
  const ctx = useContext(UserPreferencesContext);
  if (!ctx) {
    throw new Error(
      "useUserPreferences must be used within <UserPreferencesProvider>",
    );
  }
  return ctx;
}

export function UserPreferencesProvider({
  children,
  initialShowNsfw,
}: {
  children: React.ReactNode;
  initialShowNsfw: boolean;
}) {
  const { user } = useAuth();
  const [showNsfw, setShowNsfwState] = useState(initialShowNsfw);
  const effectiveShowNsfw = user ? showNsfw : false;

  const setShowNsfw = useCallback(
    async (value: boolean) => {
      if (!user) {
        return;
      }

      const res = await fetch("/api/viewer/preferences/nsfw", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ show_nsfw: value }),
      });

      if (!res.ok) {
        throw new Error("Failed to update NSFW preference");
      }

      setShowNsfwState(value);
    },
    [user],
  );

  useEffect(() => {
    const abortController = new AbortController();

    if (user) {
      void fetch("/api/viewer/preferences/nsfw", {
        cache: "no-store",
        signal: abortController.signal,
      })
        .then((res) => res.json())
        .then((data) => {
          if (abortController.signal.aborted) {
            return;
          }
          if (typeof data.show_nsfw === "boolean") {
            setShowNsfwState(data.show_nsfw);
          }
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") {
            return;
          }
          setShowNsfwState(false);
        });
    }

    return () => {
      abortController.abort();
    };
  }, [user]);

  const value = useMemo(
    () => ({ showNsfw: effectiveShowNsfw, setShowNsfw }),
    [effectiveShowNsfw, setShowNsfw],
  );

  return (
    <UserPreferencesContext value={value}>{children}</UserPreferencesContext>
  );
}
