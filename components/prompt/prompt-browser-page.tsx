"use client"

import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useTranslations } from "next-intl"
import { PromptTopBar } from "./prompt-top-bar"
import { TocSidebar } from "./prompt-toc-sidebar"
import { PromptEntryList } from "./prompt-entry-list"
import type { ScrollTarget } from "./prompt-entry-list"
import { useModel } from "@/lib/prompt-model-context"
import { loadIndex, loadFileData } from "@/lib/prompt-data-loader"
import { saveScrollPosition, getScrollPosition } from "@/hooks/use-prompts-scroll-restore"
import { nodeKey } from "./prompt-toc-tree"
import {
  filterEntriesExact,
  filterEntriesFuzzy,
  createFilterFuse,
  filterToc,
  getAllTocKeys,
} from "@/lib/prompt-filter"
import type { FileIndex, FileData, FilterScope, FilterMode } from "@/lib/prompt-types"
import { useAuth } from "@/components/auth-provider"
import { AuthLoginDialog } from "@/components/auth-login-dialog"
import { Button } from "@/components/ui/button"

const EXPAND_STORAGE_KEY = "toc-expanded"

type FileExpandedMap = Record<string, string[]>

function loadExpandedMap(): FileExpandedMap {
  try {
    if (typeof window === "undefined") return {}
    const raw = localStorage.getItem(EXPAND_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    /* ignore parse errors */
  }
  return {}
}

function saveExpandedMap(map: FileExpandedMap) {
  localStorage.setItem(EXPAND_STORAGE_KEY, JSON.stringify(map))
}

function getDefaultExpandedKeys(toc: import("@/lib/prompt-types").TocNode[]): string[] {
  const keys: string[] = []
  function walk(nodes: import("@/lib/prompt-types").TocNode[], path: string[]) {
    for (const node of nodes) {
      const nodePath = [...path, node.title]
      if (node.level < 1) keys.push(nodeKey(nodePath))
      if (node.children) walk(node.children, nodePath)
    }
  }
  walk(toc, [])
  return keys
}

export default function PromptBrowserPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { model } = useModel()
  const t = useTranslations("prompts")
  const { user } = useAuth()
  const [loginDialogOpen, setLoginDialogOpen] = useState(false)

  const [fileIndex, setFileIndex] = useState<FileIndex | null>(null)
  const [currentFileId, setCurrentFileId] = useState<string>("")
  const [fileData, setFileData] = useState<FileData | null>(null)
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [scrollTarget, setScrollTarget] = useState<ScrollTarget | null>(null)
  const [fileExpandedMap, setFileExpandedMap] = useState<FileExpandedMap>(() => loadExpandedMap())

  const [filterQuery, setFilterQuery] = useState("")
  const [filterScope, setFilterScope] = useState<FilterScope>("all")
  const [filterMode, setFilterMode] = useState<FilterMode>("exact")
  const [debouncedQuery, setDebouncedQuery] = useState("")

  const loadedFileIdRef = useRef<string>("")
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const debouncedQueryRef = useRef("")

  // --- 加载索引 ---
  useEffect(() => {
    loadIndex()
      .then((idx) => {
        setFileIndex(idx)
        const urlFile = searchParams.get("file")
        const initialFile =
          urlFile && idx.files.find((f) => f.id === urlFile)
            ? urlFile
            : idx.files[0]?.id || ""
        setCurrentFileId(initialFile)
      })
      .catch((e) => {
        setError("加载索引失败: " + e.message)
        setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // --- 加载文件数据（含滚动恢复 + 默认展开 key 初始化） ---
  useEffect(() => {
    if (!currentFileId) return
    if (loadedFileIdRef.current === currentFileId) return

    loadedFileIdRef.current = currentFileId
    setLoading(true)
    loadFileData(currentFileId)
      .then((data) => {
        setFileData(data)
        // 恢复滚动位置
        const savedEntryId = getScrollPosition(currentFileId)
        if (savedEntryId) {
          setScrollTarget({ type: "entry", value: savedEntryId })
        }
        // 为新文件初始化默认展开的 TOC key
        setFileExpandedMap((prev) => {
          if (prev[currentFileId]) return prev
          const defaults = getDefaultExpandedKeys(data.toc)
          const newMap = { ...prev, [currentFileId]: defaults }
          saveExpandedMap(newMap)
          return newMap
        })
        setLoading(false)
      })
      .catch((e) => {
        setError("加载文件失败: " + e.message)
        setLoading(false)
      })
  }, [currentFileId])

  // --- 同步 URL ---
  useEffect(() => {
    if (!currentFileId) return
    const currentFile = searchParams.get("file")
    if (currentFile !== currentFileId) {
      const newParams = new URLSearchParams(searchParams.toString())
      newParams.set("file", currentFileId)
      router.replace(`?${newParams.toString()}`, { scroll: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentFileId])

  const handleTopEntryChange = useCallback(
    (entryId: string) => {
      saveScrollPosition(currentFileId, entryId)
    },
    [currentFileId]
  )

  // --- IntersectionObserver 跟踪当前章节 ---
  useEffect(() => {
    if (!fileData) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const title = entry.target.getAttribute("data-section-title")
            if (title) setActiveSection(title)
          }
        }
      },
      { rootMargin: "-50px 0px -80% 0px" }
    )

    const sections = document.querySelectorAll("[data-section-title]")
    sections.forEach((s) => observer.observe(s))

    return () => observer.disconnect()
  }, [fileData])

  const handleToggleExpand = useCallback(
    (key: string) => {
      setFileExpandedMap((prev) => {
        const current = new Set(prev[currentFileId] || [])
        if (current.has(key)) {
          current.delete(key)
        } else {
          current.add(key)
        }
        const newMap = { ...prev, [currentFileId]: [...current] }
        saveExpandedMap(newMap)
        return newMap
      })
    },
    [currentFileId]
  )

  const handleFileChange = useCallback((fileId: string) => {
    setCurrentFileId(fileId)
    setFileData(null)
  }, [])

  const handleSectionClick = useCallback(
    (title: string) => {
      setActiveSection(title)
      const firstEntry = fileData?.entries.find((e) => e.path.includes(title))
      if (firstEntry) {
        const sectionTitle = firstEntry.path.join(" > ")
        setScrollTarget({ type: "section", value: sectionTitle })
      }
    },
    [fileData]
  )

  // --- 搜索防抖（事件处理模式，避免在 effect 中 setState） ---
  const handleFilterChange = useCallback(
    (value: string) => {
      setFilterQuery(value)
      clearTimeout(debounceRef.current)

      const wasFiltering = debouncedQueryRef.current.trim().length > 0
      const isNowFiltering = value.trim().length > 0

      if (filterMode === "exact") {
        setDebouncedQuery(value)
        if (isNowFiltering && !wasFiltering) {
          setActiveSection(null)
          setScrollTarget({ type: "section", value: "__top__" })
        }
        return
      }

      debounceRef.current = setTimeout(() => {
        // 取闭包中的 value，debouncedQueryRef 在 render 中同步但此处仍是旧值
        const wasFiltering = debouncedQueryRef.current.trim().length > 0
        const isNowFiltering = value.trim().length > 0
        setDebouncedQuery(value)
        if (isNowFiltering && !wasFiltering) {
          setActiveSection(null)
          setScrollTarget({ type: "section", value: "__top__" })
        }
      }, 200)
    },
    [filterMode]
  )

  const filterFuse = useMemo(() => {
    if (!fileData || filterMode !== "fuzzy") return null
    return createFilterFuse(fileData.entries, filterScope)
  }, [fileData, filterMode, filterScope])

  const filteredEntries = useMemo(() => {
    if (!fileData) return []
    if (!debouncedQuery.trim()) return fileData.entries
    if (filterMode === "exact") {
      return filterEntriesExact(fileData.entries, debouncedQuery, filterScope)
    }
    if (filterFuse) {
      return filterEntriesFuzzy(filterFuse, debouncedQuery)
    }
    return fileData.entries
  }, [fileData, debouncedQuery, filterScope, filterMode, filterFuse])

  // 提取 toc 为独立变量，避免 memo deps 中 fileData?.toc 被编译器视为依赖整个 fileData
  const toc = fileData?.toc
  const filteredToc = useMemo(() => {
    if (!toc) return []
    if (!debouncedQuery.trim()) return toc
    return filterToc(toc, filteredEntries)
  }, [toc, filteredEntries, debouncedQuery])

  const isFiltering = debouncedQuery.trim().length > 0

  // 保持 ref 同步（在 effect 中写入，供事件处理器读取上一个值）
  useEffect(() => {
    debouncedQueryRef.current = debouncedQuery
  }, [debouncedQuery])

  // 过滤中时关闭章节高亮（render 中派生，避免 effect setState）
  const effectiveActiveSection = isFiltering ? null : activeSection

  const expandedNodes = useMemo(() => {
    if (isFiltering && filteredToc.length > 0) {
      return new Set(getAllTocKeys(filteredToc))
    }
    if (fileExpandedMap[currentFileId]) {
      return new Set<string>(fileExpandedMap[currentFileId])
    }
    if (toc) {
      return new Set<string>(getDefaultExpandedKeys(toc))
    }
    return new Set<string>()
  }, [isFiltering, filteredToc, fileExpandedMap, currentFileId, toc])

  // 未登录时显示登录引导
  if (!user) {
    return (
      <>
        <div className="flex min-h-svh items-center justify-center">
          <div className="flex flex-col items-center gap-4 text-center max-w-sm px-4">
            <div className="text-4xl select-none" aria-hidden="true">
              {"📜"}
            </div>
            <h2 className="text-lg font-semibold">{t("loginGateTitle")}</h2>
            <p className="text-sm text-muted-foreground text-balance">
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

  if (error) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="flex flex-1 flex-col overflow-hidden" style={{ height: "calc(100dvh - 2.5rem)" }}>
      <PromptTopBar
        files={fileIndex?.files || []}
        currentFileId={currentFileId}
        onFileChange={handleFileChange}
        filterQuery={filterQuery}
        onFilterChange={handleFilterChange}
        filterScope={filterScope}
        onFilterScopeChange={setFilterScope}
        filterMode={filterMode}
        onFilterModeChange={setFilterMode}
      />

      <div className="flex flex-1 overflow-hidden">
        {fileData && (
          <TocSidebar
            toc={filteredToc}
            activeSection={effectiveActiveSection}
            onSectionClick={handleSectionClick}
            expandedNodes={expandedNodes}
            onToggleExpand={handleToggleExpand}
          />
        )}

        <main className="flex-1 overflow-hidden">
          {loading && (
            <div className="flex h-full items-center justify-center">
              <div className="text-sm text-muted-foreground">加载中...</div>
            </div>
          )}
          {!loading && fileData && isFiltering && filteredEntries.length === 0 && (
            <div className="flex h-full items-center justify-center">
              <div className="text-sm text-muted-foreground">无匹配结果</div>
            </div>
          )}
          {!loading && fileData && filteredEntries.length > 0 && (
            <PromptEntryList
              entries={filteredEntries}
              model={model}
              activeSection={effectiveActiveSection}
              scrollTarget={scrollTarget}
              onScrollComplete={() => setScrollTarget(null)}
              onTopEntryChange={handleTopEntryChange}
            />
          )}
          {!loading && fileData && !isFiltering && filteredEntries.length === 0 && (
            <div className="flex h-full items-center justify-center">
              <div className="text-sm text-muted-foreground">无条目</div>
            </div>
          )}
        </main>
      </div>
    </div>
    <AuthLoginDialog
      open={loginDialogOpen}
      onOpenChange={setLoginDialogOpen}
    />
    </>
  )
}
