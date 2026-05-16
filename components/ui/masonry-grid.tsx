"use client";

import { useEffect, useMemo, useState } from "react";

type Breakpoints = Record<number | "default", number>;

const DEFAULT_BREAKPOINTS: Breakpoints = { default: 1, 768: 2, 1024: 3 };

function getColumnCount(width: number, breakpoints: Breakpoints): number {
  let count = breakpoints.default;
  for (const [bp, cols] of Object.entries(breakpoints)) {
    if (bp !== "default" && width >= parseInt(bp, 10)) {
      count = cols;
    }
  }
  return count;
}

type MasonryGridProps = {
  children: React.ReactNode[];
  breakpoints?: Breakpoints;
  className?: string;
};

export function MasonryGrid({
  children,
  breakpoints = DEFAULT_BREAKPOINTS,
  className,
}: MasonryGridProps) {
  // Default to 1 column for SSR to avoid hydration mismatch.
  // Client-side useEffect will update to the correct count after mount.
  const [columnCount, setColumnCount] = useState(breakpoints.default);

  useEffect(() => {
    const update = () => {
      setColumnCount(getColumnCount(window.innerWidth, breakpoints));
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [breakpoints]);

  const columns = useMemo(() => {
    const cols: React.ReactNode[][] = Array.from(
      { length: columnCount },
      () => [],
    );
    children.forEach((child, i) => {
      cols[i % columnCount].push(child);
    });
    return cols;
  }, [children, columnCount]);

  return (
    <div className={`flex gap-8 ${className || ""}`}>
      {columns.map((col, colIndex) => (
        <div key={colIndex} className="flex-1 flex flex-col gap-8 min-w-0">
          {col}
        </div>
      ))}
    </div>
  );
}
