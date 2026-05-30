"use client"

import { cn } from "@/lib/utils"
import { ChevronRight } from "lucide-react"
import type { TocNode } from "@/lib/prompt-types"

const NODE_KEY_SEP = "\0"

export function nodeKey(path: string[]): string {
  return path.join(NODE_KEY_SEP)
}

interface TocTreeProps {
  nodes: TocNode[]
  activeSection: string | null
  onSectionClick: (title: string) => void
  expandedNodes: Set<string>
  onToggleExpand: (key: string) => void
  level?: number
  parentPath?: string[]
}

function TocItem({
  node,
  activeSection,
  onSectionClick,
  expandedNodes,
  onToggleExpand,
  level = 0,
  parentPath = [],
}: {
  node: TocNode
  activeSection: string | null
  onSectionClick: (title: string) => void
  expandedNodes: Set<string>
  onToggleExpand: (key: string) => void
  level?: number
  parentPath?: string[]
}) {
  const hasChildren = node.children && node.children.length > 0
  const isActive = activeSection === node.title
  const nodePath = [...parentPath, node.title]
  const key = nodeKey(nodePath)
  const expanded = expandedNodes.has(key) || level < 1

  const handleClick = () => {
    onSectionClick(node.title)
    if (hasChildren) {
      onToggleExpand(key)
    }
  }

  return (
    <div>
      <button
        onClick={handleClick}
        className={cn(
          "w-full flex items-center gap-1 rounded-md px-2 py-1 text-left text-xs transition-colors",
          "hover:bg-accent",
          isActive && "bg-accent font-medium text-accent-foreground"
        )}
        style={{ paddingLeft: `${8 + level * 12}px` }}
      >
        {hasChildren && (
          <ChevronRight
            className={cn(
              "h-3 w-3 shrink-0 text-muted-foreground transition-transform",
              expanded && "rotate-90"
            )}
            onClick={(e) => {
              e.stopPropagation()
              onToggleExpand(key)
            }}
          />
        )}
        {!hasChildren && <span className="w-3 shrink-0" />}
        <span className="truncate">{node.title}</span>
      </button>

      {hasChildren && expanded && (
        <TocTree
          nodes={node.children!}
          activeSection={activeSection}
          onSectionClick={onSectionClick}
          expandedNodes={expandedNodes}
          onToggleExpand={onToggleExpand}
          level={level + 1}
          parentPath={nodePath}
        />
      )}
    </div>
  )
}

export function TocTree({
  nodes,
  activeSection,
  onSectionClick,
  expandedNodes,
  onToggleExpand,
  level = 0,
  parentPath = [],
}: TocTreeProps) {
  return (
    <div className="space-y-0.5">
      {nodes.map((node) => (
        <TocItem
          key={node.title}
          node={node}
          activeSection={activeSection}
          onSectionClick={onSectionClick}
          expandedNodes={expandedNodes}
          onToggleExpand={onToggleExpand}
          level={level}
          parentPath={parentPath}
        />
      ))}
    </div>
  )
}
