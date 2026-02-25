"use client"

import { useParams } from "next/navigation"

import { useEffect, useMemo, useState } from "react"

import {
  type RunGridIndexData,
  type RunGridXColumn,
  VirtualGrid,
} from "@/components/comfyui/virtual-grid"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

type RunDetailSummary = {
  run_id: string
  created_at: string
  run_dir: string
  selection: {
    total_cells: number
  }
}

type RunDetailResponse = {
  run: RunDetailSummary
  xLabels: string[]
  yLabels: string[]
  x_columns: RunGridXColumn[]
  y_indexes: number[]
}

type LoadState = "loading" | "ready" | "not-found" | "error"

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
}

function isRunDetailResponse(value: unknown): value is RunDetailResponse {
  if (!isRecord(value)) {
    return false
  }

  if (!isStringArray(value.xLabels) || !isStringArray(value.yLabels)) {
    return false
  }

  if (!Array.isArray(value.x_columns) || !Array.isArray(value.y_indexes)) {
    return false
  }

  if (!isRecord(value.run) || !isRecord(value.run.selection)) {
    return false
  }

  const run = value.run
  const selection = run.selection as Record<string, unknown>

  return (
    typeof run.run_id === "string" &&
    typeof run.created_at === "string" &&
    typeof run.run_dir === "string" &&
    typeof selection.total_cells === "number"
  )
}

function isRunGridIndexData(value: unknown): value is RunGridIndexData {
  if (!isRecord(value)) {
    return false
  }

  if (!Array.isArray(value.x_columns) || !Array.isArray(value.y_indexes)) {
    return false
  }

  const x_columns = value.x_columns as unknown[]
  const xColumnsOk = x_columns.every((col) => {
    if (!isRecord(col)) return false
    const type = col["type"]
    const typeOk = typeof type === "string" || type === null
    const desc = col["description"]
    const descOk = desc === null || isRecord(desc)
    return typeOk && descOk
  })

  const y_indexes = value.y_indexes as unknown[]
  const yIndexesOk = y_indexes.every(
    (item) => typeof item === "number" && Number.isFinite(item) && item >= 0,
  )

  return xColumnsOk && yIndexesOk
}

function formatCreatedAt(createdAt: string): string {
  const date = new Date(createdAt)

  if (Number.isNaN(date.getTime())) {
    return createdAt
  }

  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date)
}

function SummarySkeleton() {
  const keys = ["k1", "k2", "k3", "k4"]
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {keys.map((key) => (
        <div key={key} className="border p-3">
          <Skeleton className="mb-2 h-3 w-16" />
          <Skeleton className="h-4 w-full" />
        </div>
      ))}
    </div>
  )
}

function GridSkeleton() {
  const rowKeys = ["r1", "r2", "r3", "r4", "r5"]
  const cellKeys = ["c1", "c2", "c3", "c4", "c5", "c6"]
  return (
    <div className="space-y-2">
      {rowKeys.map((rowKey) => (
        <div key={rowKey} className="grid min-w-[960px] grid-cols-6 gap-2">
          {cellKeys.map((cellKey) => (
            <Skeleton key={`${rowKey}-${cellKey}`} className="h-32 w-full" />
          ))}
        </div>
      ))}
    </div>
  )
}

export default function RunDetailPage() {
  const params = useParams<{ runDir: string | string[] }>()
  const [loadState, setLoadState] = useState<LoadState>("loading")
  const [detailData, setDetailData] = useState<RunDetailResponse | null>(null)
  const [gridData, setGridData] = useState<RunGridIndexData | null>(null)

  const runDir = useMemo(() => {
    if (!params?.runDir) {
      return ""
    }

    return Array.isArray(params.runDir) ? params.runDir[0] : params.runDir
  }, [params])

  useEffect(() => {
    const abortController = new AbortController()

    async function fetchRunDetail() {
      if (!runDir) {
        setDetailData(null)
        setGridData(null)
        setLoadState("not-found")
        return
      }

      setLoadState("loading")

      try {
        const [detailResponse, gridResponse] = await Promise.all([
          fetch(`/api/comfyui/run/${encodeURIComponent(runDir)}`, {
            signal: abortController.signal,
          }),
          fetch(`/api/comfyui/run/${encodeURIComponent(runDir)}/grid`, {
            signal: abortController.signal,
          }),
        ])

        if (detailResponse.status === 404 || gridResponse.status === 404) {
          setDetailData(null)
          setGridData(null)
          setLoadState("not-found")
          return
        }

        if (!detailResponse.ok || !gridResponse.ok) {
          throw new Error("Failed to load run detail")
        }

        const [detailPayload, gridPayload]: [unknown, unknown] = await Promise.all([
          detailResponse.json(),
          gridResponse.json(),
        ])

        if (!isRunDetailResponse(detailPayload)) {
          throw new Error("Unexpected run detail payload")
        }

        if (!isRunGridIndexData(gridPayload)) {
          throw new Error("Unexpected run grid payload")
        }

        setDetailData(detailPayload)
        setGridData(gridPayload)
        setLoadState("ready")
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return
        }

        setDetailData(null)
        setGridData(null)
        setLoadState("error")
      }
    }

    void fetchRunDetail()

    return () => {
      abortController.abort()
    }
  }, [runDir])

  const isLoading = loadState === "loading"
  const isReady =
    loadState === "ready" && detailData !== null && gridData !== null
  const xCount = isReady ? gridData.x_columns.length : 0
  const yCount = isReady ? gridData.y_indexes.length : 0

  return (
    <main className="mx-auto flex h-dvh w-full max-w-none flex-col gap-3 overflow-hidden p-2 md:p-4">
      <Card>
        <CardHeader>
          <CardTitle>Run 结果页</CardTitle>
          <CardDescription className="break-all">
            run_dir: {runDir || "(invalid)"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div data-testid="run-detail-loading">
              <SummarySkeleton />
            </div>
          ) : null}

          {loadState === "not-found" ? (
            <Empty data-testid="run-not-found">
              <EmptyHeader>
                <EmptyTitle>未找到 run</EmptyTitle>
                <EmptyDescription>
                  无法加载 {runDir || "该路径"}，请确认 runDir 是否存在。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}

          {loadState === "error" ? (
            <Empty data-testid="run-error">
              <EmptyHeader>
                <EmptyTitle>加载失败</EmptyTitle>
                <EmptyDescription>
                  请求 run 详情失败，请稍后刷新重试。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}

          {isReady ? (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <div className="border p-3">
                <div className="text-muted-foreground text-xs">run_id</div>
                <div className="break-all text-xs font-medium">{detailData.run.run_id}</div>
              </div>
              <div className="border p-3">
                <div className="text-muted-foreground text-xs">created_at</div>
                <div className="text-xs font-medium">
                  {formatCreatedAt(detailData.run.created_at)}
                </div>
              </div>
              <div className="border p-3">
                <div className="text-muted-foreground text-xs">x*y</div>
                <div className="text-xs font-medium">{`${xCount}*${yCount}`}</div>
              </div>
              <div className="border p-3">
                <div className="text-muted-foreground text-xs">total_cells</div>
                <div className="text-xs font-medium">
                  {detailData.run.selection.total_cells}
                </div>
              </div>
            </div>
          ) : null}

          <div className="space-y-2" data-testid="run-toolbar">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" disabled={!isReady}>
                按状态筛选（预留）
              </Button>
              <Button size="sm" variant="outline" disabled={!isReady}>
                仅看失败（预留）
              </Button>
              <Button size="sm" variant="outline" disabled={!isReady}>
                重置视图（预留）
              </Button>
            </div>
            <p className="text-muted-foreground text-xs">
              工具栏仅提供骨架，后续任务接入网格交互与预览。
            </p>
          </div>
        </CardContent>
      </Card>

      <Card className="flex min-h-0 flex-1 flex-col">
        <CardHeader>
          <CardTitle>Grid 结果</CardTitle>
          <CardDescription>按 Y 轴行虚拟化渲染，支持 sticky 表头与左列。</CardDescription>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col">
          {isLoading ? <GridSkeleton /> : null}

          {isReady ? (
            <div className="min-h-0 flex-1">
              <VirtualGrid runDir={runDir} grid={gridData} />
            </div>
          ) : null}

          {loadState === "not-found" || loadState === "error" ? (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>暂无网格可展示</EmptyTitle>
                <EmptyDescription>
                  修复 runDir 或请求错误后，此区域将显示完整网格。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}
        </CardContent>
      </Card>
    </main>
  )
}
