import { GridImage } from "./grid-image";
import { pickBestVariants } from "./virtual-grid-utils";
import type {
  BlurhashCell,
  CachedRow,
  RowCell,
} from "./virtual-grid-types";

type VirtualGridPreviewCellProps = {
  xKey: string;
  xIndex: number;
  xLabel: string;
  yIndex: number;
  yLabel: string;
  rowEntry: CachedRow | undefined;
  blurhashMap: Map<string, BlurhashCell>;
  previewHeight: number;
  isAuthenticated: boolean;
  currentUserId: string | null;
  grant: string | null;
  onRequireLogin: () => void;
  onOpenCellDialog: (
    cell: RowCell,
    xIndex: number,
    yIndex: number,
    xLabel: string,
    yLabel: string,
    preloadedBlurhash: string | null,
  ) => void;
  onThumbLoad: (cacheKey: string) => void;
};

export function VirtualGridPreviewCell({
  xKey,
  xIndex,
  xLabel,
  yIndex,
  yLabel,
  rowEntry,
  blurhashMap,
  previewHeight,
  isAuthenticated,
  currentUserId,
  grant,
  onRequireLogin,
  onOpenCellDialog,
  onThumbLoad,
}: VirtualGridPreviewCellProps) {
  const rowCell =
    rowEntry && rowEntry.status === "ready"
      ? (rowEntry.cellsByX.get(xIndex) ?? null)
      : null;
  const representativeItem =
    rowCell?.items.find((item) => pickBestVariants(item.thumb, null)) ??
    rowCell?.items[0] ??
    null;
  const thumbVariants = representativeItem
    ? pickBestVariants(representativeItem.thumb, null)
    : null;

  const preloadedCell = blurhashMap.get(`${xIndex}:${yIndex}`);
  const effectiveBlurhash =
    preloadedCell?.blurhash ?? representativeItem?.blurhash ?? null;
  const effectiveCategory =
    preloadedCell?.category ?? representativeItem?.category ?? null;

  const canOpenDialog = !!rowCell && rowCell.items.length > 0;
  const isLocked =
    !isAuthenticated &&
    effectiveCategory !== null &&
    effectiveCategory !== "normal";

  const hasBlurhash = !!effectiveBlurhash;
  const showImage = !!thumbVariants || hasBlurhash;

  const placeholderLabel =
    rowEntry && rowEntry.status === "error"
      ? "加载失败"
      : rowEntry
        ? "缺失"
        : "加载中";

  const previewNode = showImage ? (
    <div
      className="w-full rounded border border-border/40 overflow-hidden relative"
      style={{ height: previewHeight }}
    >
      <div className="w-full h-full transition-transform duration-500 ease-out group-hover/cell:scale-[1.03]">
        <GridImage
          thumbVariants={thumbVariants}
          blurhash={effectiveBlurhash}
          alt={
            yLabel && xLabel ? `${yLabel} × ${xLabel}` : yLabel || xLabel || "图片预览"
          }
          currentUserId={currentUserId}
          grant={grant}
          locked={isLocked}
          onLockedClick={onRequireLogin}
          onImageLoaded={onThumbLoad}
        />
      </div>
      <div className="absolute inset-0 bg-foreground/0 transition-colors duration-300 pointer-events-none group-hover/cell:bg-foreground/5" />
    </div>
  ) : (
    <div
      className="bg-muted/40 text-muted-foreground flex items-center justify-center rounded border border-border/40 border-dashed text-[10px] font-medium"
      data-testid="run-grid-placeholder"
      style={{ height: previewHeight }}
    >
      {placeholderLabel}
    </div>
  );

  return (
    <div
      key={`${xKey}-${yIndex}`}
      className="flex h-full flex-col border-r border-border/40 p-2 transition-colors hover:bg-muted/20 group/cell"
    >
      {canOpenDialog && !isLocked ? (
        <button
          type="button"
          aria-label="打开单元格预览"
          className="focus-visible:ring-ring rounded text-left focus-visible:outline-none focus-visible:ring-2"
          onClick={() => {
            if (!rowCell) return;
            onOpenCellDialog(
              rowCell,
              xIndex,
              yIndex,
              xLabel,
              yLabel,
              effectiveBlurhash,
            );
          }}
        >
          {previewNode}
        </button>
      ) : (
        previewNode
      )}
    </div>
  );
}
