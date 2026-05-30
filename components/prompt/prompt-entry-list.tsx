"use client"

import { useRef, useMemo, useCallback, useEffect, useState } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import type { Entry, TargetModel } from "@/lib/prompt-types"
import { PromptEntryCard } from "./prompt-entry-card"
import { cn } from "@/lib/utils"

export interface ScrollTarget {
  type: "section" | "entry"
  value: string  // section title or entry id
}

interface EntryListProps {
  entries: Entry[]
  model: TargetModel
  activeSection?: string | null
  scrollTarget?: ScrollTarget | null
  onScrollComplete?: () => void
  onTopEntryChange?: (entryId: string) => void
}

export function PromptEntryList({
  entries,
  model,
  activeSection,
  scrollTarget,
  onScrollComplete,
  onTopEntryChange,
}: EntryListProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const isScrollingRef = useRef(false)
  const [highlightEntryId, setHighlightEntryId] = useState<string | null>(null)

  // 将 entries 按 path 分组，在每组前插入章节标题
  const flatItems = useMemo(() => {
    const items: Array<
      | { type: "section"; title: string }
      | { type: "entry"; entry: Entry }
    > = []

    let currentPath: string[] = []
    for (const entry of entries) {
      if (
        entry.path.length > 0 &&
        JSON.stringify(entry.path) !== JSON.stringify(currentPath)
      ) {
        currentPath = entry.path
        items.push({ type: "section", title: entry.path.join(" > ") })
      }
      items.push({ type: "entry", entry })
    }

    return items
  }, [entries])

  // TanStack Virtual 的 useVirtualizer 返回不可安全 memoize 的函数，
  // React Compiler 无法优化此 hook — 这是库层面的限制
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => parentRef.current,
    estimateSize: useCallback((index: number) => {
      const item = flatItems[index]
      if (item.type === "section") return 32
      const entry = item.entry
      let height = 120
      if (entry.prompt.characters.length > 0) height += 80
      if (entry.variants && entry.variants.length > 0) {
        height += entry.variants.length * 60
      }
      return Math.min(height, 500)
    }, [flatItems]),
    overscan: 5,
  })

  // 处理 scrollTarget 滚动
  useEffect(() => {
    if (!scrollTarget) return

    if (scrollTarget.type === "section" && scrollTarget.value === "__top__") {
      virtualizer.scrollToIndex(0, { align: "start" })
      onScrollComplete?.()
      return
    }

    let targetIndex = -1
    if (scrollTarget.type === "section") {
      targetIndex = flatItems.findIndex(
        (item) => item.type === "section" && item.title === scrollTarget.value
      )
    } else {
      targetIndex = flatItems.findIndex(
        (item) => item.type === "entry" && item.entry.id === scrollTarget.value
      )
    }

    if (targetIndex >= 0) {
      isScrollingRef.current = true
      virtualizer.scrollToIndex(targetIndex, { align: "center" })
      if (scrollTarget.type === "entry") {
        setHighlightEntryId(scrollTarget.value)
      }
    }

    // 延迟重置标记，等待滚动完成
    const timeoutId = setTimeout(() => {
      isScrollingRef.current = false
    }, 500)

    onScrollComplete?.()
    return () => {
      clearTimeout(timeoutId)
      isScrollingRef.current = false
    }
  }, [scrollTarget, flatItems, virtualizer, onScrollComplete])

  // 2 秒后清除高亮
  useEffect(() => {
    if (!highlightEntryId) return
    const id = setTimeout(() => setHighlightEntryId(null), 2000)
    return () => clearTimeout(id)
  }, [highlightEntryId])

  // 监听用户滚动，追踪顶部可见条目
  useEffect(() => {
    const container = parentRef.current
    if (!container || !onTopEntryChange) return

    let debounceId: ReturnType<typeof setTimeout>

    const handleScroll = () => {
      clearTimeout(debounceId)
      debounceId = setTimeout(() => {
        if (isScrollingRef.current) return

        const containerRect = container.getBoundingClientRect()
        const entryEls = container.querySelectorAll<HTMLElement>("[data-entry-id]")

        let topEntryId: string | null = null
        for (const el of entryEls) {
          const rect = el.getBoundingClientRect()
          if (rect.bottom > containerRect.top + 32) {
            topEntryId = el.getAttribute("data-entry-id")
            break
          }
        }

        if (topEntryId) {
          onTopEntryChange(topEntryId)
        }
      }, 200)
    }

    container.addEventListener("scroll", handleScroll, { passive: true })
    return () => {
      container.removeEventListener("scroll", handleScroll)
      clearTimeout(debounceId)
    }
  }, [onTopEntryChange])

  const virtualItems = virtualizer.getVirtualItems()

  return (
    <div
      ref={parentRef}
      className="h-full overflow-y-auto"
      style={{ contain: "strict" }}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualItems.map((virtualItem) => {
          const item = flatItems[virtualItem.index]
          if (!item) return null

          if (item.type === "section") {
            return (
              <div
                key={`section-${virtualItem.index}`}
                data-index={virtualItem.index}
                data-section-title={item.title}
                ref={virtualizer.measureElement}
                className={cn(
                  "px-4 py-1.5 text-xs font-semibold text-muted-foreground bg-muted/60 border-b border-border/50",
                  activeSection === item.title && "text-primary bg-primary/5"
                )}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${virtualItem.start}px)`,
                }}
              >
                {item.title}
              </div>
            )
          }

          return (
            <div
              key={item.entry.id}
              data-index={virtualItem.index}
              data-entry-id={item.entry.id}
              ref={virtualizer.measureElement}
              className="px-4 py-2"
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualItem.start}px)`,
              }}
            >
              <PromptEntryCard entry={item.entry} model={model} highlight={item.entry.id === highlightEntryId} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
