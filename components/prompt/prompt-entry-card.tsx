"use client"

import { memo } from "react"
import type { Entry, TargetModel } from "@/lib/prompt-types"
import { PromptRenderer } from "./prompt-renderer"
import { CharacterBlockComponent } from "./character-block"
import { CopyButton } from "./copy-button"
import { hasPlaceholders } from "@/lib/prompt-formatter"
import { cn } from "@/lib/utils"
import { AlertTriangle } from "lucide-react"

interface EntryCardProps {
  entry: Entry
  model: TargetModel
  highlight?: boolean
}

export const PromptEntryCard = memo(function PromptEntryCard({
  entry,
  model,
  highlight,
}: EntryCardProps) {
  const { name, prompt, notes, variants } = entry
  const hasPlaceholder = hasPlaceholders(prompt.base) ||
    prompt.characters.some((c) => hasPlaceholders(c.tags))

  return (
    <div className={cn("rounded-lg border bg-card p-4 shadow-sm", highlight && "entry-highlight")}>
      {/* 头部 */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold leading-tight">{name}</h3>
          {notes && (
            <p className="mt-1 text-xs text-muted-foreground">{notes}</p>
          )}
        </div>
        <CopyButton prompt={prompt} model={model} prefix={entry.id} size="sm" />
      </div>

      {/* 占位符警告 */}
      {hasPlaceholder && (
        <div className="mb-2 flex items-center gap-1.5 rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 px-2 py-1.5 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>此条目包含占位符，复制前请确认已替换</span>
        </div>
      )}

      {/* Prompt 渲染 */}
      <div className="space-y-2">
        <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
          Tags
        </div>
        <PromptRenderer nodes={prompt.base} pathPrefix={entry.id} />

        {prompt.characters.length > 0 && (
          <CharacterBlockComponent
            characters={prompt.characters}
            pathPrefix={entry.id}
          />
        )}
      </div>

      {/* 注释 */}
      {prompt.comments.length > 0 && (
        <div className="mt-2 text-[10px] text-muted-foreground border-t pt-2">
          {prompt.comments.map((c, i) => (
            <div key={i}>💬 {c}</div>
          ))}
        </div>
      )}

      {/* 变体 */}
      {variants && variants.length > 0 && (
        <div className="mt-3 space-y-2 border-t pt-2">
          <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
            变体
          </div>
          {variants.map((variant, i) => (
            <div
              key={i}
              className="rounded-md border border-dashed bg-muted/30 p-2"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-medium">{variant.name}</span>
                <CopyButton
                  prompt={variant.prompt}
                  model={model}
                  prefix={`${entry.id}-var-${i}`}
                  size="sm"
                />
              </div>
              <PromptRenderer
                nodes={variant.prompt.base}
                pathPrefix={`${entry.id}-var-${i}`}
              />
              {variant.prompt.characters.length > 0 && (
                <CharacterBlockComponent
                  characters={variant.prompt.characters}
                  pathPrefix={`${entry.id}-var-${i}`}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
})
