"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { useVirtualizer } from "@tanstack/react-virtual"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type GridCellStatus = "success" | "failed" | "skipped" | "missing"

export type RunGridCell = {
  status: GridCellStatus
  x_index: number
  y_index: number
  local_image_path: string | null
  local_image_paths?: string[]
  seed: number | null
  prompt_hash: string | null
  positive_prompt?: string | null
  generation_params?: {
    width: number | null
    height: number | null
    steps: number | null
    cfg: number | null
    sampler_name: string | null
  }
}

export type RunGridData = {
  xLabels: string[]
  yLabels: string[]
  cells: Record<string, RunGridCell>
}

type VirtualGridProps = {
  runDir: string
  grid: RunGridData
}

const ROW_HEIGHT = 140
const CELL_WIDTH = 184
const LEFT_COLUMN_WIDTH = 220
const DEV_IMAGE_DOM_CAP_NOTE = 300

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
  imagePaths: string[]
}

function getGridCell(
  cells: Record<string, RunGridCell>,
  xIndex: number,
  yIndex: number,
): RunGridCell | null {
  return cells[`${xIndex},${yIndex}`] ?? null
}

function toImageSrc(runDir: string, localImagePath: string): string {
  const encodedPath = localImagePath
    .split("/")
    .filter((segment) => segment.length > 0)
    .map((segment) => encodeURIComponent(segment))
    .join("/")

  return `/api/comfyui/image/${encodeURIComponent(runDir)}/${encodedPath}`
}

function getCellImagePaths(cell: RunGridCell): string[] {
  const paths = Array.isArray(cell.local_image_paths)
    ? cell.local_image_paths.filter((path) => path.length > 0)
    : []

  if (cell.local_image_path && cell.local_image_path.length > 0 && !paths.includes(cell.local_image_path)) {
    return [cell.local_image_path, ...paths]
  }

  if (paths.length > 0) {
    return paths
  }

  return cell.local_image_path && cell.local_image_path.length > 0
    ? [cell.local_image_path]
    : []
}

function formatValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "-" : String(value)
}

export function VirtualGrid({ runDir, grid }: VirtualGridProps) {
  const scrollElementRef = useRef<HTMLDivElement | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedCell, setSelectedCell] = useState<SelectedCellPreview | null>(null)
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [copiedField, setCopiedField] = useState<"prompt" | "seed" | null>(null)

  const rowVirtualizer = useVirtualizer({
    count: grid.yLabels.length,
    getScrollElement: () => scrollElementRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 4,
  })

  const gridTemplateColumns = useMemo(
    () => `${LEFT_COLUMN_WIDTH}px repeat(${grid.xLabels.length}, ${CELL_WIDTH}px)`,
    [grid.xLabels.length],
  )
  const gridMinWidth = LEFT_COLUMN_WIDTH + grid.xLabels.length * CELL_WIDTH
  const virtualRows = rowVirtualizer.getVirtualItems()
  const isDevEnv = process.env.NODE_ENV !== "production"
  const currentImagePath = selectedCell?.imagePaths[currentImageIndex] ?? null
  const currentImageSrc =
    currentImagePath && currentImagePath.length > 0
      ? toImageSrc(runDir, currentImagePath)
      : null
  const totalImages = selectedCell?.imagePaths.length ?? 0
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

  const openCellDialog = useCallback(
    (cell: RunGridCell, xIndex: number, yIndex: number, xLabel: string, yLabel: string) => {
      const imagePaths = getCellImagePaths(cell)

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
        imagePaths,
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
      if (!selectedCell || index >= selectedCell.imagePaths.length - 1) {
        return index
      }

      return index + 1
    })
  }, [selectedCell])

  return (
    <div
      className="overflow-hidden border"
      data-testid="run-grid"
      data-row-count={grid.yLabels.length}
      data-row-height={ROW_HEIGHT}
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
        className="relative max-h-[70vh] overflow-auto"
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
              {grid.xLabels.map((xLabel, xIndex) => (
                <div
                  key={`${xLabel}-${xIndex}`}
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
              const yLabel = grid.yLabels[yIndex] ?? `Y${yIndex}`

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

                    {grid.xLabels.map((xLabel, xIndex) => {
                      const cell = getGridCell(grid.cells, xIndex, yIndex)
                      const status = cell?.status ?? "missing"
                      const localImagePath =
                        status === "success" ? cell?.local_image_path ?? null : null
                      const imageSrc =
                        localImagePath && localImagePath.length > 0
                          ? toImageSrc(runDir, localImagePath)
                          : null
                      const placeholderLabel =
                        status === "success" ? "无图" : STATUS_LABELS[status]

                      const canOpenDialog = status === "success" && cell !== null
                      const previewNode = imageSrc ? (
                        <img
                          alt={`${yLabel} × ${xLabel}`}
                          className="h-24 w-full rounded border object-cover"
                          data-testid="run-grid-image"
                          decoding="async"
                          loading="lazy"
                          src={imageSrc}
                        />
                      ) : (
                        <div
                          className="bg-muted/40 text-muted-foreground flex h-24 items-center justify-center rounded border border-dashed text-[10px] font-medium"
                          data-testid="run-grid-placeholder"
                        >
                          {placeholderLabel}
                        </div>
                      )

                      return (
                        <div
                          key={`${xIndex}-${yIndex}`}
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
                <img
                  alt={selectedCell ? `${selectedCell.yLabel} × ${selectedCell.xLabel}` : "cell preview"}
                  className="bg-muted/20 max-h-[62vh] w-full rounded border object-contain"
                  src={currentImageSrc}
                />
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

                {currentImageSrc ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={currentImageSrc} download>
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
