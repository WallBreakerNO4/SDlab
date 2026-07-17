"use client"

import { useCallback, useEffect, useState } from "react"
import { useLocale, useTranslations } from "next-intl"
import { toast } from "sonner"

import { useAuth } from "@/components/auth-provider"
import { AuthLoginDialog } from "@/components/auth-login-dialog"
import { Button } from "@/components/ui/button"
import { Link } from "@/i18n/navigation"
import {
  deleteStyleFavorite,
  fetchStyleFavorites,
  type StyleFavoriteEntry,
  type StyleKey,
} from "@/lib/style-favorites"

/** 收藏时间本地化显示；非法日期原样返回，不阻断列表渲染 */
function formatFavoriteTime(iso: string, locale: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date)
}

export default function FavoritesPage() {
  const t = useTranslations("styleFavorites")
  const { user } = useAuth()
  const [loginDialogOpen, setLoginDialogOpen] = useState(false)

  // 未登录：登录引导（与 prompts 页门控同一模式）
  if (!user) {
    return (
      <>
        <div className="flex min-h-svh items-center justify-center">
          <div className="flex max-w-sm flex-col items-center gap-4 px-4 text-center">
            <div className="text-4xl select-none" aria-hidden="true">
              {"⭐"}
            </div>
            <h2 className="text-lg font-semibold">{t("loginGateTitle")}</h2>
            <p className="text-sm text-balance text-muted-foreground">
              {t("loginGateDescription")}
            </p>
            <Button onClick={() => setLoginDialogOpen(true)}>
              {t("loginGateButton")}
            </Button>
          </div>
        </div>
        <AuthLoginDialog
          open={loginDialogOpen}
          onOpenChange={setLoginDialogOpen}
        />
      </>
    )
  }

  // key=user.id：切换账号时整体重挂载，收藏列表状态随之重置
  return <FavoritesList key={user.id} />
}

function FavoritesList() {
  const t = useTranslations("styleFavorites")
  const locale = useLocale()

  // null = 尚未拉取完成（加载态）；拉取失败静默降级为空列表，不报错刷屏
  const [entries, setEntries] = useState<StyleFavoriteEntry[] | null>(null)
  const [removingKeys, setRemovingKeys] = useState<ReadonlySet<StyleKey>>(
    new Set(),
  )

  // 自包含拉取收藏列表（组件已按 user.id 重挂载，无需在 effect 内重置）
  useEffect(() => {
    let cancelled = false

    fetchStyleFavorites().then((result) => {
      if (cancelled) return
      setEntries(result ?? [])
    })

    return () => {
      cancelled = true
    }
  }, [])

  // 取消收藏：成功后从列表移除，失败 toast 提示
  const handleRemove = useCallback(
    async (styleKey: StyleKey) => {
      setRemovingKeys((prev) => new Set(prev).add(styleKey))
      const ok = await deleteStyleFavorite(styleKey)
      setRemovingKeys((prev) => {
        const next = new Set(prev)
        next.delete(styleKey)
        return next
      })
      if (ok) {
        setEntries((prev) =>
          prev ? prev.filter((entry) => entry.style_key !== styleKey) : prev,
        )
      } else {
        toast.error(t("toggleFailed"))
      }
    },
    [t],
  )

  return (
    <main className="h-full w-full overflow-y-auto">
      <div className="container mx-auto max-w-3xl px-4 py-12">
        <h1 className="text-xl font-semibold">{t("title")}</h1>

        {entries === null && (
          <p className="mt-8 text-sm text-muted-foreground">{t("loading")}</p>
        )}

        {entries !== null && entries.length === 0 && (
          <p className="mt-8 text-sm text-muted-foreground">{t("empty")}</p>
        )}

        {entries !== null && entries.length > 0 && (
          <ul className="mt-8 flex flex-col gap-4">
            {entries.map((entry) => (
              <li
                key={entry.style_key}
                data-favorite-entry={entry.style_key}
                className="rounded-lg border p-4"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    {/* label 是收藏时的显示快照（决策 5），不参与匹配 */}
                    <p className="text-sm font-medium break-words">
                      {entry.label}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t("favoritedAt", {
                        time: formatFavoriteTime(entry.created_at, locale),
                      })}
                    </p>
                    <p className="mt-3 text-xs text-muted-foreground">
                      {t("availableModels")}
                    </p>
                    {entry.runs.length > 0 ? (
                      <ul className="mt-1 flex flex-wrap gap-2">
                        {entry.runs.map((run) => (
                          <li key={run.run_dir}>
                            {/* hash 为 1-based 网格行号，故 y_index + 1 */}
                            <Link
                              href={`/models/${encodeURIComponent(run.run_dir)}#${run.y_index + 1}`}
                              className="inline-block rounded-full border px-3 py-1 text-xs hover:bg-muted"
                            >
                              {run.name ?? run.run_dir}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-sm text-muted-foreground">
                        {t("noAvailableModels")}
                      </p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={removingKeys.has(entry.style_key)}
                    onClick={() => void handleRemove(entry.style_key)}
                  >
                    {t("remove")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  )
}
