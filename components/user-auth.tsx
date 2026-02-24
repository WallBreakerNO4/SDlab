"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { createClient } from "@/lib/supabase/client"

type AuthState = "loading" | "anon" | "authed"

export function UserAuth() {
  const [authState, setAuthState] = useState<AuthState>("loading")
  const [userDisplay, setUserDisplay] = useState<string>("")

  useEffect(() => {
    async function checkAuth() {
      try {
        const supabase = createClient()
        const {
          data: { user },
        } = await supabase.auth.getUser()

        if (user) {
          let display = user.id.slice(0, 8)
          if (user.email) {
            const [local, domain] = user.email.split("@")
            if (domain) {
              const maskedLocalStr =
                local.length <= 2 ? `${local}***` : `${local.slice(0, 2)}***`
              display = `${maskedLocalStr}@${domain}`
            }
          }
          setUserDisplay(display)
          setAuthState("authed")
        } else {
          setAuthState("anon")
        }
      } catch {

        setAuthState("anon")
      }
    }

    void checkAuth()
  }, [])

  const handleLogout = async () => {
    try {
      const supabase = createClient()
      await supabase.auth.signOut()
      window.location.reload()
    } catch {

    }
  }

  if (authState === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <div className="h-4 w-24 animate-pulse rounded bg-muted" />
      </div>
    )
  }

  if (authState === "anon") {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>登录以解锁 advance/nsfw 与原图下载</span>
        <Button asChild variant="outline" size="sm">
          <Link href="/login">登录</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">当前登录：{userDisplay}</span>
      <Button variant="outline" size="sm" onClick={handleLogout}>
        登出
      </Button>
    </div>
  )
}
