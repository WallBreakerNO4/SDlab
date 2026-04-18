"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  type RefObject,
} from "react";

import type { Virtualizer } from "@tanstack/react-virtual";

import {
  buildScrollAnchor,
  loadSavedScrollAnchor,
  parseLineNumberFromHash,
  resolveScrollOffsetFromAnchor,
  saveScrollAnchor,
} from "./virtual-grid-utils";

type UseVirtualGridScrollOptions = {
  scrollElementRef: RefObject<HTMLDivElement | null>;
  rowVirtualizer: Virtualizer<HTMLDivElement, Element>;
  gridYIndexes: number[];
  rowHeight: number;
  runDir: string;
  scrollViewportWidth: number | null;
};

export function useVirtualGridScroll({
  scrollElementRef,
  rowVirtualizer,
  gridYIndexes,
  rowHeight,
  runDir,
  scrollViewportWidth,
}: UseVirtualGridScrollOptions) {
  const didRestoreScrollRef = useRef(false);

  const scrollToLineNumber = useCallback(
    (lineNumber: number): boolean => {
      if (
        !Number.isSafeInteger(lineNumber) ||
        lineNumber < 1 ||
        lineNumber > gridYIndexes.length
      ) {
        return false;
      }

      rowVirtualizer.scrollToIndex(lineNumber - 1, { align: "start" });
      return true;
    },
    [gridYIndexes.length, rowVirtualizer],
  );

  const scrollToHashLine = useCallback(
    (rawHash: string): boolean => {
      const lineNumber = parseLineNumberFromHash(rawHash, gridYIndexes.length);
      if (lineNumber === null) {
        return false;
      }

      return scrollToLineNumber(lineNumber);
    },
    [gridYIndexes.length, scrollToLineNumber],
  );

  const syncUrlHashWithLineNumber = useCallback((lineNumber: number) => {
    if (typeof window === "undefined") {
      return;
    }

    const nextHash = encodeURIComponent(String(lineNumber));
    const nextUrl = `${window.location.pathname}${window.location.search}#${nextHash}`;

    window.history.replaceState(null, "", nextUrl);
  }, []);

  const persistCurrentScrollAnchor = useCallback(() => {
    const scrollElement = scrollElementRef.current;
    if (!scrollElement) return;

    const anchor = buildScrollAnchor(
      scrollElement.scrollTop,
      gridYIndexes,
      rowHeight,
    );
    if (!anchor) return;

    saveScrollAnchor(runDir, anchor);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scrollElementRef is a stable ref
  }, [gridYIndexes, rowHeight, runDir]);

  useLayoutEffect(() => {
    if (didRestoreScrollRef.current) {
      return;
    }

    if (scrollViewportWidth === null) {
      return;
    }

    didRestoreScrollRef.current = true;
    if (scrollToHashLine(window.location.hash)) {
      return;
    }

    const anchor = loadSavedScrollAnchor(runDir);
    if (!anchor) {
      return;
    }

    const targetOffset = resolveScrollOffsetFromAnchor(
      anchor,
      gridYIndexes,
      rowHeight,
    );
    if (targetOffset === null) {
      return;
    }

    rowVirtualizer.scrollToOffset(targetOffset);
  }, [
    gridYIndexes,
    rowHeight,
    rowVirtualizer,
    runDir,
    scrollToHashLine,
    scrollViewportWidth,
  ]);

  useEffect(() => {
    const handleHashChange = () => {
      scrollToHashLine(window.location.hash);
    };

    window.addEventListener("hashchange", handleHashChange);

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, [scrollToHashLine]);

  useEffect(() => {
    const element = scrollElementRef.current;
    if (!element) {
      return;
    }

    let frameId: number | null = null;

    const persistOnNextFrame = () => {
      if (frameId !== null) {
        return;
      }

      frameId = window.requestAnimationFrame(() => {
        frameId = null;
        persistCurrentScrollAnchor();
      });
    };

    element.addEventListener("scroll", persistOnNextFrame, { passive: true });

    return () => {
      element.removeEventListener("scroll", persistOnNextFrame);
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
      persistCurrentScrollAnchor();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scrollElementRef is a stable ref
  }, [persistCurrentScrollAnchor]);

  useEffect(() => {
    if (!didRestoreScrollRef.current) {
      return;
    }

    persistCurrentScrollAnchor();
  }, [persistCurrentScrollAnchor]);

  return { scrollToLineNumber, syncUrlHashWithLineNumber };
}