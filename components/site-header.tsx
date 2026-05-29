"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";
import { toast } from "sonner";
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
import { clearAllPrivateImageCaches } from "@/lib/private-image-cache";
import { Link, usePathname } from "@/i18n/navigation";

function getInitials(name: string | undefined | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function LanguageSwitcher() {
  const pathname = usePathname();

  return (
    <div className="flex items-center gap-0.5 text-xs">
      <Link
        href={pathname}
        locale="zh"
        className="px-1.5 py-0.5 rounded hover:bg-muted transition-colors"
      >
        中
      </Link>
      <span className="text-muted-foreground">/</span>
      <Link
        href={pathname}
        locale="en"
        className="px-1.5 py-0.5 rounded hover:bg-muted transition-colors"
      >
        EN
      </Link>
    </div>
  );
}

export function SiteHeader() {
  const t = useTranslations("header");
  const { user, signOut } = useAuth();
  const { showNsfw, setShowNsfw } = useUserPreferences();
  const [loginDialogOpen, setLoginDialogOpen] = useState(false);

  const handleSignOut = useCallback(async () => {
    await signOut();
  }, [signOut]);

  const handleClearCache = useCallback(async () => {
    await clearAllPrivateImageCaches();
    toast.success(t("cacheCleared"));
    window.location.reload();
  }, [t]);

  const displayName =
    user?.user_metadata?.full_name ??
    user?.user_metadata?.name ??
    user?.email ??
    t("user");
  const avatarUrl = user?.user_metadata?.avatar_url as string | undefined;

  return (
    <>
      <header className="bg-background/80 sticky top-0 z-50 w-full border-b backdrop-blur supports-backdrop-filter:bg-background/60">
        <div className="mx-auto flex h-10 w-full max-w-7xl items-center justify-between gap-4 px-4 md:px-6">
          {/* Brand */}
          <nav aria-label={t("brand")} className="flex items-center gap-2">
            <Link
              href="/"
              className="flex items-center gap-2 transition-opacity hover:opacity-80"
            >
              <span className="from-primary to-primary/70 bg-linear-to-r bg-clip-text text-base font-bold tracking-tight text-transparent">
                {t("brand")}
              </span>
              <Badge variant="secondary" className="text-[10px] font-normal">
                {t("beta")}
              </Badge>
            </Link>
          </nav>

          {/* Right side */}
          <div className="flex items-center gap-1">
            <LanguageSwitcher />
            <ThemeToggle />

            {!user ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setLoginDialogOpen(true)}
              >
                {t("login")}
              </Button>
            ) : (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="focus-visible:ring-ring ml-1 rounded-full focus-visible:outline-none focus-visible:ring-2"
                    aria-label={t("userMenu")}
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
                    {t("showNsfw")}
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => void handleClearCache()}>
                    {t("clearCache")}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => void handleSignOut()}>
                    {t("logout")}
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
