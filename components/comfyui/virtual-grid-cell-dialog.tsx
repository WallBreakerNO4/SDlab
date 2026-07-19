"use client";

import { useTranslations } from "next-intl";
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
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

import { useRenderableVariantSource } from "./use-renderable-variant-source";
import { BlurhashCanvas } from "./blurhash-canvas";
import { formatValue } from "./virtual-grid-utils";
import type { SelectedCellPreview } from "./virtual-grid-types";
import type { RunViewAccess } from "@/app/models/[runDir]/model-detail-types";

type VirtualGridCellDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cell: SelectedCellPreview | null;
  currentUserId: string | null;
  grant: string | null;
  onRefreshViewAccess: () => Promise<RunViewAccess | null>;
};

export function VirtualGridCellDialog({
  open,
  onOpenChange,
  cell,
  currentUserId,
  grant,
  onRefreshViewAccess,
}: VirtualGridCellDialogProps) {
  "use no memo";

  const t = useTranslations("cellDialog");
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [copiedField, setCopiedField] = useState<"prompt" | "seed" | null>(
    null,
  );
  const [isDialogImageLoaded, setIsDialogImageLoaded] = useState(false);

  const prevCellKeyRef = useRef<string | null>(null);
  const cellKey = cell ? `${cell.xIndex}:${cell.yIndex}` : null;

  const totalImages = cell?.items.length ?? 0;
  const currentItem = cell?.items[currentImageIndex] ?? null;
  const currentDisplayVariants = currentItem?.display ?? null;
  const currentPreviewVariants = currentItem?.thumb ?? null;
  const currentDisplayCacheVariants = currentItem?.display ?? null;
  const previewWasLoaded = Boolean(currentItem?.thumbLoaded);
  const { src: currentPreviewUrl } = useRenderableVariantSource({
    variants: currentPreviewVariants,
    currentUserId,
    grant,
    onRefreshViewAccess,
  });
  const { src: cachedDisplayUrl } = useRenderableVariantSource({
    variants: currentDisplayCacheVariants,
    currentUserId,
    grant,
    onRefreshViewAccess,
    cacheOnly: true,
  });
  const { src: fetchedDisplayUrl } = useRenderableVariantSource({
    variants: currentDisplayVariants,
    currentUserId,
    grant,
    onRefreshViewAccess,
  });
  const currentDownloadUrl = fetchedDisplayUrl ?? cachedDisplayUrl ?? null;
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
      setIsDialogImageLoaded(false);
    }
  }, [cellKey]);

  useEffect(() => {
    if (!open) {
      setCopiedField(null);
      setCurrentImageIndex(0);
      setIsDialogImageLoaded(false);
    }
  }, [open]);

  const showPreviousImage = useCallback(() => {
    if (currentImageIndex <= 0) {
      return;
    }

    setIsDialogImageLoaded(false);
    setCurrentImageIndex((index) => Math.max(0, index - 1));
  }, [currentImageIndex]);

  const showNextImage = useCallback(() => {
    if (!cell || currentImageIndex >= cell.items.length - 1) {
      return;
    }

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

  const displayPrompt = cell?.positivePrompt ?? t("noPositivePrompt");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[90vh] overflow-auto p-4 sm:max-w-4xl sm:p-6"
        data-testid="cell-dialog"
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription className="sr-only">
            {t("title")}
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
              {!isDialogImageLoaded ? (
                <div className="absolute right-3 bottom-3 z-10 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1.5 text-xs text-white backdrop-blur-md pointer-events-none transition-opacity duration-300">
                  <Spinner className="h-3 w-3" />
                  <span>{t("loading")}</span>
                </div>
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
                  {t("prevImage")}
                </Button>
                <p className="text-muted-foreground text-xs">{t("imageCount", { current: currentImageIndex + 1, total: totalImages })}</p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={showNextImage}
                  disabled={currentImageIndex >= totalImages - 1}
                >
                  {t("nextImage")}
                </Button>
              </div>
            ) : null}
          </div>

          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <p className="text-muted-foreground text-xs font-medium">
                  {t("positivePrompt")}
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
                  title={t("copyPrompt")}
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
                {displayPrompt}
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-muted-foreground text-xs font-medium">
                {t("parameters")}
              </p>
              <div className="bg-muted/20 rounded-md border p-3 text-xs">
                <div className="flex flex-col gap-y-4">
                  <div className="space-y-1.5">
                    <p className="text-muted-foreground font-medium">{t("seed")}</p>
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
                        title={t("copySeed")}
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
                    <p className="text-muted-foreground font-medium">{t("size")}</p>
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
                    {t("downloadImage")}
                  </a>
                </Button>
              ) : (
                <Button className="w-full" size="sm" disabled>
                  <HugeiconsIcon
                    icon={Download01Icon}
                    className="mr-2 h-4 w-4"
                  />
                  {t("downloadImage")}
                </Button>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
