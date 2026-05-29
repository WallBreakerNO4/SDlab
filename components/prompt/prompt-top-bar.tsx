"use client"

import { useState, useEffect } from "react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useModel } from "@/lib/prompt-model-context"
import { Search, X, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import type { FileInfo, FilterScope, FilterMode } from "@/lib/prompt-types"

interface TopBarProps {
  files: FileInfo[]
  currentFileId: string
  onFileChange: (fileId: string) => void
  filterQuery: string
  onFilterChange: (query: string) => void
  filterScope: FilterScope
  onFilterScopeChange: (scope: FilterScope) => void
  filterMode: FilterMode
  onFilterModeChange: (mode: FilterMode) => void
}

export function PromptTopBar({
  files,
  currentFileId,
  onFileChange,
  filterQuery,
  onFilterChange,
  filterScope,
  onFilterScopeChange,
  filterMode,
  onFilterModeChange,
}: TopBarProps) {
  const { model, setModel } = useModel()
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <header className="sticky top-0 z-50 flex h-14 items-center gap-3 border-b bg-background px-4">
      <div className="flex items-center gap-2">
        <Search className="h-5 w-5 text-primary" />
        <h1 className="text-sm font-semibold tracking-tight hidden sm:inline">
          Prompt 法典
        </h1>
      </div>

      <div className="flex-1" />

      {/* 搜索输入 */}
      <div className="relative">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
        <Input
          placeholder="搜索标签或名称..."
          value={filterQuery}
          onChange={(e) => onFilterChange(e.target.value)}
          className="h-8 w-[200px] pl-7 pr-7 text-xs"
        />
        {filterQuery && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute right-0.5 top-1/2 -translate-y-1/2 h-6 w-6"
            onClick={() => onFilterChange("")}
          >
            <X className="h-3 w-3" />
          </Button>
        )}
      </div>

      {/* 匹配模式切换 */}
      <Badge
        variant={filterMode === "exact" ? "default" : "outline"}
        className="cursor-pointer text-[10px] h-5 px-1.5 shrink-0"
        onClick={() =>
          onFilterModeChange(filterMode === "exact" ? "fuzzy" : "exact")
        }
      >
        {filterMode === "exact" ? "精确" : "模糊"}
      </Badge>

      {/* 搜索范围 */}
      <div className="flex gap-1">
        {(["all", "name", "tag"] as FilterScope[]).map((s) => (
          <Badge
            key={s}
            variant={filterScope === s ? "default" : "outline"}
            className="cursor-pointer text-[10px] h-5 px-1.5"
            onClick={() => onFilterScopeChange(s)}
          >
            {s === "all" ? "全部" : s === "name" ? "名称" : "Tag"}
          </Badge>
        ))}
      </div>

      <Select value={currentFileId} onValueChange={onFileChange}>
        <SelectTrigger className="w-[180px] h-8 text-xs">
          <SelectValue placeholder="选择法典" />
        </SelectTrigger>
        <SelectContent>
          {files.map((f) => (
            <SelectItem key={f.id} value={f.id} className="text-xs">
              {f.title}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={model}
        onValueChange={(v) => setModel(v as "novelai" | "comfyui")}
      >
        <SelectTrigger className="w-[120px] h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="novelai" className="text-xs">
            NovelAI
          </SelectItem>
          <SelectItem value="comfyui" className="text-xs">
            ComfyUI
          </SelectItem>
        </SelectContent>
      </Select>

      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      >
        {mounted ? (
          theme === "dark" ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )
        ) : (
          <Sun className="h-4 w-4" />
        )}
      </Button>
    </header>
  )
}
