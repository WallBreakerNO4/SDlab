export type HorizontalModelWindowInput = {
  scrollLeft: number;
  viewportWidth: number;
  promptColumnWidth: number;
  modelColumnWidth: number;
  modelCount: number;
  overscan?: number;
};

export type HorizontalModelWindow = {
  startIndex: number;
  endIndex: number;
};

type ComparisonBlurhashTuple = readonly [
  xIndex: number,
  batchIndex: number,
  blurhash: string,
];

type ComparisonBlurhashPlacement = {
  run_dir: string;
  y_index: number;
  blurhashes?: readonly ComparisonBlurhashTuple[];
};

export type ComparisonBlurhashLookup = {
  byImage: ReadonlyMap<string, string>;
  firstByPlacement: ReadonlyMap<string, string>;
  firstByX: ReadonlyMap<string, string>;
};

export function getVariantBoundValue<T>(
  snapshot: { variantKey: string; data: T } | null,
  activeVariantKey: string,
): T | null {
  return snapshot?.variantKey === activeVariantKey ? snapshot.data : null;
}

function placementKey(runDir: string, yIndex: number): string {
  return `${runDir}\u0000${yIndex}`;
}

function xKey(runDir: string, yIndex: number, xIndex: number): string {
  return `${placementKey(runDir, yIndex)}\u0000${xIndex}`;
}

function imageKey(
  runDir: string,
  yIndex: number,
  xIndex: number,
  batchIndex: number,
): string {
  return `${xKey(runDir, yIndex, xIndex)}\u0000${batchIndex}`;
}

export function buildComparisonBlurhashLookup(
  placements: Readonly<
    Record<string, readonly ComparisonBlurhashPlacement[]>
  > | null,
): ComparisonBlurhashLookup {
  const byImage = new Map<string, string>();
  const firstByPlacement = new Map<string, string>();
  const firstByX = new Map<string, string>();

  for (const stylePlacements of Object.values(placements ?? {})) {
    for (const placement of stylePlacements) {
      const placementLookupKey = placementKey(
        placement.run_dir,
        placement.y_index,
      );
      for (const [xIndex, batchIndex, blurhash] of placement.blurhashes ?? []) {
        const imageLookupKey = imageKey(
          placement.run_dir,
          placement.y_index,
          xIndex,
          batchIndex,
        );
        if (!byImage.has(imageLookupKey)) {
          byImage.set(imageLookupKey, blurhash);
        }
        if (!firstByPlacement.has(placementLookupKey)) {
          firstByPlacement.set(placementLookupKey, blurhash);
        }
        const columnLookupKey = xKey(
          placement.run_dir,
          placement.y_index,
          xIndex,
        );
        if (!firstByX.has(columnLookupKey)) {
          firstByX.set(columnLookupKey, blurhash);
        }
      }
    }
  }

  return { byImage, firstByPlacement, firstByX };
}

export function getComparisonBlurhash(
  lookup: ComparisonBlurhashLookup,
  runDir: string,
  yIndex: number,
  xIndex: number,
  batchIndex: number,
  rowBlurhash: string | null,
): string | null {
  return (
    rowBlurhash ??
    lookup.byImage.get(imageKey(runDir, yIndex, xIndex, batchIndex)) ??
    null
  );
}

export function getComparisonPlaceholderBlurhash(
  lookup: ComparisonBlurhashLookup,
  runDir: string,
  yIndex: number,
  xIndex?: number,
): string | null {
  const key = placementKey(runDir, yIndex);
  return (
    (xIndex === undefined
      ? lookup.firstByPlacement.get(key)
      : lookup.firstByX.get(xKey(runDir, yIndex, xIndex))) ?? null
  );
}

export function getHorizontalModelWindow({
  scrollLeft,
  viewportWidth,
  promptColumnWidth,
  modelColumnWidth,
  modelCount,
  overscan = 1,
}: HorizontalModelWindowInput): HorizontalModelWindow {
  if (modelCount <= 0 || modelColumnWidth <= 0 || viewportWidth <= 0) {
    return { startIndex: 0, endIndex: 0 };
  }

  const safeScrollLeft = Math.max(0, scrollLeft);
  const safeOverscan = Math.max(0, Math.floor(overscan));
  const firstVisible = Math.floor(safeScrollLeft / modelColumnWidth);
  const usableWidth = Math.max(0, viewportWidth - promptColumnWidth);
  const visibleEnd = Math.ceil(
    (safeScrollLeft + usableWidth) / modelColumnWidth,
  );
  const startIndex = Math.max(0, firstVisible - safeOverscan);
  const endIndex = Math.min(modelCount, visibleEnd + safeOverscan);

  return { startIndex, endIndex };
}

export function getShiftWheelDelta({
  shiftKey,
  deltaX,
  deltaY,
}: {
  shiftKey: boolean;
  deltaX: number;
  deltaY: number;
}): number | null {
  if (!shiftKey || deltaY === 0 || Math.abs(deltaX) >= Math.abs(deltaY)) {
    return null;
  }
  return deltaY;
}
