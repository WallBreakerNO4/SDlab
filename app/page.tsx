"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

import type { RunSummary } from "@/lib/comfyui-types"

type LoadState = "loading" | "ready" | "error"

function isRunSummary(value: unknown): value is RunSummary {
  if (!value || typeof value !== "object") {
    return false
  }

  const run = value as Partial<RunSummary>

  return (
    typeof run.run_id === "string" &&
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
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <Card className="h-[120px]">
        <CardContent className="flex h-full flex-col justify-center space-y-4 pt-6">
          <Skeleton className="h-6 w-3/4" />
          <div className="flex gap-2">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-16" />
          </div>
        </CardContent>
      </Card>
      <Card className="h-[120px]">
        <CardContent className="flex h-full flex-col justify-center space-y-4 pt-6">
          <Skeleton className="h-6 w-3/4" />
          <div className="flex gap-2">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-16" />
          </div>
        </CardContent>
      </Card>
      <Card className="h-[120px]">
        <CardContent className="flex h-full flex-col justify-center space-y-4 pt-6">
          <Skeleton className="h-6 w-3/4" />
          <div className="flex gap-2">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-16" />
          </div>
        </CardContent>
      </Card>
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
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 overflow-auto p-4 md:p-8">
      <div className="animate-fade-in-up space-y-4 text-center">
        <h1 className="bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-4xl font-bold tracking-tight text-transparent md:text-5xl">
          AI 图像风格实验室
        </h1>
        <p className="text-muted-foreground text-xl">
          探索 Stable Diffusion 风格组合，发现无限创意可能
        </p>
      </div>

      <div className="space-y-8">
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
                  : "暂无可用 runs，请确认数据源已配置。"}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}

        {!isLoading && runs.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {runs.map((run, index) => {
              const modelName = run.model?.name || run.run_dir
              const modelDesc = run.model?.description?.zh || run.model?.description?.en
              return (
              <Link
                key={run.run_dir}
                href={`/runs/${encodeURIComponent(run.run_dir)}`}
                className="animate-fade-in-up block"
                style={{
                  animationFillMode: "forwards",
                  opacity: 0,
                  animationDelay: `${index * 80}ms`,
                }}
              >
                <Card className="hover:border-primary/50 group h-full transition-all duration-300 hover:shadow-xl dark:hover:shadow-primary/5">
                  <CardContent className="flex h-full flex-col justify-between space-y-4 pt-6">
                    <div className="space-y-3">
                      <div className="space-y-1.5">
                        <div className="group-hover:text-primary transition-colors text-xl font-bold leading-none tracking-tight">
                          {modelName}
                        </div>
                        <div className="text-muted-foreground/60 font-mono text-[10px]">
                          {run.run_dir}
                        </div>
                      </div>
                      {modelDesc ? (
                        <div className="bg-muted/50 rounded-md p-3 text-sm text-muted-foreground line-clamp-2">
                          {modelDesc}
                        </div>
                      ) : null}
                    </div>
                    <div className="flex items-center justify-between pt-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="bg-primary/5">{`${run.x_count}×${run.y_count}`}</Badge>
                        <Badge variant="secondary" className="opacity-80">{`${run.total_cells} 张`}</Badge>
                      </div>
                      <div className="text-muted-foreground/80 text-xs">
                        {formatCreatedAt(run.created_at)}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            )})}
          </div>
        ) : null}
      </div>
    </main>
  )
}
