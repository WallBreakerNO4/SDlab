"use client";

import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import { SunIcon, MoonIcon } from "@hugeicons/core-free-icons";
import { Button } from "@/components/ui/button";
import {
  THEME_COOKIE_MAX_AGE,
  THEME_COOKIE_NAME,
  type ThemePreference,
} from "@/lib/theme";

const emptySubscribe = () => () => {};

export function ThemeToggle() {
  const t = useTranslations("header");
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" aria-label={t("toggleTheme")} disabled>
        <HugeiconsIcon icon={SunIcon} className="size-4" />
      </Button>
    );
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={t("toggleTheme")}
      onClick={() => {
        const nextTheme: ThemePreference =
          resolvedTheme === "dark" ? "light" : "dark";

        document.cookie = `${THEME_COOKIE_NAME}=${encodeURIComponent(nextTheme)}; path=/; max-age=${THEME_COOKIE_MAX_AGE}; samesite=lax`;
        setTheme(nextTheme);
      }}
    >
      {resolvedTheme === "dark" ? (
        <HugeiconsIcon icon={SunIcon} className="size-4" />
      ) : (
        <HugeiconsIcon icon={MoonIcon} className="size-4" />
      )}
    </Button>
  );
}
