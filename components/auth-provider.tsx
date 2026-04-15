"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { User } from "@supabase/supabase-js";
import { toast } from "sonner";
import { createSupabaseBrowserClient } from "@/lib/supabase-browser";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  signInWithGitHub: () => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signInWithMicrosoft: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const AUTH_ERROR_QUERY_PARAM = "auth_error";

function getAuthErrorMessage(code: string | null): string {
  switch (code) {
    case "auth_not_configured":
      return "当前环境尚未配置登录功能。";
    case "oauth_cancelled":
      return "登录已取消，你可以在准备好后重新尝试。";
    case "oauth_callback_failed":
      return "登录未完成，请重新尝试。";
    case "oauth_start_failed":
      return "登录启动失败，请稍后重试。";
    default:
      return "登录失败，请稍后重试。";
  }
}

function buildAuthCallbackUrl(): string {
  const currentUrl = new URL(window.location.href);
  currentUrl.searchParams.delete(AUTH_ERROR_QUERY_PARAM);

  const nextPath =
    currentUrl.pathname === "/auth/callback"
      ? "/"
      : `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}` || "/";

  const redirectUrl = new URL("/auth/callback", window.location.origin);
  if (nextPath !== "/") {
    redirectUrl.searchParams.set("next", nextPath);
  }

  return redirectUrl.toString();
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within <AuthProvider>");
  }
  return ctx;
}

export function AuthProvider({
  children,
  initialUser,
}: {
  children: React.ReactNode;
  initialUser?: User | null;
}) {
  const supabase = useMemo(() => {
    try {
      return createSupabaseBrowserClient();
    } catch {
      // Supabase env vars not configured — auth disabled
      return null;
    }
  }, []);

  const [user, setUser] = useState<User | null>(initialUser ?? null);
  const [loading, setLoading] = useState(
    initialUser === undefined && !!supabase,
  );

  useEffect(() => {
    const currentUrl = new URL(window.location.href);
    const authError = currentUrl.searchParams.get(AUTH_ERROR_QUERY_PARAM);

    if (!authError) {
      return;
    }

    toast.error(getAuthErrorMessage(authError));
    currentUrl.searchParams.delete(AUTH_ERROR_QUERY_PARAM);
    window.history.replaceState(
      window.history.state,
      "",
      `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`,
    );
  }, []);

  useEffect(() => {
    if (!supabase) {
      return;
    }

    if (initialUser === undefined) {
      void supabase.auth
        .getUser()
        .then(({ data }) => {
          setUser(data.user ?? null);
        })
        .catch(() => {
          setUser(null);
        })
        .finally(() => {
          setLoading(false);
        });
    }

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "INITIAL_SESSION" && initialUser !== undefined) {
        return;
      }
      setUser(session?.user ?? null);
      setLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [supabase, initialUser]);

  const signInWithOAuth = useCallback(
    async (
      provider: "github" | "google" | "azure",
      providerLabel: string,
      scopes?: string,
    ) => {
      if (!supabase) {
        toast.error(getAuthErrorMessage("auth_not_configured"));
        return;
      }

      const { error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: buildAuthCallbackUrl(),
          ...(scopes ? { scopes } : {}),
        },
      });

      if (error) {
        console.error(
          `[auth] Failed to start ${providerLabel} OAuth:`,
          error.message,
        );
        toast.error(`${providerLabel} 登录启动失败，请稍后重试。`);
      }
    },
    [supabase],
  );

  const signInWithGitHub = useCallback(async () => {
    await signInWithOAuth("github", "GitHub");
  }, [signInWithOAuth]);

  const signInWithGoogle = useCallback(async () => {
    await signInWithOAuth("google", "Google");
  }, [signInWithOAuth]);

  const signInWithMicrosoft = useCallback(async () => {
    await signInWithOAuth("azure", "Microsoft", "email");
  }, [signInWithOAuth]);

  const signOut = useCallback(async () => {
    if (!supabase) {
      toast.error("当前环境尚未配置登录功能。");
      return;
    }

    const { error } = await supabase.auth.signOut();
    if (error) {
      console.error("[auth] Failed to sign out:", error.message);
      toast.error("退出登录失败，请稍后重试。");
      return;
    }

    setUser(null);
  }, [supabase]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      signInWithGitHub,
      signInWithGoogle,
      signInWithMicrosoft,
      signOut,
    }),
    [
      user,
      loading,
      signInWithGitHub,
      signInWithGoogle,
      signInWithMicrosoft,
      signOut,
    ],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
