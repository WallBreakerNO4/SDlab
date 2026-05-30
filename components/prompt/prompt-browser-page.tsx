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
  const [fileExpandedMap, setFileExpandedMap] = useState<FileExpandedMap>({})

  const [filterQuery, setFilterQuery] = useState("")
  const [filterScope, setFilterScope] = useState<FilterScope>("all")
  const [filterMode, setFilterMode] = useState<FilterMode>("exact")
  const [debouncedQuery, setDebouncedQuery] = useState("")

  const loadedFileIdRef = useRef<string>("")

  useEffect(() => {
    setFileExpandedMap(loadExpandedMap())
  }, [])

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

  useEffect(() => {
    if (!currentFileId) return
    if (loadedFileIdRef.current === currentFileId) return

    loadedFileIdRef.current = currentFileId
    setLoading(true)
    loadFileData(currentFileId)
      .then((data) => {
        setFileData(data)
        setLoading(false)
      })
      .catch((e) => {
        setError("加载文件失败: " + e.message)
        setLoading(false)
      })
  }, [currentFileId])

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

  useEffect(() => {
    if (!fileData || scrollTarget) return

    const savedEntryId = getScrollPosition(currentFileId)
    if (savedEntryId) {
      setScrollTarget({ type: "entry", value: savedEntryId })
    }
  }, [fileData, currentFileId])

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

  // --- 搜索逻辑 ---

  useEffect(() => {
    if (filterMode === "exact") {
      setDebouncedQuery(filterQuery)
      return
    }
    const timer = setTimeout(() => setDebouncedQuery(filterQuery), 200)
    return () => clearTimeout(timer)
  }, [filterQuery, filterMode])

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

  const filteredToc = useMemo(() => {
    if (!fileData?.toc) return []
    if (!debouncedQuery.trim()) return fileData.toc
    return filterToc(fileData.toc, filteredEntries)
  }, [fileData?.toc, filteredEntries, debouncedQuery])

  const isFiltering = debouncedQuery.trim().length > 0

  useEffect(() => {
    if (isFiltering) {
      setActiveSection(null)
    }
  }, [isFiltering])

  useEffect(() => {
    if (isFiltering) {
      setScrollTarget({ type: "section", value: "__top__" })
    }
  }, [isFiltering])

  const expandedNodes = useMemo(() => {
    if (isFiltering && filteredToc.length > 0) {
      return new Set(getAllTocKeys(filteredToc))
    }
    if (fileExpandedMap[currentFileId]) {
      return new Set<string>(fileExpandedMap[currentFileId])
    }
    if (fileData?.toc) {
      return new Set<string>(getDefaultExpandedKeys(fileData.toc))
    }
    return new Set<string>()
  }, [isFiltering, filteredToc, fileExpandedMap, currentFileId, fileData?.toc])

  useEffect(() => {
    if (!fileData?.toc || !currentFileId) return
    if (fileExpandedMap[currentFileId]) return

    const defaults = getDefaultExpandedKeys(fileData.toc)
    setFileExpandedMap((prev) => {
      if (prev[currentFileId]) return prev
      const newMap = { ...prev, [currentFileId]: defaults }
      saveExpandedMap(newMap)
      return newMap
    })
  }, [fileData?.toc, currentFileId, fileExpandedMap])

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
        onFilterChange={setFilterQuery}
        filterScope={filterScope}
        onFilterScopeChange={setFilterScope}
        filterMode={filterMode}
        onFilterModeChange={setFilterMode}
      />

      <div className="flex flex-1 overflow-hidden">
        {fileData && (
          <TocSidebar
            toc={filteredToc}
            activeSection={activeSection}
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
              activeSection={activeSection}
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
