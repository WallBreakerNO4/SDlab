"use client";

import Link from "next/link";

import { useCallback, useState } from "react";
import { AuthLoginDialog } from "@/components/auth-login-dialog";
import { useAuth } from "@/components/auth-provider";
import { useUserPreferences } from "@/components/user-preferences-provider";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function getInitials(name: string | undefined | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export function SiteHeader() {
  const { user, loading, signOut } = useAuth();
  const { showNsfw, setShowNsfw } = useUserPreferences();
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);

  const handleSignOut = useCallback(async () => {
    await signOut();
  }, [signOut]);

  const displayName =
    user?.user_metadata?.full_name ??
    user?.user_metadata?.name ??
    user?.email ??
    "用户";
  const avatarUrl = user?.user_metadata?.avatar_url as string | undefined;

  return (
    <>
      <header className="bg-background/80 sticky top-0 z-50 w-full border-b backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-10 w-full max-w-7xl items-center justify-between gap-4 px-4 md:px-6">
          {/* Brand */}
          <Link
            href="/"
            className="flex items-center gap-2 transition-opacity hover:opacity-80"
          >
            <span className="from-primary to-primary/70 bg-gradient-to-r bg-clip-text text-base font-bold tracking-tight text-transparent">
              SD Style Lab
            </span>
            <Badge variant="secondary" className="text-[10px] font-normal">
              Beta
            </Badge>
          </Link>

          {/* Right side */}
          <div className="flex items-center gap-1">
            <ThemeToggle />

            {loading ? null : !user ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setLoginDialogOpen(true)}
              >
                登录
              </Button>
            ) : (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="focus-visible:ring-ring ml-1 rounded-full focus-visible:outline-none focus-visible:ring-2"
                    aria-label="用户菜单"
                  >
                    <Avatar size="default" className="size-7">
                      {avatarUrl ? (
                        <AvatarImage src={avatarUrl} alt={displayName} />
                      ) : null}
                      <AvatarFallback className="text-[10px]">
                        {getInitials(displayName)}
                      </AvatarFallback>
                    </Avatar>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <div className="px-2 py-1.5 text-xs">
                    <p className="truncate font-medium">{displayName}</p>
                    {user.email ? (
                      <p className="text-muted-foreground truncate">
                        {user.email}
                      </p>
                    ) : null}
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuCheckboxItem
                    checked={showNsfw}
                    onCheckedChange={(checked) => {
                      void setShowNsfw(checked === true);
                    }}
                  >
                    显示 NSFW
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => void handleSignOut()}>
                    退出登录
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </header>

      <AuthLoginDialog
        open={loginDialogOpen}
        onOpenChange={setLoginDialogOpen}
      />
    </>
  );
}
