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
