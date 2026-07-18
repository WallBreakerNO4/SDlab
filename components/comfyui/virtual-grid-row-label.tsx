import { Copy01Icon, StarIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useTranslations } from "next-intl";
import type { CSSProperties, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { CachedRow, RunGridYPromptParts } from "./virtual-grid-types";

type PromptPartKind = "artist" | "common";

/**
 * 行标签收藏星标状态。
 * 为 null / undefined 时（该行无 style_key 映射，或 style-items 拉取降级）不渲染星标。
 */
type FavoriteStarState = {
  isFavorite: boolean;
  onToggle: () => void;
};

type VirtualGridRowLabelProps = {
  cachedRow: CachedRow | undefined;
  preloadedYLabel: string;
  promptParts?: RunGridYPromptParts;
  yLabel: string;
  virtualRowIndex: number;
  onCopyRowLabel: (value: string) => void | Promise<void>;
  onCopyPromptPart: (
    value: string,
    kind: PromptPartKind,
  ) => void | Promise<void>;
  highlightTerm?: string;
  favoriteStar?: FavoriteStarState | null;
};

const NOVELAI_WEIGHT_RE = /^([\d.]+)::(.+?)( ::)?$/;
const LEGACY_WEIGHT_RE = /:([0-9.]+)[)\]}]*$/;

function renderHighlightedText(
  text: string,
  term: string | undefined,
): ReactNode {
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
        className="rounded-sm bg-yellow-300/80 px-0.5 text-black dark:bg-yellow-400/70 dark:text-yellow-950"
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

function parsePromptWeight(part: string): number {
  const novelaiMatch = part.match(NOVELAI_WEIGHT_RE);
  if (novelaiMatch) {
    const parsedWeight = Number.parseFloat(novelaiMatch[1]);
    return Number.isNaN(parsedWeight) ? 1 : parsedWeight;
  }

  const legacyMatch = part.match(LEGACY_WEIGHT_RE);
  if (!legacyMatch) return 1;
  const parsedWeight = Number.parseFloat(legacyMatch[1]);
  return Number.isNaN(parsedWeight) ? 1 : parsedWeight;
}

function PromptTokens({
  value,
  highlightTerm,
}: {
  value: string;
  highlightTerm?: string;
}) {
  const parts = value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

  if (parts.length <= 1) {
    return (
      <p className="text-muted-foreground w-full wrap-break-word font-mono text-[10px] leading-relaxed">
        {renderHighlightedText(value, highlightTerm)}
      </p>
    );
  }

  return (
    <div className="flex max-h-full flex-wrap content-start gap-1">
      {parts.map((part, index) => {
        const weight = parsePromptWeight(part);
        if (weight === 1) {
          return (
            <span
              key={`${part}-${index}`}
              className="bg-muted/60 text-muted-foreground border-border/50 inline-block max-w-full truncate rounded border px-1.5 py-0.5 font-mono text-[10px] leading-none"
            >
              {renderHighlightedText(part, highlightTerm)}
            </span>
          );
        }

        if (weight < 1) {
          return (
            <span
              key={`${part}-${index}`}
              className="bg-muted/30 text-muted-foreground border-border/20 inline-block max-w-full truncate rounded border px-1.5 py-0.5 font-mono text-[10px] leading-none"
              style={{ opacity: Math.max(0.3, weight) }}
            >
              {renderHighlightedText(part, highlightTerm)}
            </span>
          );
        }

        const ratio = Math.min(Math.max(weight - 1, 0), 1);
        const style = {
          "--weight-hue": Math.round(220 - 220 * ratio),
          fontWeight: Math.min(Math.round(400 + (weight - 1) * 400), 900),
        } as CSSProperties;

        return (
          <span
            key={`${part}-${index}`}
            className="inline-block max-w-full truncate rounded border border-[hsla(var(--weight-hue),80%,50%,0.3)] bg-[hsla(var(--weight-hue),80%,50%,0.15)] px-1.5 py-0.5 font-mono text-[10px] leading-none text-[hsl(var(--weight-hue),80%,40%)] dark:text-[hsl(var(--weight-hue),80%,65%)]"
            style={style}
          >
            {renderHighlightedText(part, highlightTerm)}
          </span>
        );
      })}
    </div>
  );
}

function FavoriteStarButton({
  state,
  className,
}: {
  state: FavoriteStarState;
  className?: string;
}) {
  const t = useTranslations("styleFavorites");
  const actionLabel = state.isFavorite ? t("remove") : t("add");
  return (
    <Button
      type="button"
      size="icon-xs"
      variant="ghost"
      className={cn(
        "h-5 w-5",
        state.isFavorite
          ? "text-amber-500 hover:text-amber-600 dark:text-amber-400 dark:hover:text-amber-300"
          : "text-muted-foreground hover:text-foreground",
        className,
      )}
      aria-label={actionLabel}
      aria-pressed={state.isFavorite}
      title={actionLabel}
      data-testid="run-grid-favorite-star"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        state.onToggle();
      }}
    >
      <HugeiconsIcon
        icon={StarIcon}
        className="h-3 w-3"
        fill={state.isFavorite ? "currentColor" : "none"}
      />
    </Button>
  );
}

function PromptPartSection({
  kind,
  label,
  value,
  highlightTerm,
  onCopy,
  trailing,
}: {
  kind: PromptPartKind;
  label: string;
  value: string;
  highlightTerm?: string;
  onCopy: (value: string, kind: PromptPartKind) => void | Promise<void>;
  /** 头部右侧附加小图标（星标），渲染在复制按钮左侧，不挤压现有交互 */
  trailing?: ReactNode;
}) {
  const t = useTranslations("virtualGrid");
  const copyLabel = kind === "artist" ? t("copyArtist") : t("copyCommonPrompt");

  return (
    <section
      className="group/prompt-part relative flex min-h-0 flex-col overflow-hidden px-3 py-2"
      data-testid={`run-grid-${kind}-prompt`}
    >
      <div className="mb-1.5 flex h-5 shrink-0 items-center justify-between gap-2">
        <span className="text-foreground/70 text-[9px] font-semibold uppercase">
          {label}
        </span>
        <div className="flex items-center gap-0.5">
          {trailing}
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            className="text-muted-foreground hover:text-foreground -mr-1 h-5 w-5"
            aria-label={copyLabel}
            title={copyLabel}
            data-testid={`run-grid-copy-${kind}`}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              void onCopy(value, kind);
            }}
          >
            <HugeiconsIcon icon={Copy01Icon} className="h-3 w-3" />
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden pr-1">
        <PromptTokens value={value} highlightTerm={highlightTerm} />
      </div>
      <div className="from-background/95 pointer-events-none absolute inset-x-3 bottom-0 h-4 bg-linear-to-t to-transparent" />
    </section>
  );
}

function LegacyRowLabel({
  value,
  highlightTerm,
  onCopy,
}: {
  value: string;
  highlightTerm?: string;
  onCopy: (value: string) => void | Promise<void>;
}) {
  const t = useTranslations("virtualGrid");
  if (!value || value === "-") {
    return <span className="text-muted-foreground/50 text-[10px]">-</span>;
  }

  return (
    <button
      type="button"
      className="h-full w-full cursor-pointer overflow-hidden pr-6 text-left transition-opacity hover:opacity-80"
      onClick={() => void onCopy(value)}
      title={t("clickToCopy")}
    >
      <PromptTokens value={value} highlightTerm={highlightTerm} />
    </button>
  );
}

export function VirtualGridRowLabel({
  cachedRow,
  preloadedYLabel,
  promptParts,
  yLabel,
  virtualRowIndex,
  onCopyRowLabel,
  onCopyPromptPart,
  highlightTerm,
  favoriteStar,
}: VirtualGridRowLabelProps) {
  const t = useTranslations("virtualGrid");
  const artist = promptParts?.artist?.trim() || null;
  const commonPrompt = promptParts?.commonPrompt?.trim() || null;
  const hasPromptParts = artist !== null || commonPrompt !== null;

  const legacyLabel =
    cachedRow && cachedRow.status === "ready"
      ? (cachedRow.yValue ?? preloadedYLabel) || "-"
      : cachedRow && cachedRow.status === "error"
        ? preloadedYLabel || t("loadFailed")
        : yLabel;

  const starButton = favoriteStar ? (
    <FavoriteStarButton state={favoriteStar} />
  ) : null;

  return (
    <div
      className="bg-background/95 supports-backdrop-filter:bg-background/80 sticky left-0 z-20 flex h-full w-full overflow-hidden border-r border-border/40 text-xs backdrop-blur"
      data-testid="run-grid-y-label"
    >
      {hasPromptParts ? (
        <div
          className={cn(
            "grid min-h-0 flex-1",
            artist && commonPrompt
              ? "grid-rows-2 divide-y divide-border/40"
              : "grid-rows-1",
          )}
        >
          {artist ? (
            <PromptPartSection
              kind="artist"
              label={t("artistLabel")}
              value={artist}
              highlightTerm={highlightTerm}
              onCopy={onCopyPromptPart}
              trailing={starButton}
            />
          ) : null}
          {commonPrompt ? (
            <PromptPartSection
              kind="common"
              label={t("commonPromptLabel")}
              value={commonPrompt}
              highlightTerm={highlightTerm}
              onCopy={onCopyPromptPart}
              trailing={artist ? null : starButton}
            />
          ) : null}
        </div>
      ) : (
        <div className="relative min-h-0 flex-1 overflow-hidden px-3 py-2">
          <LegacyRowLabel
            value={legacyLabel}
            highlightTerm={highlightTerm}
            onCopy={onCopyRowLabel}
          />
          {favoriteStar ? (
            <FavoriteStarButton
              state={favoriteStar}
              className="absolute right-1 top-1 z-10"
            />
          ) : null}
          <div className="from-background/95 pointer-events-none absolute inset-x-3 bottom-0 h-8 bg-linear-to-t to-transparent" />
        </div>
      )}
      <div className="text-muted-foreground/30 pointer-events-none absolute right-2 bottom-1 z-10 font-mono text-[10px] select-none">
        #{virtualRowIndex + 1}
      </div>
    </div>
  );
}
