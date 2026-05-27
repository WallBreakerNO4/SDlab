import { useTranslations } from "next-intl";
import type { CSSProperties, ReactNode } from "react";

import type { CachedRow } from "./virtual-grid-types";

type VirtualGridRowLabelProps = {
  cachedRow: CachedRow | undefined;
  preloadedYLabel: string;
  yLabel: string;
  virtualRowIndex: number;
  onCopyRowLabel: (value: string) => void | Promise<void>;
  highlightTerm?: string;
};

function renderHighlightedText(text: string, term: string | undefined): ReactNode {
  if (!term || !term.trim()) return text;
  const lowerText = text.toLowerCase();
  const lowerTerm = term.trim().toLowerCase();
  if (!lowerText.includes(lowerTerm)) return text;

  const result: ReactNode[] = [];
  let lastIndex = 0;
  let index = lowerText.indexOf(lowerTerm);
  let key = 0;
  while (index !== -1) {
    if (index > lastIndex) {
      result.push(text.slice(lastIndex, index));
    }
    result.push(
      <mark
        key={`h-${key++}`}
        className="bg-yellow-300/80 text-black dark:bg-yellow-400/70 dark:text-yellow-950 rounded-sm px-0.5"
      >
        {text.slice(index, index + lowerTerm.length)}
      </mark>,
    );
    lastIndex = index + lowerTerm.length;
    index = lowerText.indexOf(lowerTerm, lastIndex);
  }
  if (lastIndex < text.length) {
    result.push(text.slice(lastIndex));
  }
  return result;
}

export function VirtualGridRowLabel({
  cachedRow,
  preloadedYLabel,
  yLabel,
  virtualRowIndex,
  onCopyRowLabel,
  highlightTerm,
}: VirtualGridRowLabelProps) {
  const t = useTranslations("virtualGrid");
  return (
    <div
      className="bg-background/95 sticky left-0 z-20 flex h-full w-full border-r border-border/40 px-3 py-2 text-xs backdrop-blur supports-backdrop-filter:bg-background/80 overflow-hidden"
      data-testid="run-grid-y-label"
    >
      <div className="flex flex-col items-start justify-between w-full h-full gap-1 relative group/y-label">
        <div className="flex-1 w-full overflow-hidden pr-6">
          {(() => {
            const labelText =
              cachedRow && cachedRow.status === "ready"
                ? ((cachedRow.yValue ?? preloadedYLabel) || "-")
                : cachedRow && cachedRow.status === "error"
                  ? (preloadedYLabel || t("loadFailed"))
                  : yLabel;

            if (!labelText || labelText === "-") {
              return (
                <span className="text-muted-foreground/50 text-[10px]">-</span>
              );
            }

            if (labelText.includes(",")) {
              const parts = labelText
                .split(",")
                .map((part) => part.trim())
                .filter(Boolean);
              return (
                <div
                  className="flex flex-wrap gap-1 content-start max-h-full cursor-pointer hover:opacity-80 transition-opacity"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    void onCopyRowLabel(labelText);
                  }}
                  title={t("clickToCopy")}
                >
                  {parts.map((part, index) => {
                    let weight = 1;
                    // NovelAI format: weight::tag ::
                    const novelaiMatch = part.match(
                      /^([\d.]+)::(.+?)( ::)?$/,
                    );
                    if (novelaiMatch) {
                      const parsedWeight = parseFloat(novelaiMatch[1]);
                      if (!isNaN(parsedWeight)) {
                        weight = parsedWeight;
                      }
                    } else {
                      // Legacy WebUI format: (tag:weight)
                      const match = part.match(/:([0-9.]+)[)\]}]*$/);
                      if (match) {
                        const parsedWeight = parseFloat(match[1]);
                        if (!isNaN(parsedWeight)) {
                          weight = parsedWeight;
                        }
                      }
                    }

                    if (weight === 1) {
                      return (
                        <span
                          key={index}
                          className="inline-block border bg-muted/60 text-muted-foreground border-border/50 rounded px-1.5 py-0.5 text-[10px] font-mono leading-none truncate max-w-full transition-all"
                        >
                          {renderHighlightedText(part, highlightTerm)}
                        </span>
                      );
                    }

                    if (weight < 1) {
                      const opacity = Math.max(0.3, weight);
                      return (
                        <span
                          key={index}
                          className="inline-block border bg-muted/30 text-muted-foreground border-border/20 rounded px-1.5 py-0.5 text-[10px] font-mono leading-none truncate max-w-full transition-all"
                          style={{ opacity }}
                        >
                          {renderHighlightedText(part, highlightTerm)}
                        </span>
                      );
                    }

                    const ratio = Math.min(Math.max((weight - 1) / 1, 0), 1);
                    const hue = Math.round(220 - 220 * ratio);
                    const fontWeight = Math.min(
                      Math.round(400 + (weight - 1) * 400),
                      900,
                    );

                    const style = {
                      "--weight-hue": hue,
                      fontWeight,
                    } as CSSProperties;

                    return (
                      <span
                        key={index}
                        className="inline-block border rounded px-1.5 py-0.5 text-[10px] font-mono leading-none truncate max-w-full transition-all bg-[hsla(var(--weight-hue),80%,50%,0.15)] border-[hsla(var(--weight-hue),80%,50%,0.3)] text-[hsl(var(--weight-hue),80%,40%)] dark:text-[hsl(var(--weight-hue),80%,65%)]"
                        style={style}
                      >
                        {renderHighlightedText(part, highlightTerm)}
                      </span>
                    );
                  })}
                </div>
              );
            }

            return (
              <p
                  className="text-muted-foreground text-[10px] leading-relaxed wrap-break-word w-full cursor-pointer hover:opacity-80 transition-opacity"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    void onCopyRowLabel(labelText);
                  }}
                  title={t("clickToCopy")}
                >
                  {renderHighlightedText(labelText, highlightTerm)}
                </p>
            );
          })()}
        </div>
        <div className="absolute bottom-4 left-0 right-0 h-8 bg-linear-to-t from-background/95 to-transparent pointer-events-none" />
        <div className="absolute -bottom-1 -right-1 text-[10px] font-mono text-muted-foreground/30 select-none pointer-events-none">
          #{virtualRowIndex + 1}
        </div>
      </div>
    </div>
  );
}
