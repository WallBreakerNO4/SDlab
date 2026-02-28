"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"
import type { User } from "@supabase/supabase-js"
import { createSupabaseBrowserClient } from "@/lib/supabase-browser"

type AuthContextValue = {
  user: User | null
  loading: boolean
  signInWithGitHub: () => Promise<void>
  signInWithGoogle: () => Promise<void>
  signInWithMicrosoft: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error("useAuth must be used within <AuthProvider>")
  }
  return ctx
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const supabase = useMemo(() => {
    try {
      return createSupabaseBrowserClient()
    } catch {
      // Supabase env vars not configured — auth disabled
      return null
    }
  }, [])

  useEffect(() => {
    if (!supabase) {
      setLoading(false)
      return
    }

    // Fetch initial session
    supabase.auth.getUser().then(({ data }) => {
      setUser(data.user ?? null)
      setLoading(false)
    })

    // Listen for auth state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
    })

    return () => {
      subscription.unsubscribe()
    }
  }, [supabase])

  const signInWithGitHub = useCallback(async () => {
    if (!supabase) return
    await supabase.auth.signInWithOAuth({
      provider: "github",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    })
  }, [supabase])

  const signInWithGoogle = useCallback(async () => {
    // Placeholder — Google OAuth not yet configured
    console.warn("[auth] Google OAuth is not yet configured")
  }, [])

  const signInWithMicrosoft = useCallback(async () => {
    // Placeholder — Microsoft OAuth not yet configured
    console.warn("[auth] Microsoft OAuth is not yet configured")
  }, [])

  const signOut = useCallback(async () => {
    if (!supabase) return
    await supabase.auth.signOut()
    setUser(null)
  }, [supabase])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      signInWithGitHub,
      signInWithGoogle,
      signInWithMicrosoft,
      signOut,
    }),
    [user, loading, signInWithGitHub, signInWithGoogle, signInWithMicrosoft, signOut],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
