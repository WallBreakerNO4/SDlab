"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { HugeiconsIcon } from "@hugeicons/react";
import { ArrowDown01Icon, StarIcon } from "@hugeicons/core-free-icons";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { StyleKey } from "@/lib/style-favorites";

/**
 * 收藏面板行数据：收藏经 style-items 客户端 join + 防御性过滤后的结果。
 * label 取当前 run 网格行标签（不用收藏快照），见 virtual-grid.tsx 的 join 逻辑。
 */
export type GridFavoritesPanelRow = {
  styleKey: StyleKey;
  /** 1-based 网格行号（scrollToLineNumber / hash 直接消费） */
  lineNumber: number;
  /** 当前 run 网格行标签摘要 */
  label: string;
};

type GridFavoritesPanelProps = {
  isAuthenticated: boolean;
  rows: GridFavoritesPanelRow[];
  onRequireLogin: () => void;
  onJumpToLine: (lineNumber: number) => void;
};

/**
 * 工具栏收藏面板（模型详情页网格）。
 * - 按行号升序列出当前用户全部收藏，点击滚动到对应行并同步 URL hash。
 * - 未登录：入口保持收起，点击改弹登录框（与行标签星标一致）。
 * 仅做展示与跳转；收藏数据的拉取 / join / 过滤都在 virtual-grid.tsx 完成。
 */
export function GridFavoritesPanel({
  isAuthenticated,
  rows,
  onRequireLogin,
  onJumpToLine,
}: GridFavoritesPanelProps) {
  const t = useTranslations("styleFavorites");
  const [open, setOpen] = useState(true);

  return (
    <Collapsible
      open={isAuthenticated ? open : false}
      onOpenChange={(nextOpen) => {
        // 未登录：不展开面板，点击入口弹登录框
        if (!isAuthenticated) {
          onRequireLogin();
          return;
        }
        setOpen(nextOpen);
      }}
      data-testid="run-grid-favorites-panel"
    >
      <CollapsibleTrigger
        className="hover:bg-muted/40 flex w-full items-center justify-between border-b border-border/40 px-3 py-2 text-left text-xs font-medium transition-colors"
        data-testid="run-grid-favorites-trigger"
      >
        <span className="flex items-center gap-1.5">
          <HugeiconsIcon
            icon={StarIcon}
            strokeWidth={2}
            className="size-3 text-muted-foreground"
          />
          {t("panelTitle")}
        </span>
        <span className="flex items-center gap-1.5">
          {isAuthenticated && rows.length > 0 ? (
            <span
              aria-hidden="true"
              className="flex min-w-4 h-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[9px] font-semibold leading-none text-white"
            >
              {rows.length > 99 ? "99+" : rows.length}
            </span>
          ) : null}
          <HugeiconsIcon
            icon={ArrowDown01Icon}
            strokeWidth={2}
            className="size-3 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180"
          />
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="border-b border-border/40">
        {rows.length === 0 ? (
          <p className="px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground/70">
            {t("panelEmpty")}
          </p>
        ) : (
          <ul className="max-h-48 overflow-y-auto py-1">
            {rows.map((row) => (
              <li key={row.styleKey}>
                <button
                  type="button"
                  className="hover:bg-muted/40 flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors"
                  onClick={() => onJumpToLine(row.lineNumber)}
                  title={row.label}
                  data-testid="run-grid-favorites-item"
                  data-line-number={row.lineNumber}
                >
                  <span className="w-8 shrink-0 text-[10px] tabular-nums text-muted-foreground/70">
                    #{row.lineNumber}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-xs">
                    {row.label}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
