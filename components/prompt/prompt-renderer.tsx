"use client"

import type { PromptNode } from "@/lib/prompt-types"
import { TagNodeComponent } from "./tag-node"
import { ChoiceNodeComponent } from "./choice-node"
import { cn } from "@/lib/utils"

interface PromptRendererProps {
  nodes: PromptNode[]
  pathPrefix?: string
  className?: string
}

export function PromptRenderer({
  nodes,
  pathPrefix = "",
  className,
}: PromptRendererProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {nodes.map((node, index) => {
        const nodePath = `${pathPrefix}-${index}`
        if (node.type === "tag") {
          return <TagNodeComponent key={nodePath} node={node} />
        } else if (node.type === "choice") {
          return (
            <ChoiceNodeComponent
              key={nodePath}
              node={node}
              choiceId={nodePath}
            />
          )
        }
        return null
      })}
    </div>
  )
}
