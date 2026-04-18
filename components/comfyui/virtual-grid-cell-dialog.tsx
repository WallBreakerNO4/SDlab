"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Copy01Icon,
  Download01Icon,
  Tick01Icon,
} from "@hugeicons/core-free-icons";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import { BlurhashCanvas } from "./blurhash-canvas";
import { formatValue, parseDialogImagePayload } from "./virtual-grid-utils";
import type { SelectedCellPreview, VariantUrls } from "./virtual-grid-types";

type VirtualGridCellDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cell: SelectedCellPreview | null;
  runDir: string;
  currentUserId: string | null;
};

export function VirtualGridCellDialog({
  open,
  onOpenChange,
  cell,
  runDir,
  currentUserId,
}: VirtualGridCellDialogProps) {
  "use no memo";

  const dialogImageRequestRef = useRef<AbortController | null>(null);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [copiedField, setCopiedField] = useState<"prompt" | "seed" | null>(
    null,
  );
  const [dialogImageVariants, setDialogImageVariants] =
    useState<VariantUrls | null>(null);
  const [isDialogImageLoaded, setIsDialogImageLoaded] = useState(false);

  const prevCellKeyRef = useRef<string | null>(null);
  const cellKey = cell ? `${cell.xIndex}:${cell.yIndex}` : null;

  const totalImages = cell?.items.length ?? 0;
  const currentItem = cell?.items[currentImageIndex] ?? null;
  const selectedXIndex = cell?.xIndex ?? null;
  const selectedYIndex = cell?.yIndex ?? null;
  const currentBatchIndex = currentItem?.batchIndex ?? null;
  const currentDisplayVariants = dialogImageVariants;
  const currentPreviewVariants = currentItem?.thumb ?? null;
  const previewWasLoaded = Boolean(currentItem?.thumbLoaded);
  const currentPreviewUrl =
    currentPreviewVariants?.webp ?? currentPreviewVariants?.avif ?? null;
  const currentDownloadUrl =
    currentDisplayVariants?.webp ?? currentDisplayVariants?.avif ?? null;
  const showPreviewPlaceholder = previewWasLoaded && !!currentPreviewUrl;
  const dialogAlt =
    cell && (cell.yLabel || cell.xLabel)
      ? [cell.yLabel, cell.xLabel].filter(Boolean).join(" × ")
      : "cell preview";
  const sizeText =
    currentItem &&
    typeof currentItem.width === "number" &&
    typeof currentItem.height === "number" &&
    Number.isFinite(currentItem.width) &&
    Number.isFinite(currentItem.height)
      ? `${currentItem.width}×${currentItem.height}`
      : "-";

  useEffect(() => {
    if (cellKey !== prevCellKeyRef.current) {
      prevCellKeyRef.current = cellKey;
      setCurrentImageIndex(0);
      setDialogImageVariants(null);
      setIsDialogImageLoaded(false);
    }
  }, [cellKey]);

  useEffect(() => {
    if (!open) {
      dialogImageRequestRef.current?.abort();
      dialogImageRequestRef.current = null;
      setCopiedField(null);
      setCurrentImageIndex(0);
      setDialogImageVariants(null);
      setIsDialogImageLoaded(false);
    }
  }, [open]);

  useEffect(() => {
    return () => {
      dialogImageRequestRef.current?.abort();
      dialogImageRequestRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (
      !open ||
      selectedXIndex === null ||
      selectedYIndex === null ||
      currentBatchIndex === null
    ) {
      return;
    }

    let ignore = false;
    dialogImageRequestRef.current?.abort();
    setDialogImageVariants(null);
    setIsDialogImageLoaded(false);

    const controller = new AbortController();
    dialogImageRequestRef.current = controller;

    async function loadDialogImage() {
      try {
        const response = await fetch(
          `/api/comfyui/run/${encodeURIComponent(runDir)}/display?x_index=${encodeURIComponent(String(selectedXIndex))}&y_index=${encodeURIComponent(String(selectedYIndex))}&batch_index=${encodeURIComponent(String(currentBatchIndex))}`,
          {
            cache: "no-store",
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          return;
        }

        const raw: unknown = await response.json();
        const image = parseDialogImagePayload(raw);
        if (!ignore && image) {
          setDialogImageVariants(image);
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
      } finally {
        if (dialogImageRequestRef.current === controller) {
          dialogImageRequestRef.current = null;
        }
      }
    }

    void loadDialogImage();

    return () => {
      ignore = true;
      controller.abort();
      if (dialogImageRequestRef.current === controller) {
        dialogImageRequestRef.current = null;
      }
    };
  }, [currentBatchIndex, currentUserId, open, runDir, selectedXIndex, selectedYIndex]);

  const showPreviousImage = useCallback(() => {
    if (currentImageIndex <= 0) {
      return;
    }

    setDialogImageVariants(null);
    setIsDialogImageLoaded(false);
    setCurrentImageIndex((index) => Math.max(0, index - 1));
  }, [currentImageIndex]);

  const showNextImage = useCallback(() => {
    if (!cell || currentImageIndex >= cell.items.length - 1) {
      return;
    }

    setDialogImageVariants(null);
    setIsDialogImageLoaded(false);
    setCurrentImageIndex((index) => index + 1);
  }, [currentImageIndex, cell]);

  const copyText = useCallback(
    async (field: "prompt" | "seed", value: string) => {
      try {
        await navigator.clipboard.writeText(value);
        setCopiedField(field);
        setTimeout(() => {
          setCopiedField((current) => (current === field ? null : current));
        }, 2000);
      } catch {
        setCopiedField(null);
      }
    },
    [],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] overflow-auto p-4 sm:max-w-4xl sm:p-6"
        data-testid="cell-dialog"
      >
        <DialogHeader className="sr-only">
          <DialogTitle>单元格预览</DialogTitle>
          <DialogDescription className="sr-only">
            单元格图片预览
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="space-y-2">
            <div className="relative h-[62vh] w-full rounded-sm border bg-black overflow-hidden flex items-center justify-center">
              {currentItem?.blurhash ? (
                <BlurhashCanvas
                  blurhash={currentItem.blurhash}
                  width={(() => {
                    const ratio =
                      (currentItem.width ?? 1) / (currentItem.height ?? 1);
                    return ratio > 1
                      ? 32
                      : Math.max(1, Math.round(32 * ratio));
                  })()}
                  height={(() => {
                    const ratio =
                      (currentItem.width ?? 1) / (currentItem.height ?? 1);
                    return ratio > 1
                      ? Math.max(1, Math.round(32 / ratio))
                      : 32;
                  })()}
                  className={cn(
                    "absolute inset-0 m-auto h-full w-full object-contain blur-md transition-opacity duration-500",
                    isDialogImageLoaded || showPreviewPlaceholder
                      ? "opacity-0"
                      : "opacity-100",
                  )}
                />
              ) : null}
              {showPreviewPlaceholder ? (
                <picture className="absolute inset-0 h-full w-full pointer-events-none">
                  {currentPreviewVariants?.avif ? (
                    <source
                      srcSet={currentPreviewVariants.avif}
                      type="image/avif"
                    />
                  ) : null}
                  {currentPreviewVariants?.webp ? (
                    <source
                      srcSet={currentPreviewVariants.webp}
                      type="image/webp"
                    />
                  ) : null}
                  <img
                    alt={dialogAlt}
                    className={cn(
                      "h-full w-full object-contain transition-opacity duration-500",
                      isDialogImageLoaded ? "opacity-0" : "opacity-100",
                    )}
                    data-testid="cell-dialog-preview-image"
                    decoding="async"
                    src={currentPreviewUrl}
                  />
                </picture>
              ) : null}
              {currentDownloadUrl ? (
                <picture className="absolute inset-0 h-full w-full pointer-events-none">
                  {currentDisplayVariants?.avif ? (
                    <source
                      srcSet={currentDisplayVariants.avif}
                      type="image/avif"
                    />
                  ) : null}
                  {currentDisplayVariants?.webp ? (
                    <source
                      srcSet={currentDisplayVariants.webp}
                      type="image/webp"
                    />
                  ) : null}
                  <img
                    alt={dialogAlt}
                    className={cn(
                      "h-full w-full object-contain transition-opacity duration-500 pointer-events-auto",
                      isDialogImageLoaded ? "opacity-100" : "opacity-0",
                    )}
                    data-testid="cell-dialog-display-image"
                    decoding="async"
                    src={currentDownloadUrl}
                    onLoad={() => setIsDialogImageLoaded(true)}
                  />
                </picture>
              ) : null}
            </div>

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

          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <p className="text-muted-foreground text-xs font-medium">
                  Positive Prompt
                </p>
                <Button
                  type="button"
                  size="icon-xs"
                  variant="ghost"
                  className="h-6 w-6 text-muted-foreground hover:text-foreground"
                  data-testid="cell-dialog-copy-prompt"
                  onClick={() => {
                    void copyText("prompt", cell?.positivePrompt ?? "");
                  }}
                  disabled={!cell}
                  title="复制 Prompt"
                >
                  {copiedField === "prompt" ? (
                    <HugeiconsIcon icon={Tick01Icon} className="h-3 w-3" />
                  ) : (
                    <HugeiconsIcon icon={Copy01Icon} className="h-3 w-3" />
                  )}
                </Button>
              </div>
              <div
                className="bg-muted/30 max-h-64 overflow-auto rounded-md border p-3 text-xs leading-relaxed whitespace-pre-wrap"
                data-testid="cell-dialog-prompt"
              >
                {cell?.positivePrompt ?? "（无 positive prompt）"}
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-muted-foreground text-xs font-medium">
                Parameters
              </p>
              <div className="bg-muted/20 rounded-md border p-3 text-xs">
                <div className="flex flex-col gap-y-4">
                  <div className="space-y-1.5">
                    <p className="text-muted-foreground font-medium">Seed</p>
                    <div className="group flex items-start gap-2">
                      <p
                        className="break-all font-mono"
                        data-testid="cell-dialog-seed"
                      >
                        {formatValue(cell?.seed)}
                      </p>
                      <Button
                        type="button"
                        size="icon-xs"
                        variant="ghost"
                        className="h-5 w-5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                        data-testid="cell-dialog-copy-seed"
                        onClick={() => {
                          void copyText(
                            "seed",
                            cell && cell.seed !== null
                              ? String(cell.seed)
                              : "",
                          );
                        }}
                        disabled={!cell || cell.seed === null}
                        title="复制 Seed"
                      >
                        {copiedField === "seed" ? (
                          <HugeiconsIcon icon={Tick01Icon} className="h-3 w-3" />
                        ) : (
                          <HugeiconsIcon icon={Copy01Icon} className="h-3 w-3" />
                        )}
                      </Button>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <p className="text-muted-foreground font-medium">Size</p>
                    <p className="font-mono">{sizeText}</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-auto pt-4">
              {currentDownloadUrl ? (
                <Button asChild className="w-full" size="sm">
                  <a href={currentDownloadUrl} download>
                    <HugeiconsIcon
                      icon={Download01Icon}
                      className="mr-2 h-4 w-4"
                    />
                    下载图片
                  </a>
                </Button>
              ) : (
                <Button className="w-full" size="sm" disabled>
                  <HugeiconsIcon
                    icon={Download01Icon}
                    className="mr-2 h-4 w-4"
                  />
                  下载图片
                </Button>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
