"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

type RunSummary = {
  run_dir: string
  created_at: string
  x_count: number
  y_count: number
  total_cells: number
}

type LoadState = "loading" | "ready" | "error"

function isRunSummary(value: unknown): value is RunSummary {
  if (!value || typeof value !== "object") {
    return false
  }

  const run = value as Partial<RunSummary>

  return (
    typeof run.run_dir === "string" &&
    typeof run.created_at === "string" &&
    typeof run.x_count === "number" &&
    typeof run.y_count === "number" &&
    typeof run.total_cells === "number"
  )
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

function RunsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="grid grid-cols-4 gap-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ))}
    </div>
  )
}

export default function Page() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loadState, setLoadState] = useState<LoadState>("loading")

  useEffect(() => {
    const abortController = new AbortController()

    async function fetchRuns() {
      setLoadState("loading")

      try {
        const response = await fetch("/api/comfyui/runs", {
          signal: abortController.signal,
        })

        if (!response.ok) {
          throw new Error("Failed to load runs")
        }

        const data: unknown = await response.json()

        if (!Array.isArray(data)) {
          throw new Error("Unexpected runs payload")
        }

        setRuns(data.filter(isRunSummary))
        setLoadState("ready")
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return
        }

        setRuns([])
        setLoadState("error")
      }
    }

    void fetchRuns()

    return () => {
      abortController.abort()
    }
  }, [])

  const isLoading = loadState === "loading"
  const isEmpty = !isLoading && runs.length === 0

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-4 md:p-8">
      <Card>
        <CardHeader>
          <CardTitle>ComfyUI Runs</CardTitle>
          <CardDescription>
            浏览历史运行记录，选择一个 run 进入网格详情页。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? <RunsSkeleton /> : null}

          {isEmpty ? (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>
                  {loadState === "error" ? "加载失败" : "暂无可用 runs"}
                </EmptyTitle>
                <EmptyDescription>
                  {loadState === "error"
                    ? "请稍后刷新重试。"
                    : "当前还没有 run.json 可展示。"}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : null}

          {!isLoading && runs.length > 0 ? (
            <>
              <div className="space-y-3 md:hidden">
                {runs.map((run) => (
                  <Card key={run.run_dir} size="sm">
                    <CardContent className="space-y-2">
                      <div className="text-sm font-medium">{run.run_dir}</div>
                      <div className="text-muted-foreground text-xs">
                        {formatCreatedAt(run.created_at)}
                      </div>
                      <div className="text-xs">{`${run.x_count}*${run.y_count}`}</div>
                      <div className="text-xs">total: {run.total_cells}</div>
                      <Link
                        href={`/runs/${encodeURIComponent(run.run_dir)}`}
                        aria-label={run.run_dir}
                        className="text-primary text-xs underline-offset-4 hover:underline"
                      >
                        查看详情
                      </Link>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>run_dir</TableHead>
                      <TableHead>created_at</TableHead>
                      <TableHead>x_count*y_count</TableHead>
                      <TableHead>total_cells</TableHead>
                      <TableHead className="text-right">详情</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {runs.map((run) => (
                      <TableRow key={run.run_dir}>
                        <TableCell className="font-medium">{run.run_dir}</TableCell>
                        <TableCell>{formatCreatedAt(run.created_at)}</TableCell>
                        <TableCell>{`${run.x_count}*${run.y_count}`}</TableCell>
                        <TableCell>{run.total_cells}</TableCell>
                        <TableCell className="text-right">
                          <Link
                            href={`/runs/${encodeURIComponent(run.run_dir)}`}
                            aria-label={run.run_dir}
                            className="text-primary underline-offset-4 hover:underline"
                          >
                            打开
                          </Link>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>
    </main>
  )
}
