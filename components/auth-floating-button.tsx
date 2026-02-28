"use client"

import { useCallback, useState } from "react"
import { useAuth } from "./auth-provider"
import { AuthLoginDialog } from "./auth-login-dialog"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

function getInitials(name: string | undefined | null): string {
  if (!name) return "?"
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
}

export function AuthFloatingButton() {
  const { user, loading, signOut } = useAuth()
  const [loginDialogOpen, setLoginDialogOpen] = useState(false)

  const handleSignOut = useCallback(async () => {
    await signOut()
  }, [signOut])

  // Don't render while loading to avoid flash
  if (loading) return null

  if (!user) {
    return (
      <>
        <div className="fixed top-4 right-4 z-50">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="shadow-sm"
            onClick={() => setLoginDialogOpen(true)}
          >
            登录
          </Button>
        </div>
        <AuthLoginDialog
          open={loginDialogOpen}
          onOpenChange={setLoginDialogOpen}
        />
      </>
    )
  }

  const displayName =
    user.user_metadata?.full_name ??
    user.user_metadata?.name ??
    user.email ??
    "用户"
  const avatarUrl = user.user_metadata?.avatar_url as string | undefined

  return (
    <div className="fixed top-4 right-4 z-50">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="focus-visible:ring-ring rounded-full focus-visible:outline-none focus-visible:ring-2"
            aria-label="用户菜单"
          >
            <Avatar size="default" className="shadow-sm">
              {avatarUrl ? (
                <AvatarImage src={avatarUrl} alt={displayName} />
              ) : null}
              <AvatarFallback>{getInitials(displayName)}</AvatarFallback>
            </Avatar>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <div className="px-2 py-1.5 text-xs">
            <p className="truncate font-medium">{displayName}</p>
            {user.email ? (
              <p className="text-muted-foreground truncate">{user.email}</p>
            ) : null}
          </div>
          <DropdownMenuItem onClick={() => void handleSignOut()}>
            退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
