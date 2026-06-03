"use client"

import type { TagNode } from "@/lib/prompt-types"
import { useModel } from "@/lib/prompt-model-context"
import { cn } from "@/lib/utils"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Badge } from "@/components/ui/badge"

interface TagNodeComponentProps {
  node: TagNode
}

export function TagNodeComponent({ node }: TagNodeComponentProps) {
  const { text, weight, comment, placeholder } = node
  const { model, weightMode } = useModel()

  // Anima 模式下显示平方后的权重
  const displayWeight =
    weightMode === "anima" && model === "comfyui"
      ? weight * weight
      : weight

  const weightStr = displayWeight !== 1.0 ? `×${displayWeight.toFixed(2)}` : null

  if (placeholder) {
    return (
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded border border-dashed px-1.5 py-0.5 text-xs",
                "border-muted-foreground/40 text-muted-foreground bg-muted/50 cursor-help"
              )}
            >
              <span className="italic">{text}</span>
              {weightStr && (
                <span className="text-[10px] opacity-60">{weightStr}</span>
              )}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            <p className="text-xs">此 tag 为占位符，请替换为实际内容</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs",
              "border-border bg-background hover:bg-accent transition-colors cursor-default"
            )}
          >
            <span>{text}</span>
            {weightStr && (
              <Badge
                variant="secondary"
                className="h-3.5 px-1 text-[9px] font-normal leading-none"
              >
                {weightStr}
              </Badge>
            )}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs space-y-1">
          {weightStr && (
            <p className="text-[10px] text-muted-foreground">
              权重: {displayWeight.toFixed(2)}
            </p>
          )}
          {comment && (
            <p className="text-xs">{comment}</p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
