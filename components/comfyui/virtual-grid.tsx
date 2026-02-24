"use client"

import { useVirtualizer } from "@tanstack/react-virtual"
import Image from "next/image"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type GridCellStatus = "success" | "failed" | "skipped" | "missing"

export type RunGridMeta = {
  xColumns: Array<Record<string, unknown>>
  yLabels: string[]
  x_count: number
  y_count: number
}

export type RunGridCellItem = {
  batch_index: number
  thumb_src: string | null
  display_src: string | null
  original_download_url: string | null
}

export type RunGridCell = {
  x: number
  y: number
  status: GridCellStatus
  blurhash: string | null
  seed: number | null
  prompt_hash: string | null
  positive_prompt: string | null
  generation_params: {
    width?: number | null
    height?: number | null
    steps?: number | null
    cfg?: number | null
    sampler_name?: string | null
  }
  items: RunGridCellItem[]
}

type VirtualGridProps = {
  runDir: string
  meta: RunGridMeta
}

const CELL_MIN_WIDTH = 184
const LEFT_COLUMN_WIDTH = 220
const DEV_IMAGE_DOM_CAP_NOTE = 300

const CELL_PADDING_PX = 8
const CELL_GAP_PX = 4
const CELL_META_HEIGHT_PX = 28

function getPreferredAspectRatio(cells: Record<string, RunGridCell>): number {
  for (const cell of Object.values(cells)) {
    const width = cell.generation_params?.width
    const height = cell.generation_params?.height

    if (
      typeof width === "number" &&
      typeof height === "number" &&
      Number.isFinite(width) &&
      Number.isFinite(height) &&
      width > 0 &&
      height > 0
    ) {
      return height / width
    }
  }

  return 1
}

const STATUS_LABELS: Record<GridCellStatus, string> = {
  success: "成功",
  failed: "失败",
  skipped: "跳过",
  missing: "缺失",
}

type SelectedCellPreview = {
  xIndex: number
  yIndex: number
  xLabel: string
  yLabel: string
  seed: number | null
  positivePrompt: string
  generationParams: RunGridCell["generation_params"]
  items: RunGridCellItem[]
}

function getGridCell(
  cells: Record<string, RunGridCell>,
  xIndex: number,
  yIndex: number,
): RunGridCell | null {
  return cells[`${xIndex},${yIndex}`] ?? null
}



function formatValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "-" : String(value)
}

export function VirtualGrid({ runDir, meta }: VirtualGridProps) {
  const scrollElementRef = useRef<HTMLDivElement | null>(null)
  const [scrollViewportWidth, setScrollViewportWidth] = useState<number | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedCell, setSelectedCell] = useState<SelectedCellPreview | null>(null)
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [copiedField, setCopiedField] = useState<"prompt" | "seed" | null>(null)

  const [cells, setCells] = useState<Record<string, RunGridCell>>({})
  const [loadedRows, setLoadedRows] = useState<Map<number, boolean>>(new Map())
  const loadedRowsRef = useRef<Map<number, boolean>>(new Map())
  const inFlightRequests = useRef<Set<string>>(new Set())

  const xHeaders = useMemo(() => {
    return meta.xColumns.map((col, index) => {
      const label = String(col.label ?? "")
      const key = typeof col.original_x_index === "number" ? String(col.original_x_index) : String(index)
      return { label, key, xIndex: index }
    })
  }, [meta.xColumns])

  useEffect(() => {
    const element = scrollElementRef.current
    if (!element) {
      return
    }

    const update = () => {
      setScrollViewportWidth(element.clientWidth)
    }

    update()

    const observer = new ResizeObserver(() => {
      update()
    })

    observer.observe(element)

    return () => {
      observer.disconnect()
    }
  }, [])

  const preferredAspectRatio = useMemo(
    () => getPreferredAspectRatio(cells),
    [cells],
  )

  const cellWidth = useMemo(() => {
    if (!scrollViewportWidth || scrollViewportWidth <= 0) {
      return CELL_MIN_WIDTH
    }

    const xCount = Math.max(1, meta.x_count)
    const available = scrollViewportWidth - LEFT_COLUMN_WIDTH

    if (available <= 0) {
      return CELL_MIN_WIDTH
    }

    return Math.max(CELL_MIN_WIDTH, Math.floor(available / xCount))
  }, [meta.x_count, scrollViewportWidth])

  const previewHeight = useMemo(() => {
    const innerWidth = Math.max(1, cellWidth - CELL_PADDING_PX * 2)
    return Math.max(32, Math.round(innerWidth * preferredAspectRatio))
  }, [cellWidth, preferredAspectRatio])

  const rowHeight = useMemo(() => {
    return CELL_PADDING_PX * 2 + previewHeight + CELL_GAP_PX + CELL_META_HEIGHT_PX
  }, [previewHeight])

  // TanStack Virtual's hook returns functions that React Compiler can't memoize safely.
  // We intentionally keep virtualization here for performance.
  const rowVirtualizer = useVirtualizer({
    count: meta.y_count,
    getScrollElement: () => scrollElementRef.current,
    estimateSize: () => rowHeight,
    overscan: 4,
  })

  const gridTemplateColumns = useMemo(
    () => `${LEFT_COLUMN_WIDTH}px repeat(${meta.x_count}, ${cellWidth}px)`,
    [cellWidth, meta.x_count],
  )
  const gridMinWidth = LEFT_COLUMN_WIDTH + meta.x_count * CELL_MIN_WIDTH
  const virtualRows = rowVirtualizer.getVirtualItems()
  const isDevEnv = process.env.NODE_ENV !== "production"
  const currentItem = selectedCell?.items[currentImageIndex] ?? null
  const currentImageSrc = currentItem?.display_src ?? currentItem?.thumb_src ?? null
  const totalImages = selectedCell?.items.length ?? 0
  const sizeText =
    selectedCell?.generationParams?.width !== null &&
    selectedCell?.generationParams?.width !== undefined &&
    selectedCell?.generationParams?.height !== null &&
    selectedCell?.generationParams?.height !== undefined
      ? `${selectedCell.generationParams.width}×${selectedCell.generationParams.height}`
      : "-"

  useEffect(() => {
    if (!dialogOpen) {
      setCopiedField(null)
      setCurrentImageIndex(0)
    }
  }, [dialogOpen])

  useEffect(() => {
    if (rowHeight > 0) {
      rowVirtualizer.measure()
    }
  }, [rowHeight, rowVirtualizer])

  useEffect(() => {
    const _resetKey = `${runDir}:${meta.x_count}:${meta.y_count}`
    if (_resetKey) {
      setCells({})
      setLoadedRows(new Map())
      loadedRowsRef.current = new Map()
      inFlightRequests.current.clear()
    }
  }, [runDir, meta])

  useEffect(() => {
    if (virtualRows.length === 0) return

    const minVisible = virtualRows[0].index
    const maxVisible = virtualRows[virtualRows.length - 1].index

    const y_from = Math.max(0, minVisible - 4)
    const y_to = Math.min(meta.y_count - 1, maxVisible + 4)

    const rowsToFetch: number[] = []
    for (let y = y_from; y <= y_to; y++) {
      if (!loadedRowsRef.current.has(y)) {
        rowsToFetch.push(y)
      }
    }

    if (rowsToFetch.length === 0) return

    const abortController = new AbortController()

    const fetchChunks = async () => {
      let current_from = y_from
      while (current_from <= y_to) {
        const current_to = Math.min(current_from + 29, y_to)
        const reqKey = `${current_from}-${current_to}`

        if (!inFlightRequests.current.has(reqKey)) {
          let allLoaded = true
          for (let y = current_from; y <= current_to; y++) {
            if (!loadedRowsRef.current.has(y)) {
              allLoaded = false
              break
            }
          }

          if (!allLoaded) {
            inFlightRequests.current.add(reqKey)
            try {
              const res = await fetch(
                `/api/comfyui/run/${encodeURIComponent(runDir)}/grid/chunk?y_from=${current_from}&y_to=${current_to}`,
                { signal: abortController.signal }
              )
              if (res.ok) {
                const data = (await res.json()) as { cells?: RunGridCell[] }
                const fetchedCells = data?.cells
                if (Array.isArray(fetchedCells)) {
                  setCells((prev) => {
                    const next = { ...prev }
                    for (const cell of fetchedCells) {
                      next[`${cell.x},${cell.y}`] = cell
                    }
                    return next
                  })
                  setLoadedRows((prev) => {
                    const next = new Map(prev)
                    for (let y = current_from; y <= current_to; y++) {
                      next.set(y, true)
                    }
                    loadedRowsRef.current = next
                    return next
                  })
                }
              }
            } catch (err) {
              if (err instanceof DOMException && err.name === "AbortError") {
                // ignore
              }
            } finally {
              inFlightRequests.current.delete(reqKey)
            }
          }
        }
        current_from = current_to + 1
      }
    }

    void fetchChunks()

    return () => {
      abortController.abort()
    }
  }, [virtualRows, meta.y_count, runDir])

  const openCellDialog = useCallback(
    (cell: RunGridCell, xIndex: number, yIndex: number, xLabel: string, yLabel: string) => {
      setSelectedCell({
        xIndex,
        yIndex,
        xLabel,
        yLabel,
        seed: cell.seed,
        positivePrompt:
          typeof cell.positive_prompt === "string" && cell.positive_prompt.trim().length > 0
            ? cell.positive_prompt
            : "（无 positive prompt）",
        generationParams: cell.generation_params,
        items: cell.items || [],
      })
      setCurrentImageIndex(0)
      setDialogOpen(true)
    },
    [],
  )

  const copyText = useCallback(async (field: "prompt" | "seed", value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopiedField(field)
    } catch {
      setCopiedField(null)
    }
  }, [])

  const showPreviousImage = useCallback(() => {
    setCurrentImageIndex((index) => {
      if (index <= 0) {
        return 0
      }

      return index - 1
    })
  }, [])

  const showNextImage = useCallback(() => {
    setCurrentImageIndex((index) => {
      if (!selectedCell || index >= selectedCell.items.length - 1) {
        return index
      }

      return index + 1
    })
  }, [selectedCell])

  return (
    <div
      className="flex h-full min-h-0 flex-col overflow-hidden border"
      data-testid="run-grid"
      data-row-count={meta.y_count}
      data-row-height={rowHeight}
    >
      {isDevEnv ? (
        <div
          className="text-muted-foreground border-b px-3 py-1 text-[10px]"
          data-testid="run-grid-dev-debug"
        >
          {`dev: rendered rows ${virtualRows.length}, img cap target < ${DEV_IMAGE_DOM_CAP_NOTE}`}
        </div>
      ) : null}

      <div
        ref={scrollElementRef}
        className="relative min-h-0 flex-1 overflow-auto"
        data-testid="run-grid-scroll"
      >
        <div className="relative" style={{ minWidth: gridMinWidth }}>
          <div className="bg-background/95 sticky top-0 z-30 border-b backdrop-blur supports-[backdrop-filter]:bg-background/80">
            <div className="grid" style={{ gridTemplateColumns }}>
              <div
                className="bg-background sticky left-0 z-40 border-r px-3 py-2 text-xs font-semibold"
                data-testid="run-grid-corner"
              >
                Y\X
              </div>
              {xHeaders.map(({ label: xLabel, key, xIndex }) => (
                <div
                  key={key}
                  className="border-r px-3 py-2 text-xs font-semibold"
                >
                  <p className="truncate">{`X${xIndex}`}</p>
                  <p className="text-muted-foreground mt-1 truncate text-[10px] font-normal">
                    {xLabel}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="relative" style={{ height: rowVirtualizer.getTotalSize() }}>
            {virtualRows.map((virtualRow) => {
              const yIndex = virtualRow.index
              const yLabel = meta.yLabels[yIndex] ?? `Y${yIndex}`

              return (
                <div
                  key={virtualRow.key}
                  className="absolute left-0 top-0 w-full border-b"
                  data-testid="run-grid-row"
                  data-row-index={yIndex}
                  style={{
                    height: virtualRow.size,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <div className="grid h-full" style={{ gridTemplateColumns }}>
                    <div
                      className="bg-background sticky left-0 z-20 flex h-full border-r px-3 py-2 text-xs"
                      data-testid="run-grid-y-label"
                    >
                      <div>
                        <p className="font-semibold">{`Y${yIndex}`}</p>
                        <p className="text-muted-foreground mt-1 line-clamp-3 text-[10px]">
                          {yLabel}
                        </p>
                      </div>
                    </div>

                    {xHeaders.map(({ label: xLabel, key, xIndex }) => {
                      const isLoaded = loadedRows.has(yIndex)
                      const cell = getGridCell(cells, xIndex, yIndex)
                      const status = isLoaded ? (cell?.status ?? "missing") : "loading"
                      const firstItem = cell?.items?.[0]
                      const imageSrc = status === "success" ? (firstItem?.thumb_src ?? firstItem?.display_src ?? null) : null
                      const placeholderLabel =
                        status === "success" ? "无图" : status === "loading" ? "加载中..." : STATUS_LABELS[status as GridCellStatus]

                      const canOpenDialog = status === "success" && cell !== null
                      const previewNode = imageSrc ? (
                        <div
                          className="relative w-full rounded border"
                          style={{ height: previewHeight }}
                        >
                          <Image
                            alt={`${yLabel} × ${xLabel}`}
                            className="object-contain"
                            data-testid="run-grid-image"
                            fill
                            loading="lazy"
                            sizes={`${Math.max(1, cellWidth)}px`}
                            src={imageSrc}
                            unoptimized
                          />
                        </div>
                      ) : (
                        <div
                          className="bg-muted/40 text-muted-foreground flex items-center justify-center rounded border border-dashed text-[10px] font-medium"
                          data-testid="run-grid-placeholder"
                          style={{ height: previewHeight }}
                        >
                          {placeholderLabel}
                        </div>
                      )

                      return (
                        <div
                          key={`${key}-${yIndex}`}
                          className="flex h-full flex-col gap-1 border-r p-2"
                        >
                          {canOpenDialog && cell ? (
                            <button
                              type="button"
                              aria-label={`打开单元格 X${xIndex} Y${yIndex} 预览`}
                              className="focus-visible:ring-ring rounded text-left focus-visible:outline-none focus-visible:ring-2"
                              onClick={() => {
                                openCellDialog(cell, xIndex, yIndex, xLabel, yLabel)
                              }}
                            >
                              {previewNode}
                            </button>
                          ) : (
                            previewNode
                          )}

                          <div className="space-y-0.5 text-[10px] leading-tight">
                            <p className="truncate font-medium">{`X${xIndex} · Y${yIndex}`}</p>
                            {cell?.seed !== null && cell?.seed !== undefined ? (
                              <p className="text-muted-foreground truncate">{`seed ${cell.seed}`}</p>
                            ) : null}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent
          className="max-h-[90vh] overflow-auto p-4 sm:max-w-4xl"
          data-testid="cell-dialog"
        >
          <DialogHeader>
            <DialogTitle>{`单元格 X${selectedCell?.xIndex ?? "-"} · Y${selectedCell?.yIndex ?? "-"}`}</DialogTitle>
            <DialogDescription>
              {selectedCell ? `${selectedCell.yLabel} × ${selectedCell.xLabel}` : "-"}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="space-y-2">
              {currentImageSrc ? (
                <div className="bg-muted/20 relative h-[62vh] w-full rounded border">
                  <Image
                    alt={selectedCell ? `${selectedCell.yLabel} × ${selectedCell.xLabel}` : "cell preview"}
                    className="object-contain"
                    fill
                    sizes="100vw"
                    src={currentImageSrc}
                    unoptimized
                  />
                </div>
              ) : (
                <div className="bg-muted/30 text-muted-foreground flex min-h-64 items-center justify-center rounded border border-dashed text-xs">
                  当前单元格无可用图片
                </div>
              )}

              {totalImages > 1 ? (
                <div className="flex items-center justify-between gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={showPreviousImage}
                    disabled={currentImageIndex <= 0}
                  >
                    上一张
                  </Button>
                  <p className="text-muted-foreground text-xs">{`${currentImageIndex + 1}/${totalImages}`}</p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={showNextImage}
                    disabled={currentImageIndex >= totalImages - 1}
                  >
                    下一张
                  </Button>
                </div>
              ) : null}
            </div>

            <div className="space-y-4">
              <div className="space-y-1">
                <p className="text-muted-foreground text-xs font-medium">positive prompt</p>
                <p
                  className="bg-muted/30 max-h-52 overflow-auto rounded border p-2 text-xs whitespace-pre-wrap"
                  data-testid="cell-dialog-prompt"
                >
                  {selectedCell?.positivePrompt ?? "（无 positive prompt）"}
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  data-testid="cell-dialog-copy-prompt"
                  onClick={() => {
                    void copyText("prompt", selectedCell?.positivePrompt ?? "")
                  }}
                  disabled={!selectedCell}
                >
                  {copiedField === "prompt" ? "已复制 prompt" : "复制 prompt"}
                </Button>
              </div>

              <div className="space-y-2 text-xs">
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">seed</p>
                  <p data-testid="cell-dialog-seed">{formatValue(selectedCell?.seed)}</p>
                </div>
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">steps</p>
                  <p>{formatValue(selectedCell?.generationParams?.steps)}</p>
                </div>
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">cfg</p>
                  <p>{formatValue(selectedCell?.generationParams?.cfg)}</p>
                </div>
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">sampler</p>
                  <p>{formatValue(selectedCell?.generationParams?.sampler_name)}</p>
                </div>
                <div className="grid grid-cols-[64px_1fr] gap-2">
                  <p className="text-muted-foreground">size</p>
                  <p>{sizeText}</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  data-testid="cell-dialog-copy-seed"
                  onClick={() => {
                    void copyText(
                      "seed",
                      selectedCell && selectedCell.seed !== null
                        ? String(selectedCell.seed)
                        : "",
                    )
                  }}
                  disabled={!selectedCell || selectedCell.seed === null}
                >
                  {copiedField === "seed" ? "已复制 seed" : "复制 seed"}
                </Button>

                {currentItem?.original_download_url ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={currentItem.original_download_url} download>
                      下载原图
                    </a>
                  </Button>
                ) : (
                  <Button size="sm" variant="outline" disabled>
                    下载原图
                  </Button>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
