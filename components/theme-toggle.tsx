"use client"

import { useTheme } from "next-themes"
import { useEffect, useState } from "react"
import { HugeiconsIcon } from "@hugeicons/react"
import { SunIcon, MoonIcon } from "@hugeicons/core-free-icons"
import { Button } from "@/components/ui/button"

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" aria-label="切换主题" disabled>
        <HugeiconsIcon icon={SunIcon} className="size-4" />
      </Button>
    )
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="切换主题"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      {resolvedTheme === "dark" ? (
        <HugeiconsIcon icon={SunIcon} className="size-4" />
      ) : (
        <HugeiconsIcon icon={MoonIcon} className="size-4" />
      )}
    </Button>
  )
}
